#!/usr/bin/python
# -*- coding:utf-8 -*-
import socket
import select
import time
import random
import types
import Queue

from handler import Handler, DefaultHandler
from channel import Channel


class TimeEvent(object):
    def __init__(self, func, args, kwargs, target_time, is_cron=True):
        self.func = func
        self.is_cron = is_cron
        self.time = target_time
        self.args = args
        self.kwargs = kwargs
        self.rm = False

    def invoke(self, excepted_time, real_time):
        self.func(excepted_time, real_time, *self.args, **self.kwargs)


class IO2Channel(Channel):
    """
    直接与IO关联的Channel
    """

    def __init__(self, server, client, _next):
        super(IO2Channel, self).__init__(server, client, _next)

    def input(self, data=None, recv=True):
        client_close = False
        try:
            if recv:
                request = self.client.recv(1024)
            else:
                request = data
        except Exception, e:
            client_close = True
        else:
            if request:
                self.next.input(request, recv)
            else:
                client_close = True
        if client_close:
            self.server.close(self.client)

    def output(self):
        response, end = self.next.output()
        if response:
            try:
                self.client.send(response)
            except (IOError, socket.error):
                self.server.close(self.client)
        if (not response or end) and self.client in self.server.outputs:
            self.server.outputs.remove(self.client)


class Channel2Handler(Channel):
    """
    与handler关联起来
    """

    def __init__(self, server, client, _next):
        super(Channel2Handler, self).__init__(server, client, _next)
        self.queue = Queue.Queue()

    def input(self, data, recv):
        response = None
        if recv:
            if isinstance(self.next, Handler):
                response = self.next.handle(self.server, self.client, data)
            elif isinstance(self.next, types.FunctionType):
                response = self.next(self.server, self.client, data)
        else:
            # 说明直接发出去
            response = data
        if response:
            self.queue.put(response)
            if self.client not in self.server.outputs:
                self.server.outputs.append(self.client)

    def output(self):
        try:
            return self.queue.get_nowait(), self.queue.empty()
        except Queue.Empty:
            return None, True

    def close(self):
        return self.next.close(self.server, self.client)


class Server(object):
    def _is_subclass_of(self, subclass, superclass):
        if not subclass or not superclass or not isinstance(subclass, types.TypeType) or not isinstance(superclass,
                                                                                                        types.TypeType):
            return False
        while True:
            if subclass is superclass:
                return True
            elif subclass is object:
                return False
            subclass = subclass.__base__

    def __init__(self, port=2333, host='', **kwargs):
        self.host = host
        self.port = port
        self.inputs = []
        self.outputs = []
        self.exceptions = []
        self.context = {}
        self.connect_pool = {}
        self.channel_class = None
        if 'handler' in kwargs and isinstance(kwargs['handler'], (Handler, types.FunctionType)):
            self.handler_class = kwargs['handler']
        else:
            self.handler_class = DefaultHandler
        if 'channels' in kwargs:
            cc = kwargs['channels']
            if self._is_subclass_of(cc, Channel):
                self.channel_class = [cc, ]
            elif isinstance(cc, (types.TupleType, types.ListType)) and len(cc) > 0:
                self.channel_class = [c for c in cc if self._is_subclass_of(c, Channel)]
        # self.input_buffer = {}
        # self.request_queue = {}
        # self.response_queue = {}
        self.timers = {}
        # 0 running 1 stopping 2 stopped
        self.state = 0

    def register_handler(self, handler):
        if handler and (
                self._is_subclass_of(handler, Handler) or isinstance(handler, types.FunctionType)) or isinstance(
                handler,
                Handler):
            self.handler_class = handler

    def register_channel(self, channel):
        if channel and self._is_subclass_of(channel, Channel):
            if not self.channel_class:
                self.channel_class = []
            self.channel_class.append(channel)

    def get_channel(self, client):
        """
        初始化链式的channel
        :param client:
        :return:
        """
        if client not in self.context:
            if self._is_subclass_of(self.handler_class, Handler):
                c = self.handler_class()
            elif isinstance(self.handler_class, (Handler, types.FunctionType)):
                c = self.handler_class
            else:
                return
            c = Channel2Handler(self, client, c)
            if self.channel_class:
                for claz in self.channel_class[::-1]:
                    c = claz(self, client, c)
            # IO2Channel在链的最前面
            c = IO2Channel(self, client, c)
            self.context[client] = c
        return self.context[client]

    def getpeername(self):
        return self.host, self.port

    def handle_io_event(self):
        # print 'waiting for next event'
        try:
            # print 'inputs:', self.inputs
            # print 'outputs:', self.outputs
            # print 'exceptins:', self.exceptions
            readable, writable, exceptional = select.select(self.inputs, self.outputs, self.exceptions,
                                                            self._get_timeout())
            for r in readable:
                if r is self.accepter:
                    # A readable socket is ready to accept  a connection
                    connection, addr = r.accept()
                    # print 'connection from, ', addr
                    connection.setblocking(False)
                    self.inputs.append(connection)
                    # print 'accept %s' % connection
                    self.get_channel(connection)
                else:
                    # readable from other system
                    try:
                        self.context[r].input()
                    except KeyError:
                        print '[%s] removed .' % r
            for w in writable:
                try:
                    self.context[w].output()
                except KeyError:
                    print '[%s] removed.' % w
            for e in exceptional:
                self.close(e)
                del self.context[e]
        except socket.error, e:
            print e


    def _get_timeout(self):
        """
        获取select的超时时间
        根据timeevent队列到目前为止的最小时间就算
        :return:
        """
        current = time.time()
        ret = 1  # default timeout 1s
        if not self.timers:
            # 如果没有超时事件，那么就不超时
            return ret
        for t in self.timers:
            timeout = t - current
            if timeout > 0:
                if not ret or timeout < ret:
                    # 找到最近过期时间
                    ret = timeout
        return ret

    def handle_timeout_event(self):
        # print 'handle the timers ...'
        current = time.time()
        reset_timers = {}
        # 计算下次循环的select 超时时间
        for t, events in self.timers.items():
            if t <= current and self.is_running():
                # 说明已经过了或者到时间了，需要处理
                for event in events:
                    if not event.rm:
                        event.invoke(t, current)
                    if event.is_cron and not event.rm:  # 需要再次判断，因为可能在event.invoke的时候调用rm_timer
                        if isinstance(event.time, types.TupleType):
                            next_time = random.uniform(event.time[0], event.time[1]) + t
                        else:
                            next_time = event.time + t
                        if next_time not in reset_timers:
                            reset_timers[next_time] = []
                        reset_timers[next_time].append(event)
                    if not event.is_cron and not event.rm:
                        event.rm = True
                    if event in self.timers[t]:
                        self.timers[t].remove(event)
                # 处理完了，就删除
                del self.timers[t]
        self.timers.update(reset_timers)
        # 重新计算select的超时时间
        # for t in self.timers:
        # if not self.timeout or (t > current and t - current < self.timeout):
        #         self.timeout = t - current
        # print 'next timeout is ', self.timeout

    def set_timer(self, target_time, is_cron, func, *args, **kwargs):
        """
        设置时间事件
        :param func: 超时事件处理函数 func(except_time, real_time, *args, **kwargs)
        :param target_time: 时间发生的时间
                            如果是固定的值：
                            如果target_time<current 那么下次执行时间为target_time+current_time 否则为target_time
                            否则是一个(min, max) tuple类型，表示范围在min-max之内的随机时间
        :param is_cron: 是否是定时任务,执行多次，否则只执行一次
        :return:
        """
        current_time = time.time()
        if isinstance(target_time, types.TupleType):
            if target_time[0] > target_time[1]:
                return  # invalide (min, max)
            _target_time = random.uniform(target_time[0], target_time[1])
        else:
            _target_time = target_time
        if _target_time < current_time:
            real_time = current_time + _target_time
        else:
            real_time = _target_time
        if real_time not in self.timers:
            self.timers[real_time] = []
        event = TimeEvent(func, args, kwargs, target_time, is_cron)
        self.timers[real_time].append(event)

    def rm_timer(self, func):
        """
        删除相对应的TimeEvent
        :param func:
        :return:
        """
        for events in self.timers.values():
            for event in events:
                if func == event.func:
                    event.rm = True

    def connect(self, addr):
        """
        主动连接
        :param addr: (ip, port)
        :return: client
        """
        if addr not in self.connect_pool:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(addr)
            client.setblocking(False)
            self.inputs.append(client)
            self.connect_pool[addr] = client
            self.get_channel(client)
        else:
            client = self.connect_pool[addr]
        # self.outputs.append(client)
        # if client not in self.inputs:
        # self.inputs.append(client)
        return client, self.context.get(client, None)

    def close(self, client):
        """
        关闭client连接
        :param client:
        :return:
        """
        self.context[client].close()
        addr = client.getpeername()
        if addr in self.connect_pool:
            del self.connect_pool[addr]
        if client in self.context:
            del self.context[client]
        if client in self.inputs:
            self.inputs.remove(client)
        if client in self.outputs:
            self.outputs.remove(client)
        if client in self.exceptions:
            self.exceptions.remove(client)
        try:
            client.close()
        except IOError, e:
            print e

    def stop(self):
        if self.state == 0:
            self.state = 1

    def is_running(self):
        return self.state == 0

    def is_stopping(self):
        return self.state == 1

    def is_stopped(self):
        return self.state == 2

    def realease(self):
        """
        停止服务, 释放资源
        :return:
        """
        if self.state == 0 or self.state == 2:
            # if running or has stopped, do nothing
            return
        self.state = 2
        self.finalize()

    def finalize(self):
        """
        关闭连接
        :return:
        """
        if self.state == 0 or self.state == 1:
            return
        for conn in self.context:
            try:
                conn.close()
            except Exception:
                pass
            else:
                if conn in self.inputs:
                    self.inputs.remove(conn)
                if conn in self.outputs:
                    self.outputs.remove(conn)
                if conn in self.exceptions:
                    self.exceptions.remove(conn)
        if self.accepter:
            try:
                self.accepter.close()
            except Exception:
                pass
            else:
                if self.accepter in self.inputs:
                    self.inputs.remove(self.accepter)

    def initialise(self):
        """
        初始化
        :return:
        """
        self.accepter = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.accepter.setblocking(False)
        self.accepter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.accepter.bind((self.host, self.port))
        self.accepter.listen(10)
        self.inputs.append(self.accepter)
        # 计算超时时间
        # self.timeout = None
        # current = time.time()
        # for t in self.timers:
        # timeout = t - current
        #     if not self.timeout or (timeout > 0 and timeout < self.timeout):
        #         self.timeout = timeout
        # set state
        self.state = 0

    def server_forever(self):
        """
        启动服务
        :return:
        """
        # init the server runtime env
        self.initialise()
        # Main Loop
        while self.inputs:
            # handle io
            self.handle_io_event()
            # handle timer
            self.handle_timeout_event()
            if not self.is_running():
                # stoppde or stopping
                break
        # release the resources
        self.realease()
        print 'Server stopped!'
