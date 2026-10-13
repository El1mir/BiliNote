"""容量边界清理的行为验收（spec 007 §12 / spec 009 ticket 07）。

覆盖 ticket 里点名的几条硬要求：

* 「终态即清」——只有 SUCCESS / FAILED 任务的资源可删；活跃（PENDING..
  SAVING）与**状态文件缺失**的任务一律跳过；
* 超限时**最旧优先**删到上限的 `_CACHE_LOW_WATER_RATIO`（90%）以下；
* `cache_limit_bytes == 0` 是彻底的 no-op（连扫描都不做）；
* 路径防护不被绕过：非法 `row.path` 必须标 failed 且文件保留。

**绝不触碰用户真实数据**：受管根、状态目录、导出目录、visual_cache 根、temp 根
全部 monkeypatch 到 tmp_path，并把 cwd 也切到 tmp_path（`uploads` 是相对 cwd 的）。
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.media_cleanup_run import MediaCleanupRun
from app.db.models.media_resources import MediaResource
from app.services import media_resource_service as service

# side-effect import：`Base.metadata.create_all` 只建**已经 import 过**的模型，
# 而 media_resource_service 里的 MediaSettings 是函数内惰性导入的，
# 不在这里显式 import 的话建表会漏掉 media_settings，register_resource 直接
# 抛 "no such table"。ruff 会把纯 side-effect import 当未使用删掉，故加 noqa。
import app.db.models.media_settings  # noqa: F401  # isort: skip

MiB = 1024 * 1024


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    """把容量清理会扫到的每一个根都搬到 tmp_path，返回 (factory, shots, status_dir)。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'cache-test.db'}",
        connect_args={"check_same_thread": False},
    )
    # 只建**已 import** 的模型的表；GeneralSettings / MediaSettings 是 side-effect import。
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", factory)

    shots = tmp_path / "shots"
    data_root = tmp_path / "data"
    status_dir = tmp_path / "note_results"
    note_out = tmp_path / "data" / "note_output"
    visual_root = tmp_path / "data" / "visual_cache" / "v1"
    uploads = tmp_path / "uploads"
    temp_root = tmp_path / "temp"
    for path in (
        shots,
        data_root,
        status_dir,
        note_out,
        visual_root,
        uploads,
        temp_root,
    ):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        service,
        "_roots",
        lambda: {"screenshot": shots, "audio": data_root, "video": data_root},
    )
    monkeypatch.setattr(service, "_note_output_dir", lambda: status_dir)
    monkeypatch.setattr(service, "_note_export_dir", lambda: note_out)

    # visual_cache 根走 get_app_dir（函数内 import），必须连模块属性一起换掉，
    # 否则测试会扫到仓库真实的 backend/data/visual_cache 并可能删掉它。
    import app.utils.path_helper as path_helper

    monkeypatch.setattr(path_helper, "get_app_dir", lambda subdir: str(visual_root))

    # ASR 切片扫的是系统 temp；换掉根，避免统计到真实的 asr_speech_* 目录。
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp_root))

    # uploads 是相对 cwd 解析的（Path("uploads")）。
    monkeypatch.chdir(tmp_path)
    return factory, shots, status_dir


def _set_limit(monkeypatch, limit_bytes: int) -> None:
    """把容量上限钉成指定值（设置读取本身由 DAO 用例单独覆盖）。"""
    monkeypatch.setattr(
        service,
        "get_cache_settings",
        lambda: {
            "cache_limit_bytes": limit_bytes,
            "min_free_disk_bytes": 5 * 1024**3,
            "circuit_breaker_threshold": 5,
        },
    )


def _write_status(status_dir: Path, task_id: str, status: str) -> None:
    (status_dir / f"{task_id}.status.json").write_text(
        f'{{"status": "{status}"}}', encoding="utf-8"
    )


def _register(shots: Path, name: str, size: int, task_id: str, days_ago: float):
    path = shots / name
    path.write_bytes(b"x" * size)
    service.register_resource(
        "screenshot",
        path,
        task_id=task_id,
        created_at=datetime.now() - timedelta(days=days_ago),
    )
    return path


def test_only_terminal_tasks_are_deleted_and_oldest_first(cache_env, monkeypatch):
    factory, shots, status_dir = cache_env
    _set_limit(monkeypatch, 2 * MiB)

    # 4 个资源：2 个终态（SUCCESS / FAILED）+ 1 个活跃 + 1 个没有状态文件。
    old = _register(shots, "old.jpg", 2 * MiB, "task_old", 10)  # SUCCESS，最旧
    new = _register(shots, "new.jpg", MiB // 2, "task_new", 2)  # FAILED
    live = _register(shots, "live.jpg", MiB // 2, "task_live", 20)  # DOWNLOADING
    ghost = _register(shots, "ghost.jpg", MiB // 2, "task_ghost", 30)  # 无状态文件

    _write_status(status_dir, "task_old", "SUCCESS")
    _write_status(status_dir, "task_new", "FAILED")
    _write_status(status_dir, "task_live", "DOWNLOADING")
    # task_ghost 刻意不写：状态文件缺失 ⇒ 视为不可清理（保守）。

    # --- dry run：只算不删、不写审计 -----------------------------------------
    preview = service.preview_cache_limit()
    assert preview["dry_run"] is True
    assert preview["enabled"] is True
    assert preview["total_bytes"] == 2 * MiB + 3 * (MiB // 2)
    assert preview["over_limit"] is True
    # 最旧的 old.jpg 一个就够降到低水位以下（target = 90% × 2 MiB）。
    assert preview["would_delete_count"] == 1
    assert preview["would_delete_bytes"] == 2 * MiB
    for path in (old, new, live, ghost):
        assert path.exists(), "dry run 不得删除任何文件"
    with factory() as db:
        assert db.query(MediaCleanupRun).count() == 0

    skipped_paths = {sample["path"] for sample in preview["skipped_samples"]}
    assert str(live) in skipped_paths
    assert str(ghost) in skipped_paths
    assert str(old) not in skipped_paths

    # --- 真正执行 ------------------------------------------------------------
    report = service.enforce_cache_limit()
    assert report["deleted"] == 1
    assert report["bytes_freed"] == 2 * MiB
    assert not old.exists(), "最旧的终态资源应被删除"
    assert new.exists(), "删到低水位以下就该停手"
    assert live.exists(), "活跃任务的资源绝不能删"
    assert ghost.exists(), "状态文件缺失的资源绝不能删"

    with factory() as db:
        remaining = {row.path for row in db.query(MediaResource).all()}
        # 被删资源的登记行随之移除；不可清理的三行原样保留。
        assert not any(path.endswith("old.jpg") for path in remaining)
        assert sum(1 for path in remaining if path.endswith("live.jpg")) == 1
        assert sum(1 for path in remaining if path.endswith("ghost.jpg")) == 1
        audit = db.query(MediaCleanupRun).one()
        # 触发原因靠 resource_types 前缀区分：容量维度固定 "capacity"，
        # 时间维度写 "screenshot,video,audio"。
        assert audit.resource_types == "capacity"
        assert audit.expired_only is False
        assert audit.deleted == 1
        assert audit.bytes_freed == 2 * MiB


def test_deletes_oldest_first_down_to_low_water(cache_env, monkeypatch):
    factory, shots, status_dir = cache_env
    limit = 4 * MiB
    _set_limit(monkeypatch, limit)

    names = ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"]
    paths = []
    for index, name in enumerate(names):
        # 越靠前越旧；每个 1 MiB，总计 6 MiB，上限 4 MiB，低水位 3.6 MiB。
        paths.append(
            _register(shots, name, MiB, f"task_{name[0]}", days_ago=60 - index * 10)
        )
        _write_status(status_dir, f"task_{name[0]}", "SUCCESS")

    report = service.enforce_cache_limit()

    # 6 MiB → 需要删到 ≤ 3.6 MiB：删 3 个（3 MiB）剩 3 MiB，正好过线。
    assert report["deleted"] == 3
    assert report["bytes_freed"] == 3 * MiB
    assert [path.exists() for path in paths] == [False, False, False, True, True, True]
    # 低水位是**上限的 90%**（不是 100%），留出余量避免每轮都刚好踩线。
    assert report["low_water_bytes"] == int(limit * service._CACHE_LOW_WATER_RATIO)
    assert report["total_bytes"] - report["bytes_freed"] <= report["low_water_bytes"]


def test_zero_limit_is_a_complete_noop(cache_env, monkeypatch):
    factory, shots, status_dir = cache_env
    # 0 = 不设上限（spec 007 §12.2）。注意它**不等于**「用默认 10 GiB」。
    _set_limit(monkeypatch, 0)

    path = _register(shots, "kept.jpg", 2 * MiB, "task_kept", 90)
    _write_status(status_dir, "task_kept", "SUCCESS")

    report = service.enforce_cache_limit()
    assert report["enabled"] is False
    assert report["limit_bytes"] == 0
    # 关掉容量维度必须在**扫描之前**返回：统计值保持初始 0，不是「扫了但不删」。
    assert report["total_bytes"] == 0
    assert report["over_limit"] is False
    assert path.exists()
    with factory() as db:
        assert db.query(MediaCleanupRun).count() == 0, "no-op 不该写审计行"


def test_path_guard_is_not_bypassed(cache_env, monkeypatch):
    """容量维度必须与时间维度共用同一套路径防护（复用 `_managed_relative`）。"""
    factory, shots, status_dir = cache_env
    _set_limit(monkeypatch, 1)  # 极小上限，保证一定触发删除

    inside = _register(shots, "inside.jpg", MiB, "task_guard", 10)
    victim = _register(shots, "victim.jpg", MiB, "task_victim", 20)
    _write_status(status_dir, "task_guard", "SUCCESS")
    _write_status(status_dir, "task_victim", "SUCCESS")

    outside = shots.parent / "outside.jpg"
    outside.write_bytes(b"y" * MiB)
    with factory() as db:
        # 只把 victim 那一行的登记键改成逃出受管根的形式（与 007 的时间维度用例
        # 同一手法）；inside 保持合法，用来验证「一个坏行不会连累好行」。
        # pi-lens-ignore: python-sql-injection
        row = db.query(MediaResource).filter_by(task_id="task_victim").one()
        row.path = "screenshot:../outside.jpg"
        db.commit()

    report = service.enforce_cache_limit()

    assert report["failed"] >= 1
    assert outside.exists(), "越界文件绝不能被删除"
    with factory() as db:
        # pi-lens-ignore: python-sql-injection
        row = db.query(MediaResource).one()
        assert row.delete_state == "failed"
        assert "outside its managed root" in row.last_error
    # 合法的那一个仍然按容量维度被回收。
    assert not inside.exists()
