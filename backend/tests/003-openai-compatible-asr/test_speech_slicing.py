"""spec 003 ticket 11：chat 风格 ASR 按「说话」自动切片，拿真实语音边界当时间轴。"""
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from app.transcriber import openai_asr
from app.transcriber.openai_asr import OpenAIASRTranscriber
from app.utils.audio_helper import detect_speech_regions, merge_regions_to_limit


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def _make_speech_audio(path: str) -> None:
    """1s 静音 + 1s 音 + 1s 静音 + 1s 音 + 1s 静音。"""
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=1",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1",
            "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=16000:duration=1",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1",
            "-filter_complex", "[0][1][2][3][4]concat=n=5:v=0:a=1[out]",
            "-map", "[out]", path,
        ],
        check=True,
        capture_output=True,
    )


def _chat_client(handler):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: handler(kw))
        )
    )


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="需要 ffmpeg")


def test_detect_speech_regions_finds_speech_not_silence(tmp_path):
    audio = tmp_path / "sp.wav"
    _make_speech_audio(str(audio))

    regions = detect_speech_regions(str(audio))

    assert len(regions) == 2
    assert abs(regions[0][0] - 1.0) < 0.2 and abs(regions[0][1] - 2.0) < 0.2
    assert abs(regions[1][0] - 3.0) < 0.2 and abs(regions[1][1] - 4.0) < 0.2


def test_merge_regions_to_limit_merges_smallest_gap():
    regions = [(0.0, 1.0), (1.2, 2.0), (10.0, 11.0)]
    merged = merge_regions_to_limit(regions, max_count=2)
    assert len(merged) == 2
    # 空隙最小的一对（1.0→1.2）先被合并
    assert merged[0] == (0.0, 2.0)


def test_chat_style_uses_speech_boundaries_as_timeline(tmp_path):
    audio = tmp_path / "sp.wav"
    _make_speech_audio(str(audio))
    seen = []

    def handler(kwargs):
        seen.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"第{len(seen)}段文字"))]
        )

    with mock.patch.object(
        openai_asr, "build_openai_client", return_value=_chat_client(handler)
    ):
        result = OpenAIASRTranscriber(
            "https://x/v1", "sk", "m", api_style="chat"
        ).transcript(str(audio))

    # 两段语音 → 两次请求，时间轴来自真实静音边界
    assert len(seen) == 2
    assert len(result.segments) == 2
    assert abs(result.segments[0].start - 1.0) < 0.2
    assert abs(result.segments[0].end - 2.0) < 0.2
    assert abs(result.segments[1].start - 3.0) < 0.2
    assert result.segments[1].text == "第2段文字"
    assert result.full_text == "第1段文字 第2段文字"


def test_chat_style_falls_back_when_no_speech_detected(tmp_path):
    audio = tmp_path / "sp.wav"
    _make_speech_audio(str(audio))

    def handler(kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="整段文字"))]
        )

    with mock.patch.object(
        openai_asr, "detect_speech_regions", return_value=[]
    ), mock.patch.object(
        openai_asr, "build_openai_client", return_value=_chat_client(handler)
    ):
        result = OpenAIASRTranscriber(
            "https://x/v1", "sk", "m", api_style="chat"
        ).transcript(str(audio))

    # 退化路径：仍然能拿到文本
    assert result.full_text == "整段文字"


def test_speech_params_are_passed_from_endpoint_config(tmp_path):
    audio = tmp_path / "sp.wav"
    _make_speech_audio(str(audio))
    seen = {}

    def fake_detect(path, noise_db=-30.0, min_silence=0.5, timeout=900):
        seen["noise_db"] = noise_db
        seen["min_silence"] = min_silence
        return [(0.0, 1.0)]

    def fake_merge(regions, max_count=120):
        seen["max_count"] = max_count
        return regions

    def handler(kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="文字"))]
        )

    with mock.patch.object(openai_asr, "detect_speech_regions", side_effect=fake_detect), \
            mock.patch.object(openai_asr, "merge_regions_to_limit", side_effect=fake_merge), \
            mock.patch.object(
                openai_asr, "build_openai_client", return_value=_chat_client(handler)
            ):
        OpenAIASRTranscriber(
            "https://x/v1", "sk", "m",
            api_style="chat",
            max_speech_chunks=42,
            silence_noise_db=-38.5,
            min_silence_seconds=0.9,
        ).transcript(str(audio))

    assert seen == {"noise_db": -38.5, "min_silence": 0.9, "max_count": 42}
