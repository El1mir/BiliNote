"""裸 sqlite3 连接（不走 SQLAlchemy 的少量调用点）。

这里没有 ORM 会话，拿到的是一条全新的连接，所以 PRAGMA 必须在每次
``get_connection()`` 时重新设置一遍 —— PRAGMA 是连接级状态，不会持久化到
数据库文件里（``journal_mode=WAL`` 是唯一例外，它写进文件头，但每次显式声明
一次也无害，还能兼容从别处拿来的、仍是 rollback journal 的老库）。
"""

import sqlite3

from app.db.engine import SQLITE_BUSY_TIMEOUT_MS

#: 复用 engine 的取值，别再各写一份：之前这里是硬编码的 10000，与
#: ``app.db.engine`` 各读各的环境变量，改了 ``SQLITE_BUSY_TIMEOUT_MS`` 之后
#: 两条连接路径的等待时长会悄悄分叉（SQLAlchemy 路径变了、裸 sqlite3 路径没变）。
__all__ = ["SQLITE_BUSY_TIMEOUT_MS", "get_connection"]


def get_connection():
    conn = sqlite3.connect("bili_note.db")
    # 长批量下写锁冲突的兜底：默认 0 表示一撞锁就抛 "database is locked"。
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    return conn
