"""spec 003 ticket 09：真实的音频切割（需要 ffmpeg 在 PATH 上）。"""
import os
import shutil
import subprocess

import pytest

from app.utils.audio_helper import make_silent_wav, probe_duration_seconds, split_audio


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="需要 ffmpeg")


def test_split_wav_into_seconds(tmp_path):
    src = make_silent_wav(3.0, 16000)
    try:
        chunks, temp_dir = split_audio(src, 1.0)
        try:
            assert len(chunks) == 3
            for chunk in chunks:
                assert os.path.getsize(chunk) > 0
                assert 0.8 <= probe_duration_seconds(chunk) <= 1.2
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    finally:
        if os.path.exists(src):
            os.remove(src)


def test_split_mp3_also_works(tmp_path):
    src_wav = make_silent_wav(3.0, 16000)
    src_mp3 = str(tmp_path / "src.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src_wav, src_mp3],
        check=True,
        capture_output=True,
    )
    os.remove(src_wav)

    chunks, temp_dir = split_audio(src_mp3, 1.0)
    try:
        assert len(chunks) >= 2
        total = sum(probe_duration_seconds(c) for c in chunks)
        assert 2.5 <= total <= 3.5
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
