"""用真实任务数据复现「有插图位置却没有图片」，验证修复。"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.enmus.note_enums import DownloadQuality
from app.services.note import NoteGenerator

TASK_ID = "1d994afa-a36c-4861-b4b9-f83d7d5beb12"
VIDEO_URL = "https://www.bilibili.com/video/BV1Rch76WEfQ"

gen = object.__new__(NoteGenerator)
gen.video_path = None
gen.shot_frames = None
gen.shot_image_paths = None
gen.shot_image_urls = None
gen.approved_shots = None
gen.ocr_texts = None
gen.ocr_judgement_enabled = True
gen.ocr_assist = False
gen.ocr_failures = 0
gen.ocr_cache_used_ocr = False
gen.ocr_cache_url = None
gen.frame_candidates = None
gen.picked_frames = None
gen.video_img_urls = []
gen.last_error_non_retryable = False
gen.last_error_rate_limited = False
gen._update_status = lambda *a, **kw: None

# 1) 音频缓存命中：视频路径是否被找回
audio = gen._download_media(
    downloader=BilibiliDownloader(),
    video_url=VIDEO_URL,
    quality=DownloadQuality.medium,
    audio_cache_file=Path("note_results") / f"{TASK_ID}_audio.json",
    status_phase=None,
    platform="bilibili",
    output_path=None,
    screenshot=True,
    video_understanding=True,
    video_interval=6,
    grid_size=[2, 2],
    task_id=TASK_ID,
)
print("AUDIO_TITLE:", audio.title[:30])
print("VIDEO_PATH:", gen.video_path)
print("VIDEO_EXISTS:", bool(gen.video_path and Path(gen.video_path).is_file()))

# 2) 复用 OCR 磁盘缓存（与第二次运行一致）
loaded = gen._load_ocr_cache(VIDEO_URL, need_ocr=False)
print("OCR_CACHE_LOADED:", loaded, "APPROVED:", len(gen.approved_shots or []))
print("OCR_TEXTS:", len(gen.ocr_texts or {}))

# 3) 复用 OCR 时补渲染单帧（新增的 P6 分支）
if not gen.shot_image_urls:
    gen._render_shot_frames(gen.video_path, task_id=TASK_ID)
print("SHOT_URLS:", len(gen.shot_image_urls or []))
print("SHOT_PATHS:", len(gen.shot_image_paths or []))
print("PROMPT_IMG_URLS_NONEMPTY:", sum(1 for u in (gen.shot_image_urls or []) if u))

# 4) 后处理插图
md_path = Path("note_results") / f"{TASK_ID}_markdown.md"
markdown = md_path.read_text(encoding="utf-8")
print("BEFORE_IMG:", markdown.count("!["), "BEFORE_MARKERS:", markdown.count("[[SHOT"))

class _Meta:
    video_id = "BV1Rch76WEfQ"

out = gen._post_process_markdown(
    markdown=markdown,
    video_path=gen.video_path,
    formats=["screenshot", "summary", "toc"],
    audio_meta=_Meta(),
    platform="bilibili",
    task_id=TASK_ID,
)
print("AFTER_IMG:", out.count("!["), "AFTER_MARKERS:", out.count("[[SHOT"))
print("STATIC_LINKS:", out.count("/static/screenshots/"))
Path("note_results/_verify_fixed.md").write_text(out, encoding="utf-8")
print("SAMPLE:", [l for l in out.splitlines() if l.startswith("![")][:2])
