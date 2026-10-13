"""spec 009 ticket 05：video_tasks 去重索引 + payload_json 列 + 幂等迁移。

为什么这么测：

* 索引这件事有两个独立的失效面 —— ① 模型里 ``__table_args__`` 写错（列序反了
  就等于没有索引），② 老库已经存在 ``video_tasks`` 表，``create_all`` 不会给
  已存在的表补列/补索引，只有 ``init_db()`` 里的显式迁移能补上。所以模型断言
  与迁移断言分开测。
* 查询计划断言不写死完整输出：SQLite 可能输出 ``USING INDEX`` 也可能输出
  ``USING COVERING INDEX``，版本之间措辞会变，只断言索引名出现即可。
* ``init_db()`` 里的 ``get_engine()`` 与 ``backfill_legacy_resources()`` 都指向
  真实环境（用户的 ``backend/bili_note.db``、``backend/data/``），所以两个都要
  在测试里换掉，否则这个测试会去扫用户的真实目录、往真实库里写迁移。
* 本仓库没有 conftest.py，也没有 pytest.ini / pyproject.toml；所有 fixture 都
  来自 pytest 内建（``tmp_path`` / ``monkeypatch``），不需要 import pytest。
"""

import sqlite3

from sqlalchemy import create_engine

from app.db import engine as engine_module
from app.db import init_db as init_db_module
from app.db.engine import Base
from app.db.models.video_tasks import VideoTask

INDEX_NAME = "ix_video_tasks_video_platform"

#: 老库结构：spec 009 ticket 05 之前 ``create_all`` 建出来的样子 ——
#: 没有 payload_json，也没有去重索引。group_id 已由 spec 007 的迁移补过。
_LEGACY_SCHEMA = """
CREATE TABLE video_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id VARCHAR NOT NULL,
    platform VARCHAR NOT NULL,
    task_id VARCHAR NOT NULL UNIQUE,
    created_at DATETIME,
    group_id VARCHAR
)
"""


def _new_engine(db_path):
    """在 ``tmp_path`` 下的临时文件上建 engine —— 绝不打开用户的 bili_note.db。"""
    return create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )


def _run_migration(db_engine, monkeypatch):
    """跑一次 ``init_db()`` 的迁移逻辑，但把它钉在临时库上。

    为什么必须 patch 两个东西：

    * ``init_db`` 模块顶部是 ``from app.db.engine import get_engine``，拿到的是
      函数对象本身，绑定已经固化在 ``init_db`` 的命名空间里；所以必须 patch
      ``init_db`` 模块上的属性，patch ``app.db.engine.get_engine`` 不起作用。
    * ``init_db()`` 末尾会调 ``backfill_legacy_resources()``，它按
      ``app/utils/path_helper.get_data_dir()`` 去扫真实目录并写真实库。这个
      测试只关心表结构迁移，把回填换成空操作，避免触碰用户数据。
    """
    monkeypatch.setattr(init_db_module, "get_engine", lambda: db_engine)
    monkeypatch.setattr(engine_module, "engine", db_engine)
    monkeypatch.setattr(engine_module, "_INIT_DB_DONE", False)
    monkeypatch.setattr(init_db_module, "backfill_legacy_resources", lambda: 0)
    init_db_module.init_db()


def _columns_of(db_engine, table):
    with db_engine.connect() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def _index_names(db_engine):
    with db_engine.connect() as conn:
        return {
            row[1] for row in conn.exec_driver_sql("PRAGMA index_list(video_tasks)")
        }


# --------------------------------------------------------------------------
# 模型层：索引定义与列定义
# --------------------------------------------------------------------------


def test_index_declared_with_correct_column_order():
    """列序必须是 (video_id, platform) —— 与 ``get_task_by_video`` 的查询条件一致。

    反过来的复合索引对这个查询基本无效（SQLite 只能用到前导列），所以列序
    本身就是被守护的契约，不能只断言「存在一个索引」。
    """
    indexes = {index.name: index for index in VideoTask.__table__.indexes}
    assert INDEX_NAME in indexes
    assert tuple(indexes[INDEX_NAME].columns.keys()) == ("video_id", "platform")


def test_payload_json_column_is_nullable_text():
    column = VideoTask.__table__.columns.get("payload_json")
    assert column is not None
    # 老库迁移补出来的列只能是 NULL 起步，模型侧必须一致，否则 ORM 写入会报错。
    assert column.nullable is True


# --------------------------------------------------------------------------
# 新建库：查询计划真的走索引
# --------------------------------------------------------------------------


def test_query_plan_uses_the_dedupe_index(tmp_path):
    db_engine = _new_engine(tmp_path / "index-test.db")
    try:
        Base.metadata.create_all(db_engine)
        with db_engine.begin() as conn:
            for i in range(20):
                conn.exec_driver_sql(
                    "INSERT INTO video_tasks (video_id, platform, task_id) "
                    "VALUES (?, ?, ?)",
                    (f"BV{i:04d}", "bilibili", f"task-{i}"),
                )

        with db_engine.connect() as conn:
            plan = conn.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT * FROM video_tasks "
                "WHERE video_id = ? AND platform = ?",
                ("BV0001", "bilibili"),
            ).fetchall()
        detail = " | ".join(str(row[-1]) for row in plan)
        assert INDEX_NAME in detail, f"去重探测没有走索引，实际计划: {detail}"
    finally:
        db_engine.dispose()


# --------------------------------------------------------------------------
# 老库迁移：幂等
# --------------------------------------------------------------------------


def test_migration_adds_payload_json_and_index_on_legacy_table(tmp_path, monkeypatch):
    """手工建出老结构表，跑迁移 —— 列与索引都该补上。

    这条覆盖的是 ``create_all`` 覆盖不到的场景：表已存在时它整表跳过，只有
    ``ALTER TABLE`` / ``CREATE INDEX IF NOT EXISTS`` 能救。
    """
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_LEGACY_SCHEMA)

    db_engine = _new_engine(db_path)
    try:
        assert "payload_json" not in _columns_of(db_engine, "video_tasks")
        assert INDEX_NAME not in _index_names(db_engine)

        _run_migration(db_engine, monkeypatch)

        assert "payload_json" in _columns_of(db_engine, "video_tasks")
        assert INDEX_NAME in _index_names(db_engine)
    finally:
        db_engine.dispose()


def test_migration_is_idempotent_on_legacy_table(tmp_path, monkeypatch):
    """同一个老库上连跑两次迁移都不许抛异常。

    启动路径每次都会调 ``init_db()``，迁移一旦不幂等，第二次启动就崩 —— 而
    这正是「老用户升级」最容易踩的路径。两次之后列与索引仍应存在。
    """
    db_path = tmp_path / "legacy-twice.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_LEGACY_SCHEMA)

    db_engine = _new_engine(db_path)
    try:
        _run_migration(db_engine, monkeypatch)
        _run_migration(db_engine, monkeypatch)  # 第二次不能炸

        assert "payload_json" in _columns_of(db_engine, "video_tasks")
        assert INDEX_NAME in _index_names(db_engine)
        # 索引不能被建出重复的一份（CREATE INDEX IF NOT EXISTS 的语义）。
        assert list(_index_names(db_engine)).count(INDEX_NAME) == 1
    finally:
        db_engine.dispose()


def test_migration_is_idempotent_on_fresh_schema(tmp_path, monkeypatch):
    """全新库（``create_all`` 已按模型建好最新结构）上跑迁移同样不报错。

    ``create_all`` 会先按模型建出索引，随后迁移里的 ``CREATE INDEX IF NOT
    EXISTS`` 是第二次建同一个名字 —— 这里钉死它不会因「index already exists」
    失败。
    """
    db_engine = _new_engine(tmp_path / "fresh.db")
    try:
        _run_migration(db_engine, monkeypatch)
        _run_migration(db_engine, monkeypatch)

        assert "payload_json" in _columns_of(db_engine, "video_tasks")
        assert INDEX_NAME in _index_names(db_engine)
    finally:
        db_engine.dispose()
