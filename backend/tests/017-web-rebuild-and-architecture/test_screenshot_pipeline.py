"""spec 017：「有插图位置却没有图片」的回归用例。

这条缺陷有两个独立的成因，都在真实任务 1d994afa-a36c-4861-b4b9-f83d7d5beb12 上复现过：

1. 音频缓存命中时 `_download_media` 直接 return，从不设置 `self.video_path`，
   而 `_post_process_markdown` 的插图分支以它为开关 —— 于是「第二次生成」这条最常用
   的路径永远插不进图，日志里却一切正常。
2. 复用 OCR 磁盘缓存时只复用了文字，图片不在缓存里（data URL 太占地方），
   于是模型收到 0 张图却仍被要求写 `[[SHOT-n]]`，占位符最后没人替换。

这里把两个成因和「残留占位符必须被清掉」的兜底都钉成用例。
"""
from pathlib import Path
from types import SimpleNamespace

from app.services import note as note_module
from app.services.note import NoteGenerator
from app.services.ocr_assist import WorthDecision


def _generator(tmp_path, monkeypatch, render_calls=None):
    """最小可用的 NoteGenerator：不初始化转写器，只装本组用例要用的状态。"""
    generator = object.__new__(NoteGenerator)
    generator.video_path = None
    generator.shot_frames = None
    generator.shot_image_paths = None
    generator.shot_image_urls = None
    generator.approved_shots = []
    generator.ocr_texts = None
    generator.ocr_judgement_enabled = True
    generator.ocr_assist = False
    generator.ocr_failures = 0
    generator.frame_candidates = []
    generator.picked_frames = []
    generator.video_img_urls = []

    statuses = []

    def fake_update_status(
        task_id, status, message=None, *, stage=None, progress=None,
        stage_progress=None, detail=None,
    ):
        statuses.append(message)

    def fake_generate_screenshot(video_path, output_dir, ts, index):
        if render_calls is not None:
            render_calls.append((str(video_path), ts, index))
        out = Path(output_dir) / f"screenshot_{index:03}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-jpeg")
        return str(out)

    generator._update_status = fake_update_status
    monkeypatch.setattr(note_module, "generate_screenshot", fake_generate_screenshot)
    monkeypatch.setattr(note_module, "IMAGE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(note_module, "IMAGE_BASE_URL", "/static/screenshots")
    # register_resource 会写数据库；这组用例只关心插图链路。
    monkeypatch.setattr(
        "app.services.media_resource_service.register_resource",
        lambda *a, **kw: None,
    )
    return generator, statuses


def _audio(video_id, video_path=None):
    return SimpleNamespace(
        file_path="audio.mp3",
        title="t",
        duration=1.0,
        cover_url=None,
        platform="bilibili",
        video_id=video_id,
        raw_info={},
        video_path=video_path,
    )


class _Downloader:
    """只实现 _download_media 用到的两个方法。"""

    def __init__(self, video_path):
        self.video_path = video_path
        self.download_video_calls = []

    def download_video(self, video_url, output_dir=None):
        self.download_video_calls.append((str(video_url), output_dir))
        target = Path(self.video_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video")
        return self.video_path

    def download(self, **kwargs):  # pragma: no cover - 缓存命中时不该走到这里
        raise AssertionError("缓存命中后不应再下载音频")


def _download_media_kwargs(tmp_path):
    # 缓存分支以「文件存在」为前提；内容由 read_audio_cache 的桩提供。
    (tmp_path / "audio.json").write_text("{}", encoding="utf-8")
    return dict(
        video_url="https://www.bilibili.com/video/BV1test",
        quality=None,
        audio_cache_file=tmp_path / "audio.json",
        status_phase=None,
        platform="bilibili",
        output_path=str(tmp_path),
        screenshot=True,
        video_understanding=False,
        video_interval=6,
        grid_size=[2, 2],
        task_id="task-1",
    )


def test_cache_hit_restores_video_path_from_data_dir(tmp_path, monkeypatch):
    """缓存命中 + 本地 mp4 还在 → 必须把 video_path 找回来，不重新下载。"""
    generator, _ = _generator(tmp_path, monkeypatch)
    video_file = tmp_path / "BV1test.mp4"
    video_file.write_bytes(b"video")

    monkeypatch.setattr(
        note_module, "read_audio_cache", lambda *a, **kw: _audio("BV1test")
    )
    downloader = _Downloader(str(video_file))

    generator._download_media(downloader=downloader, **_download_media_kwargs(tmp_path))

    assert generator.video_path == video_file
    assert downloader.download_video_calls == []


def test_cache_hit_redownloads_when_video_file_missing(tmp_path, monkeypatch):
    """缓存命中但 mp4 被媒体清理删掉了 → 重下一次（download_video 幂等）。"""
    generator, _ = _generator(tmp_path, monkeypatch)
    video_file = tmp_path / "BV1test.mp4"
    assert not video_file.exists()

    monkeypatch.setattr(
        note_module, "read_audio_cache", lambda *a, **kw: _audio("BV1test")
    )
    downloader = _Downloader(str(video_file))

    generator._download_media(downloader=downloader, **_download_media_kwargs(tmp_path))

    assert generator.video_path == video_file
    assert len(downloader.download_video_calls) == 1


def test_cache_hit_without_need_video_does_not_touch_downloader(tmp_path, monkeypatch):
    """不要截图也不要视频理解时，缓存命中不该顺手下一份视频。"""
    generator, _ = _generator(tmp_path, monkeypatch)
    monkeypatch.setattr(
        note_module, "read_audio_cache", lambda *a, **kw: _audio("BV1test")
    )
    downloader = _Downloader(str(tmp_path / "BV1test.mp4"))
    kwargs = _download_media_kwargs(tmp_path)
    kwargs["screenshot"] = False

    generator._download_media(downloader=downloader, **kwargs)

    assert generator.video_path is None
    assert downloader.download_video_calls == []


def test_render_shot_frames_is_idempotent(tmp_path, monkeypatch):
    """同一批判定结果只渲一次；重复调用不再跑 ffmpeg。"""
    calls = []
    generator, _ = _generator(tmp_path, monkeypatch, render_calls=calls)
    generator.approved_shots = [WorthDecision(time=10.0), WorthDecision(time=20.0)]
    video_file = tmp_path / "v.mp4"
    video_file.write_bytes(b"video")

    frames = generator._render_shot_frames(video_file, task_id="task-1")
    again = generator._render_shot_frames(video_file, task_id="task-1")

    assert len(calls) == 2
    assert [f[0] for f in frames] == [1, 2]
    assert len(generator.shot_image_urls) == 2
    assert len(generator.shot_image_paths) == 2
    assert again == frames


def test_insert_approved_screenshots_reuses_rendered_frames(tmp_path, monkeypatch):
    """送模型的图与插进笔记的图必须是同一批文件，不能再渲一遍。"""
    calls = []
    generator, _ = _generator(tmp_path, monkeypatch, render_calls=calls)
    generator.approved_shots = [WorthDecision(time=10.0)]
    video_file = tmp_path / "v.mp4"
    video_file.write_bytes(b"video")

    generator._render_shot_frames(video_file, task_id="task-1")
    assert len(calls) == 1

    markdown = generator._insert_approved_screenshots(
        "正文\n\n[[SHOT-1]]\n\n结尾", video_file, generator.approved_shots, task_id="task-1"
    )

    assert len(calls) == 1, "后处理不该重新渲染已存在的单帧"
    assert "/static/screenshots/screenshot_001.jpg" in markdown
    assert "[[SHOT-1]]" not in markdown


def test_post_process_drops_leftover_markers_when_video_missing(tmp_path, monkeypatch, caplog):
    """拿不到视频 → 跳过插图，但必须留下日志并清掉占位符，不能把空壳留给用户。"""
    generator, _ = _generator(tmp_path, monkeypatch)
    generator.approved_shots = [WorthDecision(time=10.0)]

    with caplog.at_level("WARNING"):
        markdown = generator._post_process_markdown(
            "正文\n\n[[SHOT-1]]\n\n结尾",
            None,
            ["screenshot"],
            SimpleNamespace(video_id="BV1test"),
            "bilibili",
            task_id="task-1",
        )

    assert "[[SHOT-1]]" not in markdown
    assert "跳过插图" in caplog.text
    assert "未替换的截图占位符" in caplog.text


def test_post_process_sweeps_markers_the_model_over_wrote(tmp_path, monkeypatch, caplog):
    """模型多写了编号时，多出来的占位符也必须被清掉。"""
    calls = []
    generator, _ = _generator(tmp_path, monkeypatch, render_calls=calls)
    generator.approved_shots = [WorthDecision(time=10.0)]
    video_file = tmp_path / "v.mp4"
    video_file.write_bytes(b"video")
    generator.video_path = video_file

    with caplog.at_level("WARNING"):
        markdown = generator._post_process_markdown(
            "A\n\n[[SHOT-1]]\n\nB\n\n[[SHOT-7]]\n\nC",
            video_file,
            ["screenshot"],
            SimpleNamespace(video_id="BV1test"),
            "bilibili",
            task_id="task-1",
        )

    assert "/static/screenshots/screenshot_001.jpg" in markdown
    assert "[[SHOT-7]]" not in markdown
    assert "未替换的截图占位符" in caplog.text


def test_render_shot_frames_without_approved_shots_is_empty(tmp_path, monkeypatch):
    generator, _ = _generator(tmp_path, monkeypatch)
    generator.approved_shots = []

    assert generator._render_shot_frames(tmp_path / "v.mp4", task_id="t") == []
    assert generator.shot_image_urls == []
