import logging
import os

from sqlalchemy import inspect, text

from app.db.models.media_resources import MediaResource  # noqa: F401
from app.db.models.media_settings import MediaSettings  # noqa: F401
from app.db.models.media_cleanup_run import MediaCleanupRun  # noqa: F401
from app.db.models.general_settings import GeneralSettings  # noqa: F401
from app.db.models.note_groups import NoteGroup  # noqa: F401
from app.services.media_resource_service import backfill_legacy_resources

logger = logging.getLogger(__name__)

from app.db.models.models import Model  # noqa: F401
from app.db.models.providers import Provider  # noqa: F401
from app.db.models.video_tasks import VideoTask  # noqa: F401
from app.db.engine import get_engine, Base


def _columns(connection, table: str) -> set:
    try:
        return {column["name"] for column in inspect(connection).get_columns(table)}
    except Exception:
        # 表还不存在（create_all 之前的老库），当成空集合
        return set()


def init_db():
    from app.db import engine as engine_module

    if engine_module._INIT_DB_DONE:
        return
    engine = get_engine()

    # spec 022 D4：启动时把统一数据根打进日志，并提示旧版 data/data 残留。
    # 不自动迁移历史文件——迁移会改写用户数据，必须由人决定。
    from app.utils.path_helper import get_data_dir

    data_root = get_data_dir()
    logger.info("媒体数据根目录（DATA_DIR）：%s", data_root)
    legacy_root = os.path.join(data_root, "data")
    try:
        legacy_entries = os.listdir(legacy_root) if os.path.isdir(legacy_root) else []
    except OSError:
        legacy_entries = []
    if legacy_entries:
        logger.warning(
            "检测到旧版数据目录 %s 非空（%d 项）；spec 022 不自动迁移，"
            "需要时请手动把文件移入 %s",
            legacy_root,
            len(legacy_entries),
            data_root,
        )

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        # Idempotent additive migration for older SQLite installations.
        with engine.begin() as connection:
            columns = _columns(connection, "media_resources")
            if "delete_state" not in columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE media_resources ADD COLUMN delete_state VARCHAR(24) NOT NULL DEFAULT 'active'"
                    )
                )
            run_columns = _columns(connection, "media_cleanup_runs")
            if "requested" not in run_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE media_cleanup_runs ADD COLUMN requested INTEGER NOT NULL DEFAULT 0"
                    )
                )

            # spec 007：任务分组归属。create_all 只建新表，不给已存在的表加列，
            # 所以老库（已经有 video_tasks）必须在这里补 group_id。
            task_columns = _columns(connection, "video_tasks")
            if "group_id" not in task_columns:
                connection.execute(
                    text("ALTER TABLE video_tasks ADD COLUMN group_id VARCHAR")
                )

            # spec 009 决策 8–10：提交时的完整生成参数。重启恢复靠它还原
            # quality/model/provider/screenshot 等参数 —— 没有这一列，恢复出来
            # 的任务只能按默认参数重跑。
            if "payload_json" not in task_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text("ALTER TABLE video_tasks ADD COLUMN payload_json TEXT")
                )

            # spec 009 / ticket 05：去重探测索引。老库的表是之前 create_all 建的，
            # 那时模型里还没有 __table_args__，索引不存在；create_all 不会给已存在
            # 的表补索引，所以在这里显式建一次（IF NOT EXISTS 保证新库上不重复）。
            # pi-lens-ignore: python-sql-injection
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_video_tasks_video_platform "
                    "ON video_tasks (video_id, platform)"
                )
            )

            # spec 009 / ticket 07：通用设置的「缓存边界」三列。
            # 带 DEFAULT 常量，让老库里已有的那一行也能读到合理初值（SQLite 的
            # ADD COLUMN 只接受常量默认值）；NULL 由 DAO 的 normalize 兜底。
            settings_columns = _columns(connection, "general_settings")
            if "cache_limit_bytes" not in settings_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE general_settings ADD COLUMN cache_limit_bytes "
                        "INTEGER DEFAULT 10737418240"
                    )
                )
            if "min_free_disk_bytes" not in settings_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE general_settings ADD COLUMN min_free_disk_bytes "
                        "INTEGER DEFAULT 5368709120"
                    )
                )
            if "circuit_breaker_threshold" not in settings_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE general_settings ADD COLUMN circuit_breaker_threshold "
                        "INTEGER DEFAULT 5"
                    )
                )
            # Additive migration for globally active LLM selection.
            settings_columns = _columns(connection, "general_settings")
            if "active_provider_id" not in settings_columns:
                connection.execute(
                    text("ALTER TABLE general_settings ADD COLUMN active_provider_id VARCHAR")
                )
            if "active_model_name" not in settings_columns:
                connection.execute(
                    text("ALTER TABLE general_settings ADD COLUMN active_model_name VARCHAR")
                )
            # 2026-10-17：ASR 输入上限 / 静音拆分 / LLM 请求体预算 / OCR 阶段参数。
            # 老库里的 general_settings 只有 4 个可调列，这里逐列补。常量默认值与
            # app/db/models/general_settings.py 里的 DEFAULT_* 必须一致 —— 两处不一致
            # 会让「新库」和「迁移过来的老库」行为不同。
            settings_columns = _columns(connection, "general_settings")
            _settings_additions = (
                ("asr_max_file_mb", "INTEGER DEFAULT 0"),
                ("asr_max_duration_minutes", "INTEGER DEFAULT 0"),
                ("asr_silence_split", "INTEGER DEFAULT 1"),
                ("asr_silence_noise_db", "FLOAT DEFAULT -30.0"),
                ("asr_min_silence_seconds", "FLOAT DEFAULT 0.5"),
                ("llm_max_request_bytes", "INTEGER DEFAULT 9437184"),
                ("llm_judge_image_budget_bytes", "INTEGER DEFAULT 3145728"),
                ("llm_retry_attempts", "INTEGER DEFAULT 3"),
                ("llm_retry_backoff_seconds", "FLOAT DEFAULT 1.5"),
                ("ocr_stage_concurrency", "INTEGER DEFAULT 4"),
                ("note_max_images", "INTEGER DEFAULT 30"),
                # 第二轮：失败预算（任务重试 / 429 冷却 / 下载重试）。
                ("note_max_retries", "INTEGER DEFAULT 3"),
                ("note_retry_backoff_seconds", "FLOAT DEFAULT 5.0"),
                ("llm_rate_limit_cooldown_seconds", "FLOAT DEFAULT 300.0"),
                ("llm_rate_limit_max_wait_seconds", "FLOAT DEFAULT 3600.0"),
                ("llm_rate_limit_resume_interval_seconds", "FLOAT DEFAULT 300.0"),
                ("download_retries", "INTEGER DEFAULT 3"),
                ("download_socket_timeout_seconds", "INTEGER DEFAULT 30"),
                # 第三轮：截图编码与 ffmpeg 超时（决定单图字节数 = 一次请求能带几张图）。
                ("screenshot_max_width", "INTEGER DEFAULT 0"),
                ("screenshot_quality", "INTEGER DEFAULT 2"),
                ("ffmpeg_timeout_seconds", "INTEGER DEFAULT 60"),
                ("ocr_max_judge_candidates", "INTEGER DEFAULT 200"),
                # 2026-10-05（spec 005 ticket 11）：用户自定义 BASE_PROMPT 覆盖层。
                # 空的 TEXT 列，NULL 表示「用内置模板」。
                ("base_prompt_override", "TEXT"),
            )
            for _column, _ddl in _settings_additions:
                if _column in settings_columns:
                    continue
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(f"ALTER TABLE general_settings ADD COLUMN {_column} {_ddl}")
                )
            # spec 007：供应商级并发量与每分钟请求数。
            provider_columns = _columns(connection, "providers")
            if "max_concurrency" not in provider_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE providers ADD COLUMN max_concurrency INTEGER NOT NULL DEFAULT 4"
                    )
                )
            if "max_rpm" not in provider_columns:
                # pi-lens-ignore: python-sql-injection
                connection.execute(
                    text(
                        "ALTER TABLE providers ADD COLUMN max_rpm INTEGER NOT NULL DEFAULT 600"
                    )
                )

            # spec 007：note_groups 结构对账。
            #
            # 这里不能只补列，必须整表重建：早前一轮未落库的分组试验已经用同名
            # 表建过 note_groups，但结构完全不同（id VARCHAR(36)、name
            # VARCHAR(120)，外加 is_system / updated_at，且没有 position）。
            # create_all 只建缺失的表，遇到同名表直接跳过，所以老的残缺结构会
            # 一直留着；而 ORM 生成的每个查询都带 position：
            #     no such column: note_groups.position
            # 结果是 list_groups / create_group / rename_group 全部 OperationalError。
            #
            # 重建是安全的：这两套结构没有任何一处共用的迁移语义（position 在
            # 老表里根本不存在，无法 ALTER 出来并保住排序），而老表实测 0 行；
            # 源码里也没有任何地方引用 is_system 或 updated_at。
            # 这里仍然先数行数，只有在确实是空表时才重建 —— 万一将来有人已经
            # 往老表里存了数据，宁可让 note_group_dao 报错，也不能静默丢数据。
            group_columns = _columns(connection, "note_groups")
            if group_columns and "position" not in group_columns:
                rows = connection.execute(
                    text("SELECT count(*) FROM note_groups")
                ).scalar()
                if rows:
                    logger.warning(
                        "note_groups 是老结构（缺 position）但已有 %s 行数据，"
                        "不自动重建；请人工决定是迁移还是清空",
                        rows,
                    )
                else:
                    connection.execute(text("DROP TABLE note_groups"))
                    NoteGroup.__table__.create(bind=connection)
    engine_module._INIT_DB_DONE = True
    inserted = backfill_legacy_resources()
    logger.info("媒体资源历史回填完成：新增 %d 条", inserted)
