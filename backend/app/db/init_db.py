from sqlalchemy import inspect, text
from app.db.models.media_resources import MediaResource
from app.db.models.media_settings import MediaSettings
from app.db.models.media_cleanup_run import MediaCleanupRun
from app.services.media_resource_service import backfill_legacy_resources

from app.db.models.models import Model
from app.db.models.providers import Provider
from app.db.models.video_tasks import VideoTask
from app.db.engine import get_engine, Base

def init_db():
    engine = get_engine()

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        # Idempotent additive migration for older SQLite installations.
        with engine.begin() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("media_resources")}
            if "delete_state" not in columns:
                connection.execute(text("ALTER TABLE media_resources ADD COLUMN delete_state VARCHAR(24) NOT NULL DEFAULT 'active'"))
            run_columns = {column["name"] for column in inspect(connection).get_columns("media_cleanup_runs")}
            if "requested" not in run_columns:
                connection.execute(text("ALTER TABLE media_cleanup_runs ADD COLUMN requested INTEGER NOT NULL DEFAULT 0"))
    backfill_legacy_resources()