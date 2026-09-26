import logging

from app.utils.access_log_filter import TaskStatusAccessLogFilter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_successful_task_status_polling_is_filtered():
    record = _record(
        '127.0.0.1:1234 - "GET /api/task_status/abc?x=1 HTTP/1.1" 200 OK'
    )
    assert TaskStatusAccessLogFilter().filter(record) is False


def test_failed_task_status_request_is_kept():
    record = _record(
        '127.0.0.1:1234 - "GET /api/task_status/abc HTTP/1.1" 500 Internal Server Error'
    )
    assert TaskStatusAccessLogFilter().filter(record) is True


def test_other_routes_are_kept():
    record = _record('127.0.0.1:1234 - "GET /api/models HTTP/1.1" 200 OK')
    assert TaskStatusAccessLogFilter().filter(record) is True
