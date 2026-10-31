"""端到端复跑：走真实生产入口 routers.note.run_note_task（含 save_note_to_file）。"""
import os, sys, time, json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

TASK_ID = "1d994afa-a36c-4861-b4b9-f83d7d5beb12"
VIDEO_URL = "https://www.bilibili.com/video/BV1Rch76WEfQ"

from app.enmus.note_enums import DownloadQuality
from app.routers.note import run_note_task

started = time.time()
run_note_task(
    task_id=TASK_ID,
    video_url=VIDEO_URL,
    platform="bilibili",
    quality=DownloadQuality.medium,
    link=False,
    screenshot=False,
    _format=["screenshot", "summary", "toc"],
    scene="academic",
    detail="detailed",
    video_understanding=True,
    video_interval=6,
    grid_size=[2, 2],
    sampling_mode="smart",
    max_frames=60,
    frames_per_second=2,
    frame_limit_mode="total",
    ocr_assist=None,
)
print("ELAPSED_SEC:", round(time.time() - started, 1))

payload = json.loads((Path("note_results") / f"{TASK_ID}.json").read_text(encoding="utf-8"))
md = payload.get("markdown") or ""
print("JSON_IMAGES:", md.count("!["))
print("JSON_MARKERS:", md.count("[[SHOT"))
print("JSON_STATIC:", md.count("/static/screenshots/"))
