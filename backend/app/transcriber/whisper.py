import os
from pathlib import Path
import shutil

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptSegment, TranscriptResult
from app.transcriber.base import Transcriber
from app.transcriber.whisper_models import (
    resolve_whisper_model,
    is_local_target,
    hf_cache_dirname,
)
from app.utils.logger import get_logger
from app.utils.path_helper import get_model_dir

from events import transcription_finished


'''
 Size of the model to use (tiny, tiny.en, base, base.en, small, small.en, distil-small.en, medium, medium.en, distil-medium.en, large-v1, large-v2, large-v3, large, distil-large-v2, distil-large-v3, large-v3-turbo, or turbo
'''
logger = get_logger(__name__)


def _register_nvidia_dll_dirs() -> None:
    """把 site-packages/nvidia/*/bin 加进 Windows DLL 搜索路径。

    faster-whisper 的 GPU 推理需要 cuDNN / cuBLAS 算子库（cudnn_ops64_9.dll 等）。
    这些库由 pip 的 nvidia-cudnn-cu12 / nvidia-cublas-cu12 包提供，默认落在
    site-packages/nvidia/<pkg>/bin，但 Python 3.8+ 默认搜索 DLL 时不扫 site-packages
    子目录。若不显式注册，加载会报
    "Could not locate cudnn_ops64_9.dll ... Invalid handle Cannot load symbol"，
    尽管 ctranslate2 自带的 cudnn64_9.dll 主库就在旁边。

    必须在本文件 import faster_whisper **之前**执行：ctranslate2 在首次导入时就
    固化 DLL 搜索路径，晚于导入再 add_dll_directory 就来不及了。两种手段都上：
    os.add_dll_directory（LoadLibraryEx 的专用搜索路径）+ 把 bin 目录前缀塞进
    PATH（ctranslate2 自己的 C++ 加载器会查 PATH）。
    """
    if os.name != "nt":
        return
    import site as _site

    added = set()
    for base in _site.getsitepackages():
        nvidia_root = Path(base) / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for pkg in ("cudnn", "cublas", "cuda_nvrtc"):
            bindir = nvidia_root / pkg / "bin"
            if bindir.is_dir() and str(bindir) not in added:
                added.add(str(bindir))
    for d in added:
        # best-effort：注册失败不影响继续（PATH 兜底仍在下面设置）
        try:
            os.add_dll_directory(d)
        except OSError as e:
            logger.warning(f"os.add_dll_directory 注册失败 {d}：{e}")
    # ctranslate2（C++ 侧）还认 PATH；把我们的 bin 目录前缀塞进去，避免搜索歧义
    if added:
        existing = os.environ.get("PATH", "")
        pieces = [p for p in added if p not in existing]
        if pieces:
            os.environ["PATH"] = os.pathsep.join(pieces) + os.pathsep + existing


# 必须在注册完 nvidia DLL 目录之后再导入 faster-whisper / ctranslate2
_register_nvidia_dll_dirs()
from faster_whisper import WhisperModel  # noqa: E402


def _cuda_available() -> bool:
    """faster-whisper 的 CUDA 能力探测，优先用 ctranslate2（真正的推理后端）。

    旧的 is_cuda_available/env_checker 走 torch.cuda.is_available()，但 torch 在
    轻量部署里可能不装，导致明明有显卡也被判成 CPU。ctranslate2 自带 CUDA 运行时，
    用它探测更可靠。
    """
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception as e:
        logger.warning(f"ctranslate2 CUDA 探测失败({e})，降级尝试 torch")
    try:
        import torch
        return torch.cuda.is_available()
    except Exception as e:
        logger.warning(f"torch CUDA 探测失败({e})，视为无 CUDA")
        return False

def resolve_compute_type(device: str, compute_type: str | None) -> str:
    """把配置里的 compute_type 归一化成 faster-whisper 能接受的类型。

    - compute_type 为 None 或 "auto"：按设备选 CUDA→float16（RTX 光追卡更稳 float16），
      CPU→int8（速度与精度折中最好）。
    - 显式值（float16/int8/int8_float16/float32...）原样透传。
    """
    if compute_type and compute_type != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def resolve_device(requested: str | None) -> str:
    """把配置里的设备选择解析成实际 device。

    requested:
      - None / "auto": 有 CUDA 用 GPU，否则 CPU；
      - "cuda": 尝试 GPU，加载或推理失败时回退 CPU（并在日志里说明）；
      - "cpu": 强制 CPU。
    返回 "cuda" 或 "cpu"。
    """
    if requested == "cpu":
        return "cpu"
    if requested in ("cuda", "auto", None):
        if _cuda_available():
            try:
                return "cuda"
            except Exception as e:
                logger.warning(f"CUDA 可用但初始化失败({e})，回退 CPU")
                return "cpu"
        if requested == "cuda":
            logger.warning("请求 CUDA 但不可用，回退 CPU")
        return "cpu"
    logger.warning(f"未知设备 {requested!r}，使用 auto")
    return resolve_device("auto")


# 历史遗留：之前用 modelscope 下载到自定义目录然后把路径传给 WhisperModel。
# 但 faster-whisper 1.1.1 的 download_model（utils.py:76）逻辑是：
# 只要 size_or_id 里含 "/" 就当 HF repo_id 处理，没有「本地目录直接返回」分支。
# 我们传 /app/models/whisper/whisper-tiny 进去 → 被当成不存在的 HF repo →
# 在线请求失败 → fallback local_files_only=True → HF cache 找不到（因为是
# modelscope 目录布局不是 HF）→ LocalEntryNotFoundError，误导说"离线模式"。
# 解法：彻底让 faster-whisper 自己处理下载——传 size name，配 download_root
# 作为 HF cache 根目录，HF_ENDPOINT 已经在 Dockerfile 里指到 hf-mirror.com，
# 国内能用。删掉 modelscope 那一套，避免布局不匹配。
class WhisperTranscriber(Transcriber):
    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = None,
        cpu_threads: int = 0,
        num_workers: int = 1,
    ):
        self.requested_device = device or "auto"
        self.device = resolve_device(self.requested_device)
        if self.requested_device.lower() not in ("cpu",) and self.device == "cpu":
            logger.warning("没有可用的 CUDA，使用 CPU 进行计算")

        self.compute_type = resolve_compute_type(self.device, compute_type)
        self.model_size = model_size
        # CPU 线程数：0 = 自动（用物理核心数的一个合理值）
        self.cpu_threads = self._effective_cpu_threads(cpu_threads)
        self.num_workers = max(1, num_workers)

        model_dir = get_model_dir("whisper")
        try:
            self.model = self._build_model(model_size, model_dir)
        except Exception as e:
            # 自愈：损坏 / 截断 / 半成品 cache → 删掉对应 HF cache 重下一次
            logger.warning(f"加载 whisper-{model_size} 失败：{e}；清理 cache 后重新下载")
            self._purge_cache(model_dir, model_size)
            self.model = self._build_model(model_size, model_dir)

    @staticmethod
    def _effective_cpu_threads(cpu_threads: int) -> int:
        """把 CPU 线程数归一化：0/负数 = 自动。

        自动值取「物理核心数的一半，且 1..16」——faster-whisper 默认 cpu_threads=0
        会让 CTranslate2 自己挑，但那通常在单核/低核机器上不够快；这里显式给一个
        能明显提速又不至于因为超线程争抢而劣化的值。用户可在设置里改。
        """
        if cpu_threads and cpu_threads > 0:
            return int(cpu_threads)
        try:
            cores = os.cpu_count() or 4
        except Exception:
            cores = 4
        return min(16, max(1, cores // 2))

    def _build_model(self, model_size: str, model_dir: str) -> WhisperModel:
        # resolve 把模型名映射成可加载标识：内置 size→Systran repo_id、自定义映射、
        # 直通的 repo_id 或本地路径。faster-whisper 对本地目录走 os.path.isdir 分支，
        # 对 repo_id 走 download_model(cache_dir=download_root)，两者都吃 model_size_or_path。
        target = resolve_whisper_model(model_size)
        return WhisperModel(
            model_size_or_path=target,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=self.num_workers,
            download_root=model_dir,
        )

    @staticmethod
    def _purge_cache(model_dir: str, model_size: str) -> None:
        """加载失败时清掉对应 HF cache 的 snapshot 目录，强制下次重下。

        关键：本地路径模型**绝不删**——那是用户自己的文件，删了就是数据丢失；
        只清 HF cache 布局 <model_dir>/models--{org}--{name}/（含历史 modelscope 目录）。
        """
        try:
            target = resolve_whisper_model(model_size)
        except Exception:
            target = model_size
        if is_local_target(target):
            logger.warning(
                f"模型 {model_size} 指向本地路径 {target}，加载失败不清理用户文件，请检查该目录是否完整"
            )
            return
        candidates = [
            Path(model_dir) / hf_cache_dirname(target),       # HF cache: models--org--name
            Path(model_dir) / f"whisper-{model_size}",        # 历史 modelscope 目录，顺手清掉
        ]
        for path in candidates:
            if path.exists():
                logger.info(f"清理损坏 cache: {path}")
                shutil.rmtree(path, ignore_errors=True)

    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        try:

            segments_raw, info = self.model.transcribe(file_path)

            segments = []
            full_text = ""

            for seg in segments_raw:
                text = seg.text.strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text
                ))

            result = TranscriptResult(
                language=info.language,
                full_text=full_text.strip(),
                segments=segments,
                raw=info
            )
            # self.on_finish(file_path, result)
            return result
        except Exception as e:
            # 绝不吞掉异常、更不返回 None：调用方（note.py:_transcribe_audio）
            # 拿到返回值后会立刻 asdict()，None 只会炸出一个与真实原因毫不相干的
            # "asdict() should be called on dataclass instances"，
            # 把「音频文件不存在」「显存不足」这类真正的原因彻底掩盖掉。
            logger.error(f"转写失败：{e}")
            raise

    def on_finish(self, video_path: str, result: TranscriptResult) -> None:
        print("转写完成")
        transcription_finished.send({
            "file_path": video_path,
        })
