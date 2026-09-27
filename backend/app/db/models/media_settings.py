from sqlalchemy import Column, Integer
from app.db.engine import Base


class MediaSettings(Base):
    __tablename__ = "media_settings"

    id = Column(Integer, primary_key=True, default=1)
    screenshot_retention_days = Column(Integer, nullable=False, default=7)
    media_retention_days = Column(Integer, nullable=False, default=3)
