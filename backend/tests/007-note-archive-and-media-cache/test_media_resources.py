from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.media_resources import MediaResource
from app.db.models.media_settings import MediaSettings
from app.db.models.media_cleanup_run import MediaCleanupRun
from app.services import media_resource_service as service


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    db_engine = create_engine(f"sqlite:///{tmp_path / 'media-test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(service, 'SessionLocal', factory)
    data_root = tmp_path / 'data'
    shots_root = tmp_path / 'shots'
    data_root.mkdir()
    shots_root.mkdir()
    monkeypatch.setattr(service, '_roots', lambda: {'screenshot': shots_root, 'audio': data_root, 'video': data_root})
    return factory, shots_root, data_root


def test_retention_is_fixed_when_resource_is_registered(media_env):
    factory, shots, _ = media_env
    service.set_retention_settings(7, 3)
    path = shots / 'shot.jpg'
    path.write_bytes(b'abc')
    created = datetime(2025, 1, 1)
    service.register_resource('screenshot', path, task_id='task', created_at=created)
    service.set_retention_settings(1, 1)
    with factory() as db:
        row = db.query(MediaResource).one()
        assert row.expires_at == created + timedelta(days=7)
        assert row.task_id == 'task'


def test_zero_days_disables_expiration_and_backfill_uses_mtime(media_env):
    factory, shots, _ = media_env
    service.set_retention_settings(0, 3)
    path = shots / 'legacy.png'
    path.write_bytes(b'legacy')
    old = datetime.now() - timedelta(days=12)
    import os
    os.utime(path, (old.timestamp(), old.timestamp()))
    assert service.backfill_legacy_resources() == 1
    with factory() as db:
        row = db.query(MediaResource).one()
        assert row.expires_at is None
        assert row.source == 'legacy_backfill'
        assert abs((row.created_at - old).total_seconds()) < 1


def test_cleanup_preview_execution_audit_and_path_guard(media_env):
    factory, shots, _ = media_env
    service.set_retention_settings(1, 3)
    path = shots / 'old.jpg'
    path.write_bytes(b'oldbytes')
    service.register_resource('screenshot', path, created_at=datetime.now() - timedelta(days=3))
    with factory() as db:
        row = db.query(MediaResource).one()
        row.path = 'screenshot:../outside.jpg'
        db.commit()
    preview = service.preview_cleanup(['screenshot'], expired_only=True)
    assert preview['count'] == 1
    report = service.cleanup_resources(['screenshot'], expired_only=True, limit=10)
    assert report['failed'] == 1
    assert path.exists()
    with factory() as db:
        row = db.query(MediaResource).one()
        assert row.delete_state == 'failed'
        assert 'escaped root' in row.last_error
        audit = db.query(MediaCleanupRun).one()
        assert audit.failed == 1


def test_cleanup_deletes_expired_and_leaves_unexpired(media_env):
    factory, shots, _ = media_env
    service.set_retention_settings(7, 3)
    expired = shots / 'expired.jpg'
    current = shots / 'current.jpg'
    expired.write_bytes(b'gone')
    current.write_bytes(b'stay')
    service.register_resource('screenshot', expired, created_at=datetime.now() - timedelta(days=10))
    service.register_resource('screenshot', current)
    report = service.cleanup_resources(['screenshot'], expired_only=True)
    assert report['deleted'] == 1
    assert not expired.exists()
    assert current.exists()
    assert len(service.get_recent_cleanup_runs()) == 1
