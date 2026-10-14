"""spec 014 ticket 04：``/task_list`` 每行只读一次结果文件，并用上 ``orjson``。

问题长什么样：``list_tasks`` 的每一行分别调 :func:`_task_title_from_file` 与
:func:`_task_has_note`，而这两个函数读的是**同一个** ``note_results/<task_id>.json``、
做的是**同一遍**解析。结果文件实测平均 55.9KB（中位 18.1KB，873 个共 47.6MB），N=200
时 ``/task_list`` p50 78.09ms 里有 151.4ms 花在这两次读上，纯 SQL 只有 2.9ms。

本文件锁两件事：

1. **读盘次数**：每行至多一次 —— 以 ``stat`` 计数为准（``app/`` 下有 Cython 产物，
   ``open`` 计数偏低，见 conftest.py）。
2. **语义不变**：``(title, has_note)`` 在文件缺失 / 空文件 / JSON 损坏 / markdown 非
   字符串 / ``audio_meta`` 各种形态下，都必须与改动前的两个函数逐字段一致。旧实现
   逐字抄在下面作对照，不依赖 git 历史。
"""

import json
import os

import orjson
import pytest

from app.db import note_group_dao, video_task_dao
from app.routers import note as note_module


# --------------------------------------------------------- 改动前的参考实现

def _legacy_title(result_path):
    """逐字抄自改动前的 ``_task_title_from_file``（读不到返回 ``""``）。"""
    if not result_path.is_file():
        return ""
    try:
        with open(result_path, "r", encoding="utf-8") as handle:
            result = json.load(handle)
    except Exception:
        return ""
    audio_meta = result.get("audio_meta")
    title = audio_meta.get("title") if isinstance(audio_meta, dict) else None
    return str(title or "").strip()


def _legacy_has_note(result_path):
    """逐字抄自改动前的 ``_task_has_note``（读不到返回 ``False``）。"""
    if not result_path.is_file():
        return False
    try:
        with open(result_path, "r", encoding="utf-8") as handle:
            result = json.load(handle)
    except Exception:
        return False
    markdown = result.get("markdown")
    return isinstance(markdown, str) and bool(markdown.strip())


def _legacy_summary(result_path):
    return _legacy_title(result_path), _legacy_has_note(result_path)


# ------------------------------------------------------------- 夹具与工具

#: 覆盖结果文件可能出现的各种形态。``None`` = 不写文件。
_EDGE_CASES = {
    "missing": None,
    "empty": b"",
    "truncated": b"{not json",
    "blank_markdown": b'{"markdown": "   ", "audio_meta": {"title": "T"}}',
    "normal": b'{"markdown": "# hi", "audio_meta": {"title": "T"}}',
    "no_audio_meta": b'{"markdown": "# hi"}',
    "audio_meta_null": b'{"markdown": "# hi", "audio_meta": null}',
    "audio_meta_not_dict": b'{"markdown": "# hi", "audio_meta": "oops"}',
    "title_is_number": b'{"markdown": "# hi", "audio_meta": {"title": 12345}}',
    "title_is_blank": b'{"markdown": "# hi", "audio_meta": {"title": "   "}}',
    "markdown_not_string": b'{"markdown": 123, "audio_meta": {"title": "T"}}',
    "markdown_null": b'{"markdown": null, "audio_meta": {"title": "T"}}',
    "empty_object": b"{}",
}


def _write_result(results_dir, task_id, raw):
    path = results_dir / f"{task_id}.json"
    if raw is not None:
        path.write_bytes(raw)
    return path


def _make_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app)


def _patch_dao(monkeypatch, rows, groups=None):
    monkeypatch.setattr(video_task_dao, "list_video_tasks", lambda: list(rows))
    monkeypatch.setattr(note_group_dao, "list_groups", lambda: list(groups or []))


def _row(task_id, **overrides):
    row = {
        "task_id": task_id,
        "video_id": "BV1xx411c7mD",
        "platform": "bilibili",
        "group_id": None,
        "created_at": "2026-10-14 12:00:00",
    }
    row.update(overrides)
    return row


# ----------------------------------------------------------- 语义等价性


@pytest.mark.parametrize("case", sorted(_EDGE_CASES))
def test_summary_matches_legacy_implementation(case, results_dir):
    """每一个边界形态下，新实现与旧的两个函数必须给出同一个 ``(title, has_note)``。"""
    task_id = f"t-{case}"
    result_path = _write_result(results_dir, task_id, _EDGE_CASES[case])

    expected = _legacy_summary(result_path)
    assert note_module._read_result_summary(task_id) == expected

    # 两个薄封装也必须与各自的旧实现一致（它们仍有调用方：测量脚本按函数粒度计开销）。
    assert note_module._task_title_from_file(task_id) == expected[0]
    assert note_module._task_has_note(task_id) == expected[1]


def test_non_dict_result_degrades_instead_of_breaking_the_list(results_dir, monkeypatch):
    """合法 JSON 但不是对象时，旧实现会抛 ``AttributeError`` 把整个列表打成 500。

    新实现退化成「这个任务没有标题也没有笔记」——一个坏文件不该毁掉全表。这是本
    ticket **唯一**的有意行为变更，单独测出来，不混在等价性用例里。
    """
    task_id = "t-list-json"
    _write_result(results_dir, task_id, b"[1, 2, 3]")

    with pytest.raises(AttributeError):
        _legacy_summary(results_dir / f"{task_id}.json")  # 旧实现确实会炸

    assert note_module._read_result_summary(task_id) == ("", False)

    _patch_dao(monkeypatch, [_row(task_id)])
    body = _make_client().get("/api/task_list").json()

    assert body["code"] == 0, body
    assert body["data"]["tasks"][0]["title"] == ""
    assert body["data"]["tasks"][0]["has_note"] is False


# -------------------------------------------------- orjson 与标准库一致

#: 两边都能解析的输入：换解析器不能让同一份文件解析出不同的东西。
_PARSE_AGREEMENT_RAW = [
    b'{"markdown": "# hi", "audio_meta": {"title": "T"}}',
    '{"markdown": "\\u4e2d\\u6587", "audio_meta": {"title": "标题"}}'.encode("utf-8"),
    b'{"f": 1.5, "i": 2, "s": "x", "b": true, "nul": null}',
    b'{"markdown": "a", "markdown": "b"}',
    b'{"nested": {"deep": [1, {"x": null}]}}',
    b'{"neg": -0.0, "exp": 1e10}',
]

#: ``orjson`` 比标准库**严格**的输入：它拒收，标准库收下。
#: 结果文件是 ``save_note_to_file`` 用标准库 ``json.dump``（默认 ``allow_nan=True``）
#: 写的，所以裸 ``NaN`` / ``Infinity`` 真的可能出现 —— 这就是必须留标准库兜底的原因。
_ORJSON_STRICTER_RAW = [
    b'{"n": NaN, "markdown": "# hi", "audio_meta": {"title": "T"}}',
    b'{"n": Infinity, "markdown": "# hi", "audio_meta": {"title": "T"}}',
]


@pytest.mark.parametrize("raw", _PARSE_AGREEMENT_RAW)
def test_orjson_matches_stdlib_json(raw):
    """两边都接受的输入，解析结果必须一致。

    比的是**再序列化后的文本**：这样重复键（两侧都取最后一个）、大整数与浮点的表示
    差异都能一并覆盖，不需要自己写递归比较。
    """
    mine = json.dumps(orjson.loads(raw), sort_keys=True, ensure_ascii=False)
    theirs = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False)

    assert mine == theirs


@pytest.mark.parametrize("raw", _ORJSON_STRICTER_RAW)
def test_orjson_strictness_is_absorbed_by_the_fallback(raw, results_dir):
    """orjson 拒收但标准库收得下的文件，仍然必须解析成功（走 ``_loads_result`` 的兜底）。

    少了兜底，这些文件会静默降级成「没标题、没笔记」——比报错更难发现。
    """
    with pytest.raises(orjson.JSONDecodeError):
        orjson.loads(raw)
    json.loads(raw)  # 标准库收下，不抛

    task_id = "t-strict"
    _write_result(results_dir, task_id, raw)

    assert note_module._read_result_summary(task_id) == ("T", True)
    assert note_module._task_title_from_file(task_id) == "T"
    assert note_module._task_has_note(task_id) is True


def test_orjson_downgrades_huge_integers_but_extraction_is_unaffected(results_dir):
    """另一条差异：超出 64 位的整数被 ``orjson`` **降级成 float**（丢精度），标准库保留原值。

    这是**静默**的类型变化（不抛异常），所以单独钉一条用例说明我们知情：
    ``_read_result_summary`` 只取 ``markdown`` 与 ``audio_meta.title`` 两个字符串字段，
    根本碰不到大整数，因此对 ``/task_list`` 没有任何影响。
    """
    raw = (
        b'{"big": 123456789012345678901234567890, '
        b'"markdown": "# hi", "audio_meta": {"title": "T"}}'
    )

    assert isinstance(json.loads(raw)["big"], int)
    assert isinstance(orjson.loads(raw)["big"], float)
    assert json.loads(raw)["big"] != orjson.loads(raw)["big"]

    task_id = "t-bigint"
    _write_result(results_dir, task_id, raw)

    assert note_module._read_result_summary(task_id) == ("T", True)


def test_orjson_rejects_what_stdlib_rejects(results_dir, monkeypatch):
    """``orjson`` 抛的是自己的 ``JSONDecodeError``，异常处理不能依赖它是子类。"""
    with pytest.raises(orjson.JSONDecodeError):
        orjson.loads(b"{not json")

    for case in ("empty", "truncated"):
        task_id = f"t-parse-{case}"
        _write_result(results_dir, task_id, _EDGE_CASES[case])
        assert note_module._read_result_summary(task_id) == ("", False)


# ------------------------------------------------------------- 读盘次数


def test_task_list_reads_each_result_file_once(results_dir, monkeypatch):
    """N=200：每行至多一次 ``stat``（改动前是每行两次 —— 两个函数各读一遍）。"""
    row_count = 200
    counter = _make_stat_counter()
    monkeypatch.setattr(os, "stat", counter)

    rows = []
    for index in range(row_count):
        task_id = f"t-row-{index}"
        _write_result(
            results_dir,
            task_id,
            json.dumps(
                {"markdown": "# hi", "audio_meta": {"title": f"标题 {index}"}},
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        rows.append(_row(task_id))
    _patch_dao(monkeypatch, rows)

    body = _make_client().get("/api/task_list").json()

    assert body["code"] == 0, body
    tasks = body["data"]["tasks"]
    assert len(tasks) == row_count
    assert body["data"]["total"] == row_count
    # 每行一次 is_file()；read_bytes() 不再 stat。改动前这里是 2 × row_count。
    assert counter.calls <= row_count, f"每行读了不止一次：{counter.calls} 次 / {row_count} 行"


def _make_stat_counter():
    real_stat = os.stat

    class _Counter:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1
            return real_stat(*args, **kwargs)

    return _Counter()


def test_task_list_reads_no_result_file_for_plain_rows(results_dir, monkeypatch):
    """没有结果文件的行（刚入队 / 失败）只 stat 一次、**不读**任何文件。"""
    from pathlib import Path

    row_count = 10
    stat_counter = _make_stat_counter()
    original_read_bytes = Path.read_bytes
    reads = []

    def counting_read_bytes(self):
        reads.append(self.name)
        return original_read_bytes(self)

    monkeypatch.setattr(os, "stat", stat_counter)
    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    _patch_dao(monkeypatch, [_row(f"t-empty-{index}") for index in range(row_count)])

    body = _make_client().get("/api/task_list").json()

    assert body["code"] == 0, body
    assert all(task["title"] == "" and task["has_note"] is False for task in body["data"]["tasks"])
    assert reads == [], f"没有结果文件却读了 {reads}"
    assert stat_counter.calls <= row_count


def test_newly_queued_task_appears_immediately(results_dir, monkeypatch):
    """既有承诺不能破：入队即落库，所以列表**不缓存**，新建的任务立刻可见。"""
    _patch_dao(monkeypatch, [_row("t-brand-new")])

    body = _make_client().get("/api/task_list").json()

    assert [task["task_id"] for task in body["data"]["tasks"]] == ["t-brand-new"]


def test_response_fields_are_unchanged(results_dir, monkeypatch):
    """返回体结构不变（逐个字段点名，而不是只看条数）。"""
    task_id = "t-fields"
    _write_result(
        results_dir,
        task_id,
        b'{"markdown": "# hi", "audio_meta": {"title": "T"}}',
    )
    _patch_dao(monkeypatch, [_row(task_id, group_id="7")], groups=[{"id": 7, "name": "收藏夹"}])

    body = _make_client().get("/api/task_list").json()

    assert body["code"] == 0, body
    assert body["data"]["tasks"] == [
        {
            "task_id": task_id,
            "video_id": "BV1xx411c7mD",
            "platform": "bilibili",
            "group_id": "7",
            "group_name": "收藏夹",
            "title": "T",
            "has_note": True,
            "created_at": "2026-10-14 12:00:00",
        }
    ]
