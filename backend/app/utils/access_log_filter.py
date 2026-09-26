import logging
import re


_TASK_STATUS_PATH = re.compile(r"\"(?:GET|HEAD) /api/task_status/[^\s?]+(?:\?[^\s]*)? HTTP/[^\"]+\" (\d{3})")


class TaskStatusAccessLogFilter(logging.Filter):
    """Hide successful task-status polling while retaining errors and other routes."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        message = record.getMessage()
        match = _TASK_STATUS_PATH.search(message)
        if not match:
            return True
        return not 200 <= int(match.group(1)) < 300


def install_task_status_access_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    access_filter = TaskStatusAccessLogFilter()
    logger.addFilter(access_filter)
    for handler in logger.handlers:
        handler.addFilter(access_filter)
