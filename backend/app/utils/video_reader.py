import base64
import hashlib
import os
import re
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                 llm_timestamps=None):
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
        # spec 002：interval=固定间隔抽帧；smart=画面变化+字幕分段高价值抽帧
        self.sampling_mode = sampling_mode
        self.max_frames = int(max_frames or 60)
        # spec 002 修正：高价值采样限制方式二选一——
        #   total：只用 max_frames（全片上限）；per_second：只用 frames_per_second（每秒上限）
        self.frames_per_second = int(frames_per_second or 1)
        self.frame_limit_mode = frame_limit_mode or "total"
        # 高价值采样已经按内容挑过帧了，再做逐帧 MD5 去重会把长静态画面（PPT / 口播课）
        # 全删掉（实测 40 分钟课程被删到只剩几张），所以 smart 模式关闭这个兜底去重。
        if self.sampling_mode in ("smart", "hybrid"):
            self.dedupe_enabled = False
        self.subtitle_starts = list(subtitle_starts or [])
        # 综合采样：LLM 读字幕挑出来的时间点
        self.llm_timestamps = list(llm_timestamps or [])
        self.font_path = font_path

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

    def encode_images_to_base64(self, image_paths: list[str]) -> list[str]:
        base64_images = []
        for path in image_paths:
            with open(path, "rb") as img_file:
                encoded_string = base64.b64encode(img_file.read()).decode("utf-8")
                base64_images.append(f"data:image/jpeg;base64,{encoded_string}")
        return base64_images

    def run(self)->list[str]:
        logger.info("开始提取视频帧...")
        try:
            # 确保目录存在
            os.makedirs(self.frame_dir, exist_ok=True)
            os.makedirs(self.grid_dir, exist_ok=True)
            #清空帧文件夹
            for file in os.listdir(self.frame_dir):
                if file.startswith("frame_"):
                    os.remove(os.path.join(self.frame_dir, file))
            #清空网格文件夹
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
                # per_second 模式下不设总量上限，帧数可能超过 extract_frames 的默认 1000
                self.extract_frames(timestamps=timestamps, max_frames=len(timestamps))
            else:
                self.extract_frames()
            logger.info("开始拼接网格图...")
            image_paths = []
            groups = self.group_images()
            for idx, group in enumerate(groups, start=1):
                out_path = self.concat_images(group, f"grid_{idx}")
                if out_path:
                    image_paths.append(out_path)

            logger.info("📤 开始编码图像...")
            urls = self.encode_images_to_base64(image_paths)
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


