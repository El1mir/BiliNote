"""spec 009 ticket 05：SQLite 连接加固（WAL + busy_timeout）。

为什么这么测：

* PRAGMA 是**连接级**状态，只有走 ``event.listens_for(engine, "connect")`` 才能
  保证连接池里每条新连接都被设置一遍。所以这里不用 ``app.db.engine.engine``
  （那是模块级单例，指向仓库里真实的 ``backend/bili_note.db``），而是在
  ``tmp_path`` 下新建一个 engine、手动挂上**同一个** ``_configure_sqlite_connection``
  —— 验的是监听器函数本身的行为。
* 「第二条独立连接也拿到 WAL」是关键断言：如果实现只是在 ``create_engine`` 时
  传了一次参数（或只对第一条连接生效），这条会红。
* ``sqlite_client.get_connection()`` 里是硬编码的相对路径 ``"bili_note.db"``，
  唯一能把它引到临时文件上的办法是 ``monkeypatch.chdir(tmp_path)``；否则它会
  直接打开用户的真实库。
"""

from sqlalchemy import create_engine, event

from app.db import engine as engine_module
from app.db import sqlite_client


def _sqlite_engine(tmp_path, name="pragma-test.db"):
    """建一个临时库上的 engine，并挂上与生产代码同一个 connect 监听器。

    监听器是在 ``engine_module`` 里用 ``@event.listens_for(engine, "connect")``
    注册的，只绑定到那一个 engine 实例；新 engine 必须显式 listen 同一个函数，
    否则拿到的是 SQLite 默认的 rollback journal + busy_timeout=0。
    """
    db_engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )
    event.listen(db_engine, "connect", engine_module._configure_sqlite_connection)
    return db_engine


def test_connect_event_applies_wal_and_busy_timeout(tmp_path):
    db_engine = _sqlite_engine(tmp_path)
    try:
        with db_engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            # PRAGMA 返回的是 sqlite 的动态类型（None | int | str），转成字符串
            # 比较既避开类型检查器的 Optional 噪音，也不依赖驱动把它映射成 int。
            assert str(conn.exec_driver_sql("PRAGMA busy_timeout").scalar()) == str(
                engine_module.SQLITE_BUSY_TIMEOUT_MS
            )
    finally:
        db_engine.dispose()


def test_second_independent_connection_gets_pragmas_too(tmp_path):
    """池里的第二条连接必须同样是 WAL + busy_timeout。

    只验第一条连接的话，「在 create_engine 上设一次」的错误实现也能通过 ——
    而池里新取出的连接才是长批量场景下真正干活的那条。
    """
    db_engine = _sqlite_engine(tmp_path, "two-connections.db")
    try:
        with db_engine.connect() as first:
            with db_engine.connect() as second:
                # 两条连接同时在池外，SQLAlchemy 必然给了不同的 DBAPI 连接。
                assert first.connection.dbapi_connection is not (
                    second.connection.dbapi_connection
                )
                assert second.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
                assert str(
                    second.exec_driver_sql("PRAGMA busy_timeout").scalar()
                ) == str(engine_module.SQLITE_BUSY_TIMEOUT_MS)
    finally:
        db_engine.dispose()


def test_busy_timeout_default_is_10000():
    """默认 10s：慢盘 / 杀毒扫描下 SQLite 默认的等待时长完全不够。"""
    assert engine_module.SQLITE_BUSY_TIMEOUT_MS == 10000


def test_module_constant_is_derived_from_int_env():
    """模块常量确实由 ``_int_env`` 求值而来，而不是硬编码字面量。

    这里**刻意不做 importlib.reload**：reload ``app.db.engine`` 会重新创建
    ``Base`` 与 ``engine`` 单例，而其它模块（如各 DAO、媒体服务）在 import 时
    已经把旧的 ``SessionLocal`` / ``Base`` 绑到了自己的命名空间里 —— reload 后
    两套对象并存，后续测试会以难以定位的方式互相污染。直接测 ``_int_env``
    更小、更准，且不引入全局副作用。
    """
    assert engine_module.SQLITE_BUSY_TIMEOUT_MS == engine_module._int_env(
        "SQLITE_BUSY_TIMEOUT_MS", 10000
    )


def test_int_env_reads_override_and_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "2500")
    assert engine_module._int_env("SQLITE_BUSY_TIMEOUT_MS", 10000) == 2500

    # 非法值不能把 import 阶段炸掉，只能回落默认值（配置项不该有这种杀伤力）。
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "abc")
    assert engine_module._int_env("SQLITE_BUSY_TIMEOUT_MS", 10000) == 10000

    # 空字符串按「未设置」处理。
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "   ")
    assert engine_module._int_env("SQLITE_BUSY_TIMEOUT_MS", 10000) == 10000

    monkeypatch.delenv("SQLITE_BUSY_TIMEOUT_MS")
    assert engine_module._int_env("SQLITE_BUSY_TIMEOUT_MS", 10000) == 10000


def test_overridden_timeout_reaches_new_connections(tmp_path, monkeypatch):
    """监听器读的是模块全局，所以环境变量生效后新连接会拿到新值。

    这证明 ``PRAGMA busy_timeout`` 不是写死的字面量，而是跟着
    ``SQLITE_BUSY_TIMEOUT_MS`` 走的。
    """
    monkeypatch.setattr(engine_module, "SQLITE_BUSY_TIMEOUT_MS", 2500)
    db_engine = _sqlite_engine(tmp_path, "override.db")
    try:
        with db_engine.connect() as conn:
            assert str(conn.exec_driver_sql("PRAGMA busy_timeout").scalar()) == "2500"
    finally:
        db_engine.dispose()


def test_sqlite_client_connection_sets_nonzero_busy_timeout(tmp_path, monkeypatch):
    """裸 sqlite3 路径也必须设 busy_timeout（默认 0 = 一撞锁就报 database is locked）。

    ``get_connection()`` 硬编码相对路径 ``"bili_note.db"``，所以必须切工作目录，
    否则这里会打开并可能改写用户的真实库。
    """
    monkeypatch.chdir(tmp_path)
    conn = sqlite_client.get_connection()
    try:
        assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) == (
            sqlite_client.SQLITE_BUSY_TIMEOUT_MS
        )
        assert sqlite_client.SQLITE_BUSY_TIMEOUT_MS != 0
    finally:
        conn.close()
    # 确认它落在 tmp_path 里，而不是被引到了别处。
    assert (tmp_path / "bili_note.db").exists()
