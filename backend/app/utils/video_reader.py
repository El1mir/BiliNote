import base64
import hashlib
import os
import re
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import ffmpeg
from PIL import Image, ImageDraw, ImageFont

from app.utils.logger import get_logger
from app.utils.path_helper import get_app_dir

logger = get_logger(__name__)
class VideoReader:
    def __init__(self,
                 video_path: str,
                 grid_size=(3, 3),
                 frame_interval=2,
                 dedupe_enabled=True,
                 unit_width=960,
                 unit_height=540,
                 save_quality=90,
                 font_path="fonts/arial.ttf",
                 frame_dir=None,
                 grid_dir=None,
                 sampling_mode="interval",
                 max_frames=60,
                 frames_per_second=2,
                 frame_limit_mode="total",
                 subtitle_starts=None,
                 llm_timestamps=None,
                 progress_callback=None,
                 task_id=None):
        self.video_path = video_path
        self.grid_size = grid_size
        self.frame_interval = frame_interval
        self.dedupe_enabled = dedupe_enabled
        self.unit_width = unit_width
        self.unit_height = unit_height
        self.save_quality = save_quality
        # 每个 VideoReader 实例用独立子目录：并发任务共用全局 output_frames 时，
        # run() 的清空逻辑会删掉对方正在用的帧文件（曾导致 frame_xx_yy.jpg 找不到）。
        self._owns_frame_dir = frame_dir is None
        self._owns_grid_dir = grid_dir is None
        _token = uuid.uuid4().hex[:12]
        self.frame_dir = frame_dir or get_app_dir(os.path.join("output_frames", _token))
        self.grid_dir = grid_dir or get_app_dir(os.path.join("grid_output", _token))
        self.progress_callback = progress_callback
        self.task_id = task_id
        self._cache_hit = False
        # spec 002：interval=固定间隔抽帧；smart=画面变化+字幕分段高价值抽帧
        self.sampling_mode = sampling_mode
        self.max_frames = int(max_frames or 60)
        self.frames_per_second = int(frames_per_second or 1)
        self.frame_limit_mode = frame_limit_mode or "total"
        if self.sampling_mode in ("smart", "hybrid"):
            self.dedupe_enabled = False
        self.subtitle_starts = list(subtitle_starts or [])
        self.llm_timestamps = list(llm_timestamps or [])
        self.font_path = font_path

    def _report_progress(self, stage: str, current: int | None = None, total: int | None = None, message: str = ""):
        if self.progress_callback:
            self.progress_callback(stage, current=current, total=total, message=message)

    def _log_timing(self, phase: str, started: float, **fields) -> None:
        elapsed = time.perf_counter() - started
        logger.info("Visual pipeline phase=%s seconds=%.3f cache_hit=%s fields=%s", phase, elapsed, self._cache_hit, fields)



    def _grid_cache_dir(self) -> str | None:
        if not self.task_id:
            return None
        return get_app_dir(os.path.join("visual_cache", "v1"))

    def _video_fingerprint(self) -> str:
        """Return a content fingerprint while keeping mocked pipeline tests cache-safe."""
        digest = hashlib.sha256()
        try:
            stat = os.stat(self.video_path)
            with open(self.video_path, "rb") as source:
                digest.update(source.read(1024 * 1024))
                if stat.st_size > 1024 * 1024:
                    source.seek(max(0, stat.st_size - 1024 * 1024))
                    digest.update(source.read(1024 * 1024))
            digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
        except OSError:
            digest.update(str(self.video_path).encode("utf-8"))
        return digest.hexdigest()
    def _grid_cache_key(self, groups: list[list[str]]) -> str:
        payload = {
            "schema": 1,
            "task_scope": self.task_id,
            "video": self._video_fingerprint(),
            "sampling": [self.sampling_mode, self.max_frames, self.frames_per_second, self.frame_limit_mode, self.frame_interval],
            "timestamps": [Path(path).name for group in groups for path in group],
            "grid": [self.grid_size, self.unit_width, self.unit_height, self.save_quality, self.dedupe_enabled],
            "hybrid_inputs": [self.subtitle_starts, self.llm_timestamps] if self.sampling_mode == "hybrid" else None,
        }
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _calculate_file_md5(file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def format_time(self, seconds: float) -> str:
        """时间戳 → 文件名片段。

        整秒沿用 ``MM_SS``（保持历史文件名格式）；含毫秒时追加 ``_mmm``，
        避免同一秒保留多帧时文件名冲突。
        """
        total_ms = int(round(float(seconds) * 1000))
        mm = total_ms // 60000
        ss = (total_ms % 60000) // 1000
        ms = total_ms % 1000
        if ms == 0:
            return f"{mm:02d}_{ss:02d}"
        return f"{mm:02d}_{ss:02d}_{ms:03d}"

    def extract_time_from_filename(self, filename: str) -> float:
        match = re.search(r"frame_(\d{2})_(\d{2})(?:_(\d{3}))?\.jpg", filename)
        if match:
            mm = int(match.group(1))
            ss = int(match.group(2))
            ms = int(match.group(3) or 0)
            return mm * 60 + ss + ms / 1000.0
        return float('inf')

    def _extract_single_frame(self, ts: int) -> str | None:
        """提取单帧，返回输出路径或 None（失败时）。"""
        time_label = self.format_time(ts)
        output_path = os.path.join(self.frame_dir, f"frame_{time_label}.jpg")
        cmd = ["ffmpeg", "-ss", str(ts), "-i", self.video_path, "-frames:v", "1", "-q:v", "2", "-y", output_path,
               "-hide_banner", "-loglevel", "quiet"]
        try:
            subprocess.run(cmd, check=True)
            return output_path
        except subprocess.CalledProcessError:
            return None

    def extract_frames(self, max_frames=1000, timestamps=None) -> list[str]:

        try:
            os.makedirs(self.frame_dir, exist_ok=True)
            if timestamps is None:
                duration = float(ffmpeg.probe(self.video_path, loglevel="quiet")["format"]["duration"])
                timestamps = [i for i in range(0, int(duration), self.frame_interval)][:max_frames]
            else:
                # 保留亚秒精度：高价值采样可能在同 1 秒内抽多帧。
                # 按毫秒去重，避免两个极近的时间点写到同一个文件名（并行竞态）。
                unique_ts = []
                seen_ts = set()
                for raw_ts in timestamps:
                    key = round(float(raw_ts), 3)
                    if key in seen_ts:
                        continue
                    seen_ts.add(key)
                    unique_ts.append(float(raw_ts))
                timestamps = unique_ts[:max_frames]

            if not timestamps:
                logger.warning("没有可抽帧的时间点，跳过抽帧")
                return []

            # 并行提取帧
            max_workers = min(os.cpu_count() or 4, 8, len(timestamps))
            frame_results: dict[int, str | None] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(self._extract_single_frame, ts): ts for ts in timestamps}
                for future in as_completed(futures):
                    ts = futures[future]
                    frame_results[ts] = future.result()
                    self._report_progress(
                        "extracting_frames",
                        current=len(frame_results),
                        total=len(timestamps),
                        message=f"已抽取 {len(frame_results)} / {len(timestamps)} 帧",
                    )

            # 按时间戳顺序整理结果，并进行去重
            image_paths = []
            last_hash = None
            for ts in timestamps:
                output_path = frame_results.get(ts)
                if not output_path or not os.path.exists(output_path):
                    continue

                if self.dedupe_enabled:
                    frame_hash = self._calculate_file_md5(output_path)
                    if frame_hash == last_hash:
                        os.remove(output_path)
                        continue
                    last_hash = frame_hash

                image_paths.append(output_path)
            return image_paths
        except Exception as e:
            logger.error(f"分割帧发生错误：{str(e)}")
            raise ValueError("视频处理失败")

    def group_images(self) -> list[list[str]]:
        image_files = [os.path.join(self.frame_dir, f) for f in os.listdir(self.frame_dir) if
                       f.startswith("frame_") and f.endswith(".jpg")]
        image_files.sort(key=lambda f: self.extract_time_from_filename(os.path.basename(f)))
        group_size = self.grid_size[0] * self.grid_size[1]
        return [image_files[i:i + group_size] for i in range(0, len(image_files), group_size)]

    def concat_images(self, image_paths: list[str], name: str) -> str | None:
        os.makedirs(self.grid_dir, exist_ok=True)
        font = ImageFont.truetype(self.font_path, 48) if os.path.exists(self.font_path) else ImageFont.load_default()
        images = []

        for path in image_paths:
            # Windows 上并行写帧时偶发文件还没就绪 / 被杀软短暂占用，
            # 读不出来就跳过这一张，别让整次视频理解直接失败。
            try:
                img = Image.open(path).convert("RGB").resize(
                    (self.unit_width, self.unit_height), Image.Resampling.LANCZOS
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"跳过无法读取的帧 {os.path.basename(path)}: {e}")
                continue
            timestamp = re.search(
                r"frame_(\d{2})_(\d{2})(?:_(\d{3}))?\.jpg", os.path.basename(path)
            )
            if timestamp:
                time_text = f"{timestamp.group(1)}:{timestamp.group(2)}"
                if timestamp.group(3) and timestamp.group(3) != "000":
                    time_text += f".{timestamp.group(3)[:1]}"
            else:
                time_text = ""
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), time_text, fill="yellow", font=font, stroke_width=1, stroke_fill="black")
            images.append(img)

        if not images:
            logger.warning(f"第 {name} 组没有任何可读取的帧，跳过")
            return None

        cols, max_rows = self.grid_size
        # 最后一组常常不满：按实际张数收缩行数（「半张」也能用），
        # 而不是拼出一半是空白的图，更不是把这几张丢掉。
        rows = max(1, min(max_rows, (len(images) + cols - 1) // cols))
        if len(images) < cols * max_rows:
            logger.info(f"第 {name} 组只有 {len(images)} 张，按 {cols}x{rows} 拼图（不满一组）")
        grid_img = Image.new("RGB", (self.unit_width * cols, self.unit_height * rows), (255, 255, 255))

        for i, img in enumerate(images):
            x = (i % cols) * self.unit_width
            y = (i // cols) * self.unit_height
            grid_img.paste(img, (x, y))

        save_path = os.path.join(self.grid_dir, f"{name}.jpg")
        grid_img.save(save_path, quality=self.save_quality)
        return save_path

    def encode_images_to_base64(self, image_paths: list[str], report=None) -> list[str]:
        """并发读取并编码为 data URL。

        :param image_paths: 待编码图片路径（顺序即返回顺序）
        :param report: 可选回调 ``report(done, total)``，用于进度回报
        :return: ``data:image/jpeg;base64,...`` 列表，顺序与入参一致
        """
        total = len(image_paths)
        if not total:
            return []

        def _encode_one(path: str) -> str:
            with open(path, "rb") as img_file:
                encoded_string = base64.b64encode(img_file.read()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded_string}"

        results: list[str] = []
        workers = max(1, min(os.cpu_count() or 4, 8, total))
        if workers == 1:
            for idx, path in enumerate(image_paths, start=1):
                results.append(_encode_one(path))
                if report:
                    report(idx, total)
            return results

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="b64") as pool:
            # map 保序：编码结果必须与网格图顺序一致（LLM 看到的图序不能乱）。
            for idx, encoded in enumerate(pool.map(_encode_one, image_paths), start=1):
                results.append(encoded)
                if report:
                    report(idx, total)
        return results

    def run(self)->list[str]:
        logger.info("开始提取视频帧...")
        phase_started = time.perf_counter()
        try:
            # 确保目录存在
            os.makedirs(self.frame_dir, exist_ok=True)
            os.makedirs(self.grid_dir, exist_ok=True)
            #清空帧文件夹
            for file in os.listdir(self.frame_dir):
                if file.startswith("frame_"):
                    os.remove(os.path.join(self.frame_dir, file))
            # 每轮都重建本地网格图；缓存副本单独保存在 visual_cache 中，不受临时目录清理影响。
            for file in os.listdir(self.grid_dir):
                if file.startswith("grid_"):
                    os.remove(os.path.join(self.grid_dir, file))
            if self.sampling_mode in ("smart", "hybrid"):
                from app.utils.audio_helper import probe_duration_seconds
                from app.utils.frame_sampler import (
                    select_hybrid_timestamps,
                    select_smart_timestamps,
                )
                duration = probe_duration_seconds(self.video_path)
                if self.sampling_mode == "hybrid":
                    timestamps = select_hybrid_timestamps(
                        self.video_path,
                        subtitle_starts=self.subtitle_starts,
                        llm_timestamps=self.llm_timestamps,
                        max_frames=self.max_frames,
                        duration=duration,
                    )
                else:
                    timestamps = select_smart_timestamps(
                        self.video_path,
                        subtitle_starts=self.subtitle_starts,
                        max_frames=self.max_frames,
                        max_per_second=self.frames_per_second,
                        frame_limit_mode=self.frame_limit_mode,
                        duration=duration,
                    )
                self._report_progress(
                    "planning_frames", current=1, total=1, message=f"已规划 {len(timestamps)} 个采样时间点"
                )
                # per_second 模式下不设总量上限，帧数可能超过 extract_frames 的默认 1000
                self.extract_frames(timestamps=timestamps, max_frames=len(timestamps))
            else:
                self.extract_frames()
            logger.info("开始拼接网格图...")
            groups = self.group_images()
            cache_root = self._grid_cache_dir()
            cache_key = self._grid_cache_key(groups)
            cache_dir = os.path.join(cache_root, str(self.task_id), cache_key) if cache_root and self.task_id else None
            cache_meta = os.path.join(cache_dir, "metadata.txt") if cache_dir else None
            cached_paths = []
            if cache_dir and cache_meta and os.path.isfile(cache_meta):
                try:
                    cache_stat = os.stat(cache_dir)
                    cache_valid = time.time() - cache_stat.st_mtime <= 7 * 24 * 3600
                    cached_count = int(Path(cache_meta).read_text(encoding="utf-8"))
                    cached_paths = [os.path.join(cache_dir, f"grid_{idx}.jpg") for idx in range(1, cached_count + 1)]
                    cache_valid = cache_valid and cached_count > 0 and all(os.path.isfile(path) and os.path.getsize(path) > 0 for path in cached_paths)
                    if cache_valid:
                        os.utime(cache_dir, None)
                        self._cache_hit = True
                        logger.info("Visual grid cache hit: grids=%s", cached_count)
                    else:
                        # Leave a concurrent writer's immutable cache entry untouched.
                        cached_paths = []
                except Exception:
                    cached_paths = []
            logger.info("Visual grid cache %s", "hit" if self._cache_hit else "miss")
            self._log_timing("frame_extraction", phase_started, frames=frame_total if 'frame_total' in locals() else sum(map(len, groups)), grids=len(groups))
            phase_started = time.perf_counter()
            # 进度分母 = 网格组数 + 待编码图像数（两者都在开始时已知，避免虚假/回退进度）
            frame_total = sum(len(group) for group in groups)
            total_units = len(groups) + frame_total
            grid_paths: list[str | None] = list(cached_paths) if self._cache_hit else []

            def _concat_item(item: tuple[int, list[str]]) -> str | None:
                idx, group = item
                return self.concat_images(group, f"grid_{idx}")

            phase_started = time.perf_counter()
            if groups and not self._cache_hit:
                workers = max(1, min(os.cpu_count() or 4, 8, len(groups)))
                items = list(enumerate(groups, start=1))
                if workers == 1:
                    for idx, group in items:
                        grid_paths.append(self.concat_images(group, f"grid_{idx}"))
                        self._report_progress(
                            "building_grids",
                            current=len(grid_paths),
                            total=total_units,
                            message=f"已拼接 {len(grid_paths)} / {len(groups)} 个网格图",
                        )
                else:
                    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="grid") as pool:
                        for out_path in pool.map(_concat_item, items):
                            grid_paths.append(out_path)
                            self._report_progress(
                                "building_grids",
                                current=len(grid_paths),
                                total=total_units,
                                message=f"已拼接 {len(grid_paths)} / {len(groups)} 个网格图",
                            )

            image_paths = [path for path in grid_paths if path]
            self._log_timing("grid_assembly", phase_started, grids=len(image_paths), cache_entry_hit=self._cache_hit)
            phase_started = time.perf_counter()
            if cache_dir and not self._cache_hit:
                os.makedirs(cache_root, exist_ok=True)
                temporary_dir = f"{cache_dir}.tmp-{uuid.uuid4().hex}"
                os.makedirs(temporary_dir, exist_ok=False)
                try:
                    for idx, image_path in enumerate(image_paths, start=1):
                        shutil.copy2(image_path, os.path.join(temporary_dir, f"grid_{idx}.jpg"))
                    Path(os.path.join(temporary_dir, "metadata.txt")).write_text(str(len(image_paths)), encoding="utf-8")
                    os.makedirs(os.path.dirname(cache_dir), exist_ok=True)
                    try:
                        os.rename(temporary_dir, cache_dir)
                    except OSError:
                        # Keep a concurrent writer's immutable entry; remove only our temp.
                        if os.path.isdir(cache_dir):
                            shutil.rmtree(temporary_dir, ignore_errors=True)
                        else:
                            raise
                    cache_entries = []
                    for candidate in Path(cache_root).rglob("*"):
                        if candidate.is_dir() and (candidate / "metadata.txt").is_file():
                            try:
                                size = sum(item.stat().st_size for item in candidate.rglob("*") if item.is_file())
                                cache_entries.append((candidate.stat().st_mtime, candidate, size))
                            except OSError:
                                continue
                    cache_entries = [entry for entry in cache_entries if (entry[1] / "metadata.txt").is_file()]
                    total_cache_bytes = sum(entry[2] for entry in cache_entries)
                    # TTL applies even when the cache remains under the LRU size/count caps.
                    for _, candidate, size in list(cache_entries):
                        if time.time() - candidate.stat().st_mtime > 7 * 24 * 3600:
                            shutil.rmtree(candidate, ignore_errors=True)
                            total_cache_bytes -= size
                            cache_entries = [entry for entry in cache_entries if entry[1] != candidate]
                    for _, candidate, size in sorted(cache_entries):
                        if total_cache_bytes <= 2 * 1024 * 1024 * 1024 and len(cache_entries) <= 100:
                            break
                        if candidate == Path(cache_dir):
                            continue
                        shutil.rmtree(candidate, ignore_errors=True)
                        total_cache_bytes -= size
                        cache_entries = [entry for entry in cache_entries if entry[1] != candidate]
                except Exception:
                    shutil.rmtree(temporary_dir, ignore_errors=True)
                    logger.warning("Visual grid cache write failed; continuing without cache", exc_info=True)
            logger.info("📤 开始编码图像...")
            urls = self.encode_images_to_base64(
                image_paths,
                report=lambda done, total: self._report_progress(
                    "building_grids",
                    current=len(groups) + done,
                    total=total_units,
                    message=f"正在编码第 {done} / {total} 张图像",
                ),
            )
            self._log_timing(
                "image_base64",
                phase_started,
                image_count=len(image_paths),
                input_bytes=sum(os.path.getsize(path) for path in image_paths if os.path.isfile(path)),
                data_url_bytes=sum(len(url.encode("utf-8")) for url in urls),
            )
            self._report_progress(
                "building_grids",
                current=total_units,
                total=total_units,
                message=f"网格图与图像编码完成，共 {len(urls)} 张",
            )
            return urls
        except Exception as e:
            logger.error(f"发生错误：{str(e)}")
            raise ValueError("视频处理失败")
        finally:
            self._cleanup_temp_dirs()

    def _cleanup_temp_dirs(self):
        """清理本实例自动创建的临时目录（外部显式传入的目录不动）。"""
        for owns, path in (
            (self._owns_frame_dir, self.frame_dir),
            (self._owns_grid_dir, self.grid_dir),
        ):
            if owns and os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
