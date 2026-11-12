"""spec 022 W1：合并任务断点续跑（D3）。

第 5 条撞 429（RATE_LIMIT_PARKED）时，前 4 条必须已落 checkpoint；重新派发后
前 4 条不再生成，只跑 5..10，最终 10 条齐全、顺序不变，成功后删除 checkpoint。
"""

import os
from types import SimpleNamespace

import pytest

from app.routers import note as note_module


class _Limit:
    def __init__(self, value):
        self.value = value


@pytest.fixture
def gate_env(monkeypatch):
    holder = _Limit(1)
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    monkeypatch.setattr(note_module, "_safe_max_parallel_notes", lambda: holder.value)
    yield holder
    gate = note_module._PARALLEL_GATE
    if gate is not None:
        assert gate.active == 0, f"用例结束时闸门仍有 {gate.active} 个名额未归还"


class _FakeGenerator:
    def __init__(self, probe=None):
        self._probe = probe

    def _update_status(self, *args, **kwargs):
        return None

    def generate(self, **kwargs):
        url = kwargs["video_url"]
        return SimpleNamespace(
            markdown=f"### {url}",
            transcript=None,
            audio_meta=SimpleNamespace(
                title=url, duration=1.0, video_id=url.rsplit("/", 1)[-1], cover_url=None
            ),
        )


def _items(count):
    return [{"url": f"https://video/{i}", "title": f"标题{i}"} for i in range(1, count + 1)]


def _kwargs(items):
    return dict(
        task_id="w1-merge-cp",
        items=items,
        merge_title="合并",
        merge_polish=False,
        model_name=None,
        provider_id=None,
        platform="bilibili",
        quality=None,
        link=False,
        screenshot=False,
        _format=None,
        scene=None,
        detail=None,
        extras=None,
        video_understanding=False,
        video_interval=None,
        grid_size=None,
        sampling_mode="interval",
        max_frames=None,
        frames_per_second=None,
        frame_limit_mode="count",
        ocr_assist=None,
        park_kwargs={},
    )


@pytest.fixture
def merge_env(tmp_path, monkeypatch, gate_env):
    calls = {}
    parked = []
    state = SimpleNamespace(park_index=5)

    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(tmp_path / "notes"))
    monkeypatch.setattr(note_module, "NoteGenerator", lambda: _FakeGenerator())
    monkeypatch.setattr(note_module, "_cleanup_merged_subtask_files", lambda _id: None)
    monkeypatch.setattr(note_module, "_enforce_cache_limit_in_background", lambda: None)
    monkeypatch.setattr(
        note_module, "_park_rate_limited_task", lambda task_id, kwargs: parked.append(task_id)
    )
    saved = {}
    monkeypatch.setattr(
        note_module, "save_note_to_file", lambda task_id, note: saved.setdefault(task_id, note)
    )
    breaker = SimpleNamespace(record_success=lambda: None, record_failure=lambda *a, **k: None)
    monkeypatch.setattr(note_module, "_get_circuit_breaker", lambda: breaker)

    def fake_retry(sub_task_id, generator, execute_fn):
        index = int(sub_task_id.rsplit("-s", 1)[1])
        calls[index] = calls.get(index, 0) + 1
        if index == state.park_index:
            return note_module.RATE_LIMIT_PARKED
        return execute_fn()

    monkeypatch.setattr(note_module, "_execute_note_with_retry", fake_retry)
    return SimpleNamespace(calls=calls, parked=parked, saved=saved, state=state)


def test_resume_skips_completed_subitems(merge_env, monkeypatch):
    items = _items(10)
    kwargs = _kwargs(items)

    merge_env.parked.clear()
    # 第一次：第 5 条 429，1..4 已落盘，停放保留 checkpoint。
    note_module._run_merged_note_task(**kwargs)
    assert set(merge_env.calls) == {1, 2, 3, 4, 5}
    assert merge_env.parked == ["w1-merge-cp"]

    directory = note_module._merge_checkpoint_dir("w1-merge-cp")
    files = sorted(os.listdir(directory))
    assert files == ["1.json", "2.json", "3.json", "4.json"], f"断点文件异常：{files}"

    # 第二次：配额恢复（不再 429），1..4 从 checkpoint 复用，只生成 5..10。
    merge_env.calls.clear()
    merge_env.state.park_index = None
    note_module._run_merged_note_task(**kwargs)

    assert set(merge_env.calls) == {5, 6, 7, 8, 9, 10}, (
        f"恢复后只该生成 5..10，实际调用了 {sorted(merge_env.calls)}"
    )
    merged = merge_env.saved["w1-merge-cp"]
    positions = [merged.markdown.index(f"https://video/{i}") for i in range(1, 11)]
    assert positions == sorted(positions), "恢复后的章节顺序必须仍是 1..10"
    assert not os.path.exists(directory), "成功保存后必须删除 checkpoint 目录"
