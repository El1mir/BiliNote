"""spec 002 ticket 10：综合采样（LLM 选帧 + 高价值 + 均匀）。"""
from types import SimpleNamespace
from unittest import mock

from app.gpt.universal_gpt import parse_frame_plan
from app.services.note import NoteGenerator
from app.utils import frame_sampler as fs


def test_hybrid_uses_all_three_sources():
    with mock.patch.object(
        fs, "detect_scene_timestamps", return_value=[10.0, 20.0]
    ):
        out = fs.select_hybrid_timestamps(
            "v.mp4",
            subtitle_starts=[1.0, 2.0, 3.0],
            llm_timestamps=[100.0, 200.0],
            max_frames=10,
            duration=300.0,
        )

    assert len(out) == 10
    # LLM 选的点保留
    assert 100.0 in out and 200.0 in out
    # 高价值（场景）保留
    assert 10.0 in out or 20.0 in out
    # 均匀点补足（不属于任何候选）
    known = {1.0, 2.0, 3.0, 10.0, 20.0, 100.0, 200.0}
    assert any(t not in known for t in out)


def test_hybrid_without_llm_falls_back_to_smart_plus_uniform():
    with mock.patch.object(fs, "detect_scene_timestamps", return_value=[10.0]):
        out = fs.select_hybrid_timestamps(
            "v.mp4", subtitle_starts=[1.0], llm_timestamps=[], max_frames=10, duration=100.0
        )
    assert len(out) == 10
    assert 1.0 in out and 10.0 in out


def test_hybrid_without_duration_has_no_uniform_points():
    with mock.patch.object(fs, "detect_scene_timestamps", return_value=[10.0, 20.0]):
        out = fs.select_hybrid_timestamps(
            "v.mp4", subtitle_starts=[], llm_timestamps=[5.0], max_frames=10, duration=0.0
        )
    assert sorted(out) == [5.0, 10.0, 20.0]


def test_hybrid_filters_out_of_range_llm_picks():
    with mock.patch.object(fs, "detect_scene_timestamps", return_value=[]):
        out = fs.select_hybrid_timestamps(
            "v.mp4",
            subtitle_starts=[],
            llm_timestamps=[-5.0, 10.0, 999.0],
            max_frames=5,
            duration=100.0,
        )
    assert 10.0 in out
    assert -5.0 not in out and 999.0 not in out


# ---------------- LLM 返回解析 ----------------

def test_parse_frame_plan_handles_common_shapes():
    assert parse_frame_plan('{"frames":[{"time":12.5},{"time":3}]}') == [3.0, 12.5]
    assert parse_frame_plan('[{"timestamp": 8}, 9]') == [8.0, 9.0]
    # markdown 代码块
    assert parse_frame_plan('```json\n{"frames":[{"time": 1}]}\n```') == [1.0]
    # 非 JSON：正则兜底
    assert parse_frame_plan('好的，这里是结果 "time": 42 ')


def test_parse_frame_plan_filters_and_limits():
    assert parse_frame_plan('{"frames":[{"time":-1},{"time":200}]}', duration=100) == []
    assert parse_frame_plan('{"frames":[{"time":1},{"time":2},{"time":3}]}', max_items=2) == [1.0, 2.0]
    assert parse_frame_plan("完全不是 JSON") == []


# ---------------- note.py 的调用与兜底 ----------------

def _generator():
    return NoteGenerator.__new__(NoteGenerator)


def test_plan_frames_skips_when_no_segments():
    assert _generator()._plan_frames_with_llm(object(), [], "v.mp4", 60) == []


def test_plan_frames_skips_when_gpt_has_no_support():
    segments = [SimpleNamespace(start=0.0, text="x")]
    assert _generator()._plan_frames_with_llm(object(), segments, "v.mp4", 60) == []


def test_plan_frames_returns_empty_on_llm_error():
    class BoomGPT:
        def plan_frame_timestamps(self, *args, **kwargs):
            raise RuntimeError("boom")

    segments = [SimpleNamespace(start=0.0, text="x")]
    result = _generator()._plan_frames_with_llm(BoomGPT(), segments, "v.mp4", 60)
    assert result == []


def test_plan_frames_passes_duration_and_quota():
    calls = {}

    class FakeGPT:
        def plan_frame_timestamps(self, segments, duration=0.0, max_items=24):
            calls.update(duration=duration, max_items=max_items)
            return [1.0, 2.0]

    segments = [SimpleNamespace(start=0.0, text="x")]
    with mock.patch("app.utils.audio_helper.probe_duration_seconds", return_value=120.0):
        result = _generator()._plan_frames_with_llm(FakeGPT(), segments, "v.mp4", 100)

    assert result == [1.0, 2.0]
    assert calls["duration"] == 120.0
    assert calls["max_items"] == 40  # 100 * 0.4


def test_video_reader_hybrid_passes_llm_picks_and_duration():
    from app.utils.video_reader import VideoReader

    reader = VideoReader(
        video_path="v.mp4",
        sampling_mode="hybrid",
        max_frames=5,
        llm_timestamps=[1.0, 2.0],
        subtitle_starts=[3.0],
    )
    assert reader.dedupe_enabled is False  # hybrid 也不做逐帧 MD5 去重

    with mock.patch(
        "app.utils.frame_sampler.select_hybrid_timestamps", return_value=[1, 2, 3]
    ) as sampler, \
            mock.patch.object(reader, "extract_frames") as extract, \
            mock.patch("app.utils.audio_helper.probe_duration_seconds", return_value=10.0), \
            mock.patch("app.utils.video_reader.os.listdir", return_value=[]):
        reader.run()

    assert sampler.call_args.kwargs["llm_timestamps"] == [1.0, 2.0]
    assert sampler.call_args.kwargs["duration"] == 10.0
    extract.assert_called_once_with(timestamps=[1, 2, 3], max_frames=3)


def test_plan_frame_timestamps_prompt_keeps_json_braces():
    """回归：提示词里的 JSON 花括号不能走 str.format，否则 KeyError('"frames"')。"""
    from app.gpt.universal_gpt import UniversalGPT
    from app.models.transcriber_model import TranscriptSegment

    captured = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"frames":[{"time":5}]}')
                )]
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions)

    gpt = UniversalGPT(client=FakeClient(), model="m")
    picks = gpt.plan_frame_timestamps(
        [TranscriptSegment(0.0, 3.0, "你好")], duration=100.0, max_items=5
    )

    assert picks == [5.0]
    system_prompt = captured["messages"][0]["content"]
    # JSON 示例原样保留，占位符已替换
    assert '{"frames": [' in system_prompt
    assert "0 ~ 100.0" in system_prompt
    assert "最多 5 项" in system_prompt


def test_build_plan_lines_thins_long_transcripts():
    from app.gpt.universal_gpt import MAX_PLAN_SEGMENTS, UniversalGPT
    from app.models.transcriber_model import TranscriptSegment

    gpt = UniversalGPT.__new__(UniversalGPT)
    segments = [TranscriptSegment(float(i), float(i) + 1, f"line{i}") for i in range(2000)]
    lines = gpt._build_plan_lines(segments).splitlines()
    assert len(lines) == MAX_PLAN_SEGMENTS
