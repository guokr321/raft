#!/usr/bin/python
# -*- coding:utf-8 -*-


class Channel(object):
    def __init__(self, server, client, _next):
        self.server = server
        self.client = client
        self.next = _next

    def input(self, data, recv):
        """
        :param data 数据
        :param recv 是否从socket接受来的消息
                    当为False时，说明数据是发送到其他server的，不是server接受来的
        """
        pass

    def output(self):
        pass

    def close(self):
        """
        说明socket被关闭，传递到handler
        """
        return self.next.close()


class LineChannel(Channel):
    """
    保存客户端连接
    """

    def __init__(self, server, client, _next):
        super(LineChannel, self).__init__(server, client, _next)
        self.input_buffer = ''

    def input(self, request, recv):
        if not request:
            pass
        elif '\n' not in request:
            self.input_buffer += request
        else:
            msgs = request.split('\n')
            msg = (self.input_buffer + msgs[0]).strip()
            if msg:
                self.input_buffer = ''
                self.next.input(msg, recv)
            for msg in msgs[1:-1]:
                msg = msg.strip()
                if msg:
                    self.next.input(msg, recv)
            msg = msgs[-1]
            if msg:
                self.input_buffer = msg.strip()

    def output(self):
        data, end = self.next.output()
        return data+'\n' if data else None, end