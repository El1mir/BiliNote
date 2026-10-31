"""spec 005 ticket 13：日志统一。

历史问题：`app/services/note.py` 用裸 `logging.getLogger(__name__)`（没有 handler），
于是所有 INFO（GPT 总结成功 / 已保存任务记录 / 笔记生成成功）被静默丢弃，
只有 WARNING/ERROR 通过 logging.lastResort 打到 stderr，且没有时间戳与模块名。
网络排查时看不到任何业务日志，误以为后端卡死。

这里固定：业务模块共用 `app.utils.logger.get_logger`，带 console + app.log 双 handler。
"""
import logging
import pathlib

from app.utils.logger import get_logger

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_get_logger_installs_console_and_file_handlers():
    logger = get_logger("tests.ticket13")

    assert logger.level == logging.INFO
    assert logger.propagate is False

    console = [
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
    ]
    files = [handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)]
    assert console, "缺少控制台 handler"
    assert files, "缺少 app.log handler"
    assert files[0].baseFilename.replace("\\", "/").endswith("logs/app.log")


def test_get_logger_is_idempotent():
    first = get_logger("tests.ticket13.idempotent")
    second = get_logger("tests.ticket13.idempotent")

    assert first is second
    assert len(first.handlers) == 2, "重复调用不能叠加 handler"


def test_business_modules_share_the_configured_logger():
    from app.downloaders import bilibili_dm_patch, bilibili_downloader
    from app.routers import note as note_router
    from app.services import note as note_service

    for module in (note_service, note_router, bilibili_downloader, bilibili_dm_patch):
        logger = module.logger
        assert isinstance(logger, logging.Logger)
        assert logger.name == module.__name__
        assert logger.handlers, f"{module.__name__} 的 logger 没有 handler（INFO 会被静默丢弃）"


def test_downloader_modules_no_longer_use_bare_stdlib_logger():
    for name in ("bilibili_downloader.py", "bilibili_dm_patch.py"):
        source = (ROOT / "app" / "downloaders" / name).read_text(encoding="utf-8")
        assert "logging.getLogger(__name__)" not in source, f"{name} 仍在用无 handler 的 logger"
        assert "get_logger(__name__)" in source
