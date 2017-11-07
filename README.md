1. 完成基本的网络通讯框架，使用python select做多路IO复用
2. 可以处理定时器事件
3. 单节点可以进行一些基本的操作(get  set  del  commit)
4. cluster内节点选举
5. Leader挂掉，其余节点从新选举出leader
6. 单个客户端连接Leader节点进行update操作时实现Leader Follower之间数据同步
7. client关闭后，node内进行资源释放
8. leader关闭后，释放follower资源
9. 开始编写简单的coroutine框架，简化异步的编程模型。

问题：
* 状态转换时，不能自动的处理状态内的定时时间处理函数
* 异步调用，整个程序的逻辑是分散的，考虑用**yield协程**重新改写一下事件循环的架构

Usage:

![image](https://raw.githubusercontent.com/aducode/statics/master/img/sraft-usage.png)


