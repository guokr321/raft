#!/usr/bin/python
# -*- coding:utf-8 -*-
from db.simple import DB
import types


class Config(object):
    """
    cluster的config信息
    """

    def __init__(self, host, port,
                 neighbors=None,
                 db=None,
                 heartbeat_rate=0.1,
                 heartbeat_timeout=2,
                 elect_timeout=(0.15, 0.3),
                 start_elect_timeout=(0.01, 0.05),
                 debug=False,
                 show_state_rate=3,
                 sync_count=10,
                 sync_rate=1):
        """
        构造方法
        :param host:        主机名
        :param port:        端口号
        :param neighbors:   相邻节点
        :param db:          数据存储引擎(名)
        :param heartbeat_rate: 心跳间隔
        :param heartbeat_timeout: 心跳响应超时时间
        :param elect_timeout: 选举超时时间
        :param start_elect_timeout: 开始选举的超时时间
        :param debug:       是否debug模式
        :param show_state_rate:  显示节点状态的时间间隔
        :param sync_count:  一次同步数量
        :param sync_rate:   同步间隔
        :return:
        """
        self.host = host
        self.port = port
        self.neighbors = neighbors if neighbors is not None else []
        self.heartbeat_timeout = heartbeat_timeout
        self.heartbeat_rate = heartbeat_rate
        self.elect_timeout = elect_timeout
        self.start_elect_timeout = start_elect_timeout
        self.debug = debug
        self.show_state_rate = show_state_rate
        self.sync_count = sync_count
        self.sync_rate = sync_rate
        # for db
        if db is None:
            self.db = DB()
        elif isinstance(db, types.StringTypes):
            # db engine name
            self.db = __import__('db').__dict__[db].__dict__['DB']()
        if (self.host, self.port) in self.neighbors:
            self.neighbors.remove((self.host, self.port, ))