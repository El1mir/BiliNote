"""通用设置里三个缓存边界字段的归一化 / 默认值 / 0 语义（spec 009 ticket 07）。

这个 DAO 的读路径决定媒体清理（`cache_limit_bytes`）、磁盘门禁
（`min_free_disk_bytes`）和熔断（`circuit_breaker_threshold`）的行为，所以
三条硬要求必须钉住：

* **0 是有意义的取值**，不是「没设置」——`cache_limit_bytes=0` 表示不限缓存、
  `circuit_breaker_threshold=0` 表示关闭熔断，都必须原样保留；
* **负数是无效输入**，一律回落默认值；`min_free_disk_bytes` 尤其不能把负数当
  0（那等于把保护静默关掉）；
* **读库失败回落默认值**，绝不抛异常（否则整个设置页 500、生成入口也挂）。

**不碰真实数据库**：把 `get_db` 换成指向 tmp_path 里临时 SQLite 的会话。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import general_settings_dao as dao
from app.db.engine import Base
from app.db.models.general_settings import (
    DEFAULT_CACHE_LIMIT_BYTES,
    DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
    DEFAULT_MIN_FREE_DISK_BYTES,
    MAX_CACHE_LIMIT_BYTES,
    GeneralSettings,
)

GiB = 1024**3


@pytest.fixture
def dao_env(tmp_path, monkeypatch):
    """把 DAO 的 `get_db` 换成临时 SQLite 的会话工厂。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'general-test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    def _fake_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(dao, "get_db", _fake_get_db)
    return factory


# --- 纯函数归一化：不碰数据库，先把语义钉死 ---------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0),  # 0 = 不限缓存，必须原样保留
        (5 * GiB, 5 * GiB),
        (-1, DEFAULT_CACHE_LIMIT_BYTES),  # 负数无效，回落默认
        (-1024, DEFAULT_CACHE_LIMIT_BYTES),
        (None, DEFAULT_CACHE_LIMIT_BYTES),  # 老库 NULL
        ("abc", DEFAULT_CACHE_LIMIT_BYTES),
        (MAX_CACHE_LIMIT_BYTES * 10, MAX_CACHE_LIMIT_BYTES),  # 封顶
        ("1073741824", GiB),  # 字符串数字可解析
    ],
)
def test_normalize_cache_limit_bytes(raw, expected):
    assert dao.normalize_cache_limit_bytes(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0),  # 0 = 不做磁盘门禁
        (2 * GiB, 2 * GiB),
        # 关键：负数**不能**被当成 0，否则手滑输错会把保护静默关掉。
        (-1, DEFAULT_MIN_FREE_DISK_BYTES),
        (None, DEFAULT_MIN_FREE_DISK_BYTES),
        ("xyz", DEFAULT_MIN_FREE_DISK_BYTES),
    ],
)
def test_normalize_min_free_disk_bytes(raw, expected):
    assert dao.normalize_min_free_disk_bytes(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0),  # 0 = 关闭熔断
        (12, 12),
        (-1, DEFAULT_CIRCUIT_BREAKER_THRESHOLD),
        (None, DEFAULT_CIRCUIT_BREAKER_THRESHOLD),
        ("nope", DEFAULT_CIRCUIT_BREAKER_THRESHOLD),
    ],
)
def test_normalize_circuit_breaker_threshold(raw, expected):
    assert dao.normalize_circuit_breaker_threshold(raw) == expected


# --- 读路径：默认值 + 老库 NULL + 读失败兜底 --------------------------------


def test_first_read_returns_defaults(dao_env):
    payload = dao.get_general_settings()
    assert payload["cache_limit_bytes"] == DEFAULT_CACHE_LIMIT_BYTES
    assert payload["min_free_disk_bytes"] == DEFAULT_MIN_FREE_DISK_BYTES
    assert payload["circuit_breaker_threshold"] == DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    # 每个字段都带上 default / limit，前端不用把常量再抄一遍。
    assert payload["cache_limit_bytes_default"] == DEFAULT_CACHE_LIMIT_BYTES
    assert payload["cache_limit_bytes_limit"] == MAX_CACHE_LIMIT_BYTES


def test_null_columns_fall_back_to_defaults(dao_env):
    """老库迁移过来的行这三列是 NULL（ALTER TABLE 只能加可空列）。

    注意要在 **UPDATE** 时置 NULL：INSERT 时这三列带 `default=`，SQLAlchemy 会
    自动填上默认值，测不出真正的 NULL 路径。
    """
    with dao_env() as db:
        db.add(GeneralSettings(id=1, max_parallel_notes=3))
        db.commit()
        # pi-lens-ignore: python-sql-injection
        row = db.query(GeneralSettings).filter_by(id=1).one()
        row.cache_limit_bytes = None
        row.min_free_disk_bytes = None
        row.circuit_breaker_threshold = None
        db.commit()
    payload = dao.get_general_settings()
    assert payload["cache_limit_bytes"] == DEFAULT_CACHE_LIMIT_BYTES
    assert payload["min_free_disk_bytes"] == DEFAULT_MIN_FREE_DISK_BYTES
    assert payload["circuit_breaker_threshold"] == DEFAULT_CIRCUIT_BREAKER_THRESHOLD


def test_read_failure_returns_defaults_without_raising(dao_env, monkeypatch):
    def _boom(_db):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(dao, "_get_or_create", _boom)
    payload = dao.get_general_settings()  # 不得抛
    assert payload["cache_limit_bytes"] == DEFAULT_CACHE_LIMIT_BYTES
    assert payload["min_free_disk_bytes"] == DEFAULT_MIN_FREE_DISK_BYTES
    assert payload["circuit_breaker_threshold"] == DEFAULT_CIRCUIT_BREAKER_THRESHOLD


# --- 写路径：0 保留、负数回落、部分更新不误伤其他字段 ------------------------


def test_update_preserves_zero_and_rejects_negative(dao_env):
    payload = dao.update_general_settings(
        cache_limit_bytes=0,
        circuit_breaker_threshold=0,
        min_free_disk_bytes=-1,  # 无效输入 ⇒ 回落默认，而不是 0
    )
    assert payload["cache_limit_bytes"] == 0, "0 必须原样落库（不限缓存）"
    assert payload["circuit_breaker_threshold"] == 0, "0 必须原样落库（关闭熔断）"
    assert payload["min_free_disk_bytes"] == DEFAULT_MIN_FREE_DISK_BYTES

    # 再读一次确认真的写进去了，不是只在返回值里。
    again = dao.get_general_settings()
    assert again["cache_limit_bytes"] == 0
    assert again["circuit_breaker_threshold"] == 0


def test_partial_update_leaves_other_fields_alone(dao_env):
    dao.update_general_settings(cache_limit_bytes=3 * GiB, min_free_disk_bytes=2 * GiB)
    # 只传并行度：另外两个缓存字段必须保持原值，不能被重置成默认。
    payload = dao.update_general_settings(max_parallel_notes=5)
    assert payload["max_parallel_notes"] == 5
    assert payload["cache_limit_bytes"] == 3 * GiB
    assert payload["min_free_disk_bytes"] == 2 * GiB
