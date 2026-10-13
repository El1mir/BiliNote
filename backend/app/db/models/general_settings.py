"""通用设置（spec 007，缓存边界字段见 spec 009 / ticket 07）。

单行表，``id`` 恒为 1，与 ``media_settings`` 同一套路。放这里的都是「跟具体
供应商/引擎无关、全局生效」的开关。
"""

from sqlalchemy import Column, Integer, String

from app.db.engine import Base

#: 最大笔记并行任务数量：后端同时执行的笔记生成任务数上限。
#:
#: 默认 3（spec 009 决策 3，此前是 1）。原来一批任务实际串行的根因不在这个数字 ——
#: ``/generate_notes`` 用 FastAPI ``BackgroundTasks`` 逐条 ``add_task``，而 Starlette
#: 的 ``BackgroundTasks.__call__`` 是 ``for task in self.tasks: await task()``，
#: **严格串行**，所以不管这个值调多大，一批任务的实际并发度恒为 1。spec 009 把批量
#: 入口改成受并行闸门约束的分发池之后，这个数字才真正生效。
#:
#: 为什么是 3 而不是更高：上游供应商自带 ``DEFAULT_PROVIDER_CONCURRENCY = 4`` 的
#: 限流，SQLite 也只有一个写者；3 能拿到接近 3 倍的吞吐，又不至于把两者打到报错。
DEFAULT_MAX_PARALLEL_NOTES = 3

#: 允许的上限，防止手改配置把并发开到把机器/供应商打爆。
MAX_PARALLEL_NOTES_LIMIT = 8

#: 本地媒体缓存总量上限（字节）。默认 10 GiB；**0 表示不限**。
#: 长批量（200 个视频）下音视频 + 截图轻松写满磁盘，所以要有个容量维度，
#: 和时间维度（media_settings 的保留天数）互补。
DEFAULT_CACHE_LIMIT_BYTES = 10 * 1024**3

#: 缓存上限的允许最大值（1 TiB）：手改数据库写个天文数字会让「超限才清理」
#: 永远不触发，等同于悄悄关掉这个功能，所以设个天花板。
MAX_CACHE_LIMIT_BYTES = 1024**4

#: 磁盘剩余空间门禁（字节）。默认 5 GiB：剩余低于这个值就不再启动新任务，
#: 避免把磁盘写满导致 SQLite/ffmpeg 直接失败。
DEFAULT_MIN_FREE_DISK_BYTES = 5 * 1024**3

#: 磁盘门禁的允许最大值（1 TiB）。
MAX_MIN_FREE_DISK_BYTES = 1024**4

#: 连续失败多少次后熔断（暂停继续派发新任务）。默认 5；**0 表示关闭熔断**。
#: 供应商挂掉时，批量任务会一个接一个地失败刷屏，熔断让用户先修问题再继续。
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 5

#: 熔断阈值的允许最大值，防止误填导致熔断形同虚设。
MAX_CIRCUIT_BREAKER_THRESHOLD = 100


class GeneralSettings(Base):
    __tablename__ = "general_settings"

    id = Column(Integer, primary_key=True, default=1)
    max_parallel_notes = Column(
        Integer, nullable=False, default=DEFAULT_MAX_PARALLEL_NOTES
    )
    # 以下三列是 spec 009 / ticket 07 新增的「缓存边界」。
    # 都用 Integer 存字节/次数：SQLite 的 INTEGER 是 64 位，10 GiB 甚至 1 TiB
    # 都远在范围内，不需要 BigInteger（换库时 BigInteger 反而有兼容差异）。
    # nullable=True 是为了兼容老库迁移（ALTER TABLE 加的列在 SQLite 里只能是
    # 可空或带常量默认值），DAO 读取时统一走 normalize 兜底。
    cache_limit_bytes = Column(
        Integer, nullable=True, default=DEFAULT_CACHE_LIMIT_BYTES
    )
    min_free_disk_bytes = Column(
        Integer, nullable=True, default=DEFAULT_MIN_FREE_DISK_BYTES
    )
    circuit_breaker_threshold = Column(
        Integer, nullable=True, default=DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    )
    active_provider_id = Column(String, nullable=True)
    active_model_name = Column(String, nullable=True)
