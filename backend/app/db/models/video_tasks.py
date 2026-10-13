from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func

from app.db.engine import Base


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    task_id = Column(String, unique=True, nullable=False)
    # 所属分组（spec 007）；NULL = 未分组。不设外键：任务记录在媒体清理时可能
    # 先被删掉，加外键会让清理因为悬垂引用整批失败；组被删时由 DAO 显式置空。
    group_id = Column(String, nullable=True)
    # 提交时的完整生成参数 JSON（spec 009 决策 8–10）。
    #
    # 为什么必须存：进程重启后要自动把中断的在途任务重新排队，而重新排队就得
    # 知道当初用的是什么参数 —— quality / model_name / provider_id / screenshot
    # / link / format / style / extras 等。``<task_id>.status.json`` 里只有进度
    # 字段（status/stage/progress/...），一个生成参数都没有；光靠 video_tasks
    # 原有的四列也无从还原。没有这一列，恢复出来的任务只能用默认参数重跑，
    # 用户精心选的模型和画质会静默丢失。
    #
    # 用 Text 而不是 JSON 类型：SQLite 对 JSON 列没有原生支持，且参数结构未来
    # 可能增删字段，存字符串更宽容。反序列化失败按「无参数」处理（回落默认）。
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # 去重探测索引（spec 009 / ticket 05）。
    #
    # ``get_task_by_video(video_id, platform)`` 是高频调用：批量展开时每个分 P
    # 都要查一次「这个视频是不是已经有任务了」。以前没有索引，每次都是全表扫
    # —— 任务表攒到几千行之后，展开一个 100 分 P 的视频就是 100 次全表扫。
    # 复合索引的列序与查询条件一致（video_id 在前、platform 在后），能直接命中。
    __table_args__ = (Index("ix_video_tasks_video_platform", "video_id", "platform"),)
