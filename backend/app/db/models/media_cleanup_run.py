from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.engine import Base


class MediaCleanupRun(Base):
    __tablename__ = "media_cleanup_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_types = Column(String(128), nullable=False)
    expired_only = Column(Boolean, nullable=False)
    deleted = Column(Integer, nullable=False, default=0)
    missing = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    bytes_freed = Column(Integer, nullable=False, default=0)
    requested = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime, nullable=False)
