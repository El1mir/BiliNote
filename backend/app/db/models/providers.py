from sqlalchemy import Column, String, Integer, DateTime, func

from app.db.engine import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    logo = Column(String, nullable=False)
    type = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    enabled = Column(Integer, default=1)
    # spec 007：供应商级限流。同一家供应商的所有笔记任务共享这两个额度，
    # 避免一个任务被拆成几十个分块请求后把对方打到 429。
    # 默认 4 并发 / 600 RPM（等于不限速，保持升级前行为）。
    max_concurrency = Column(Integer, nullable=False, default=4)
    max_rpm = Column(Integer, nullable=False, default=600)
    created_at = Column(DateTime, server_default=func.now())
