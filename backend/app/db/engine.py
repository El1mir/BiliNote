import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

from app.utils.logger import get_logger

_INIT_DB_DONE = False

load_dotenv()

logger = get_logger(__name__)

# 默认 SQLite，如果想换 PostgreSQL 或 MySQL，可以直接改 .env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bili_note.db")


def _int_env(name: str, default: int) -> int:
    """读一个整数环境变量，非法值一律回落到默认值。

    直接用 ``int(os.getenv(...))`` 的话，用户手滑写了个 ``DB_POOL_SIZE=abc``
    就会在 **import 阶段** 抛 ValueError —— 整个后端连启动都做不到，而配置项
    本身只是个调优旋钮，不该有这种杀伤力。
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "环境变量 %s 不是合法整数（%r），使用默认值 %s", name, raw, default
        )
        return default


# SQLite 写锁的等待时长（毫秒）。长批量生成时，同一时刻可能有多个任务在写
# video_tasks / media_resources / media_cleanup_runs，SQLite 默认的等待时间在
# 慢盘或杀毒软件扫描下完全不够，直接抛 "database is locked" 让整批任务失败。
# 放宽到 10s：与其立刻报错，不如多等一会儿。
SQLITE_BUSY_TIMEOUT_MS = _int_env("SQLITE_BUSY_TIMEOUT_MS", 10000)

# SQLite 需要特定连接参数，其他数据库不需要
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

_pool_args = {}
if not DATABASE_URL.startswith("sqlite"):
    _pool_args = {
        "pool_size": _int_env("DB_POOL_SIZE", 10),
        "max_overflow": _int_env("DB_MAX_OVERFLOW", 20),
        "pool_pre_ping": True,
    }

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
    **engine_args,
    **_pool_args,
)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, connection_record):
        """给每一条新建的 SQLite 连接挂上 PRAGMA（spec 009 / ticket 05）。

        为什么必须走 "connect" 事件而不是在 create_engine 里传一次参数：
        PRAGMA 是**连接级**状态，连接池里的每条连接都得单独设置一次，否则
        从池里新取出来的连接还是默认值（rollback journal + 无等待）。

        * ``journal_mode=WAL`` —— 默认的 rollback journal 在写入时会独占整个
          数据库，读操作会被挡住。WAL 下读写可以并发，这正是「一边批量写任务
          行、一边查任务列表」的场景所需要的。
          副作用：SQLite 会额外生成 ``bili_note.db-wal`` 和 ``bili_note.db-shm``
          两个伴生文件。它们由 SQLite 自己管理，正常关闭连接时会被回收；即使
          进程被强杀残留下来，下一次打开数据库时 SQLite 也会自动读取/合并，
          不会丢数据。清库脚本只需要删主文件，但残留的 ``-wal`` / ``-shm``
          一并删掉更干净。
        * ``busy_timeout`` —— 遇到写锁时先重试等待，而不是立即返回 SQLITE_BUSY。
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_engine():
    return engine


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
