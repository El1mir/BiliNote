"""T-062 追加：清理预演与执行必须同口径，且预演响应可 JSON 序列化。

回归两个真实缺口：
1. `preview_cleanup` 返回的 `expires_earliest` / `expires_latest` 是 datetime，
   进 JSON 响应时抛 TypeError: Object of type datetime is not JSON serializable ——
   前端点「预览全部受管资源」拿到 500，预演等于不可用（同文件的
   `get_recent_cleanup_runs` 早已按 isoformat 输出）。
2. 预演与执行的作用域必须来自同一个 `expired_only`：预演 expired 却执行全量，
   会让「预演 N 项」与实际删除量对不上，破坏预演作为确认步骤的意义。
"""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.media_resources import MediaResource
from app.db.models.media_settings import MediaSettings  # noqa: F401  建表需要
from app.db.models.media_cleanup_run import MediaCleanupRun  # noqa: F401  建表需要
from app.services import media_resource_service as service


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'cleanup-preview-test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", factory)
    shots = tmp_path / "shots"
    data = tmp_path / "data"
    shots.mkdir()
    data.mkdir()
    monkeypatch.setattr(
        service, "_roots", lambda: {"screenshot": shots, "audio": data, "video": data}
    )
    return factory, shots


def _seed(factory, shots, name, expired):
    """写一个截图文件并登记；expired=True 表示已过保留期。"""
    path = shots / name
    path.write_bytes(b"x" * 100)
    service.register_resource("screenshot", path, task_id="t062")
    now = datetime.now()
    with factory() as db:
        row = db.query(MediaResource).filter(MediaResource.path == f"screenshot:{name}").one()
        row.expires_at = now - timedelta(days=1) if expired else now + timedelta(days=30)
        db.commit()


def test_cleanup_preview_serializes_expiry_timestamps(media_env):
    """预演的时间字段必须是 JSON 可序列化的字符串。"""
    factory, shots = media_env
    _seed(factory, shots, "expired.jpg", expired=True)

    preview = service.preview_cleanup(["screenshot"], expired_only=True)

    json.dumps(preview)  # 修复前这里抛 TypeError
    assert isinstance(preview["expires_earliest"], str)
    assert isinstance(preview["expires_latest"], str)


def test_full_preview_serializes_when_only_future_expiry_exists(media_env):
    """全量预演覆盖未到期资源，时间字段同样必须走 ISO 字符串。"""
    factory, shots = media_env
    _seed(factory, shots, "fresh.jpg", expired=False)

    preview = service.preview_cleanup(["screenshot"], expired_only=False)

    json.dumps(preview)
    assert preview["count"] == 1
    assert preview["expires_earliest"] == preview["expires_latest"]


def test_preview_and_execution_agree_per_scope(media_env):
    """同一作用域下，预演数字必须等于实际删除量。"""
    factory, shots = media_env
    for i in range(2):
        _seed(factory, shots, f"expired-{i}.jpg", expired=True)
    _seed(factory, shots, "fresh.jpg", expired=False)

    expired_preview = service.preview_cleanup(["screenshot"], expired_only=True)
    expired_report = service.cleanup_resources(["screenshot"], expired_only=True)
    assert expired_preview["count"] == expired_report["deleted"] == 2

    all_preview = service.preview_cleanup(["screenshot"], expired_only=False)
    all_report = service.cleanup_resources(["screenshot"], expired_only=False)
    assert all_preview["count"] == all_report["deleted"] == 1


def test_preview_counts_do_not_leak_between_scopes(media_env):
    """两种作用域的数字必须不同：预演「仅到期」不能把未到期资源算进去。"""
    factory, shots = media_env
    _seed(factory, shots, "expired.jpg", expired=True)
    _seed(factory, shots, "fresh.jpg", expired=False)

    assert service.preview_cleanup(["screenshot"], expired_only=True)["count"] == 1
    assert service.preview_cleanup(["screenshot"], expired_only=False)["count"] == 2

