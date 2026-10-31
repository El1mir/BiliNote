"""spec 017 ticket 004：流水线缓存接缝的行为契约。

这些用例锁的是「坏缓存等于未命中，不等于任务失败」这条策略 —— 旧代码三处读转写缓存
各写各的，其中一处用 ``data["language"]`` 直接取键，缺字段就抛 KeyError 把任务打断。
"""

import json
from pathlib import Path

from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.note_cache import (
    read_audio_cache,
    read_json_cache,
    read_transcript_cache,
    shared_transcript_path,
    write_audio_cache,
    write_json_cache,
    write_transcript_cache,
)


def test_read_json_cache_missing_file_is_a_miss(tmp_path: Path) -> None:
    assert read_json_cache(tmp_path / "nope.json") is None


def test_read_json_cache_corrupt_payload_is_a_miss(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_json_cache(path) is None


def test_read_json_cache_non_object_is_a_miss(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert read_json_cache(path) is None


def test_write_json_cache_is_atomic_and_utf8(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "payload.json"
    assert write_json_cache(path, {"title": "图神经网络"}) is True
    assert path.read_text(encoding="utf-8").find("图神经网络") > 0
    # 原子写不该留下临时文件
    assert list(path.parent.glob("*.tmp")) == []


def test_transcript_cache_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "task_transcript.json"
    transcript = TranscriptResult(
        language="zh",
        full_text="你好",
        segments=[TranscriptSegment(start=0.0, end=1.5, text="你好")],
    )
    assert write_transcript_cache(path, transcript) is True
    loaded = read_transcript_cache(path)
    assert loaded is not None
    assert loaded.full_text == "你好"
    assert len(loaded.segments) == 1


def test_transcript_cache_without_language_still_loads(tmp_path: Path) -> None:
    """旧代码有一处用 data["language"] 直接取键；缺字段必须是 miss 而不是崩。"""
    path = tmp_path / "task_transcript.json"
    path.write_text(json.dumps({"full_text": "text", "segments": []}), encoding="utf-8")
    loaded = read_transcript_cache(path)
    assert loaded is not None
    assert loaded.language is None


def test_transcript_cache_without_full_text_is_a_miss(tmp_path: Path) -> None:
    path = tmp_path / "task_transcript.json"
    path.write_text(json.dumps({"segments": []}), encoding="utf-8")
    assert read_transcript_cache(path) is None


def test_transcript_cache_skips_unparsable_segment(tmp_path: Path) -> None:
    path = tmp_path / "task_transcript.json"
    path.write_text(
        json.dumps(
            {
                "language": "zh",
                "full_text": "text",
                "segments": [{"start": 0, "end": 1, "text": "ok"}, {"bogus": 1}],
            }
        ),
        encoding="utf-8",
    )
    loaded = read_transcript_cache(path)
    assert loaded is not None
    assert len(loaded.segments) == 1


def test_audio_cache_requires_the_media_file(tmp_path: Path) -> None:
    """媒体清理会删掉音频；只认缓存不认文件会让任务拿着死路径去转写。"""
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"x")
    cache = tmp_path / "task_audio.json"
    audio = AudioDownloadResult(
        file_path=str(media),
        title="测试音频",
        duration=12.0,
        cover_url=None,
        platform="bilibili",
        video_id="BV1",
        raw_info={},
    )
    assert write_audio_cache(cache, audio) is True
    assert read_audio_cache(cache) is not None

    media.unlink()
    assert read_audio_cache(cache) is None
    # 不校验文件时仍然可读（调用方明确知道自己只要元信息）
    assert read_audio_cache(cache, require_file=False) is not None


def test_shared_transcript_path_is_stable_and_engine_scoped(tmp_path: Path) -> None:
    """跨任务共享缓存的键：同一视频 + 同一引擎必须落到同一个文件。"""
    a = shared_transcript_path(
        tmp_path, "https://www.bilibili.com/video/BV1uY41167Ha", "fast-whisper|tiny"
    )
    b = shared_transcript_path(
        tmp_path, "https://www.bilibili.com/video/BV1uY41167Ha", "fast-whisper|tiny"
    )
    assert a == b
    assert a.parent == tmp_path / "shared"
    assert a.name.startswith("transcript_") and a.suffix == ".json"


def test_shared_transcript_path_separates_engines_and_videos(tmp_path: Path) -> None:
    """换转写引擎或换视频必须换键 —— 否则会把上一次的答案冒充这一次的结果。"""
    url = "https://www.bilibili.com/video/BV1uY41167Ha"
    other_url = "https://www.bilibili.com/video/BV1uY41167Hb"
    base = shared_transcript_path(tmp_path, url, "fast-whisper|tiny")
    assert base != shared_transcript_path(tmp_path, url, "fast-whisper|base")
    assert base != shared_transcript_path(tmp_path, url, "openai-asr|unconfigured")
    assert base != shared_transcript_path(tmp_path, other_url, "fast-whisper|tiny")


def test_shared_transcript_path_round_trips_through_the_cache_seam(
    tmp_path: Path,
) -> None:
    """共享路径和任务级路径走同一套读写，命中语义必须一致。"""
    path = shared_transcript_path(tmp_path, "BV1uY41167Ha", "fast-whisper|tiny")
    assert read_transcript_cache(path) is None
    transcript = TranscriptResult(
        language="zh",
        full_text="你好世界",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="你好世界")],
    )
    assert write_transcript_cache(path, transcript) is True
    restored = read_transcript_cache(path)
    assert restored is not None
    assert restored.full_text == "你好世界"
