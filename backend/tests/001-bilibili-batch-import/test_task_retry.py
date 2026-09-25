"""ticket 04：任务级自动重试（首次 + 3 次重试）。"""
from types import SimpleNamespace
from unittest import mock

from app.routers import note as note_module


def _run_with(execute, generator):
    with mock.patch.object(note_module, "NOTE_RETRY_BACKOFF", [0, 0, 0]), \
         mock.patch.object(note_module, "task_serial_executor") as executor:
        executor.run.side_effect = lambda fn: fn()
        return note_module._execute_note_with_retry("t1", generator, execute)


def test_retries_then_succeeds():
    calls = []

    def execute():
        calls.append(1)
        return None if len(calls) < 3 else SimpleNamespace(markdown="ok")

    generator = mock.Mock()
    result = _run_with(execute, generator)

    assert result.markdown == "ok"
    assert len(calls) == 3           # 首次失败 + 第 1、2 次重试后成功
    assert generator._update_status.call_count == 2


def test_gives_up_after_three_retries():
    calls = []

    def execute():
        calls.append(1)
        return None

    generator = mock.Mock()
    result = _run_with(execute, generator)

    assert result is None
    assert len(calls) == 4           # 首次 + 3 次重试
    assert generator._update_status.call_count == 3


def test_empty_markdown_counts_as_failure():
    calls = []

    def execute():
        calls.append(1)
        return SimpleNamespace(markdown="")

    generator = mock.Mock()
    result = _run_with(execute, generator)

    assert result is None
    assert len(calls) == 4
