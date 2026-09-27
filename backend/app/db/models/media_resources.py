from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class MediaResource(Base):
    __tablename__ = "media_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_type = Column(String(24), nullable=False, index=True)
    task_id = Column(String(128), nullable=True, index=True)
    video_id = Column(String(256), nullable=True, index=True)
    path = Column(String(1024), nullable=False, unique=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=True, index=True)
    source = Column(String(32), nullable=False, default="generated")
    delete_state = Column(String(24), nullable=False, default="active")
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
