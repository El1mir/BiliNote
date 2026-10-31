import os
import threading
from enum import Enum

from app.transcriber.openai_asr import OpenAIASRTranscriber
from app.transcriber.whisper import WhisperTranscriber
from app.utils.logger import get_logger

logger = get_logger(__name__)

class TranscriberType(str, Enum):
    FAST_WHISPER = "fast-whisper"
    OPENAI_ASR = "openai-asr"

#: 引擎清单只剩两条路：本地 faster-whisper，或任何 openai 兼容的在线 ASR。
#: 必剪 / 快手 / Groq / MLX 已连同各自的实现一起移除 —— 前三个是随时会限流或
#: 关停的第三方免费接口，MLX 只在 macOS 上存在，而 openai 兼容端点已经能覆盖
#: 它们全部（用户填自己的 base_url 即可）。
AVAILABLE_TYPES = (TranscriberType.FAST_WHISPER, TranscriberType.OPENAI_ASR)

logger.info('初始化转录服务提供器')

# 转录器单例缓存
_transcribers = {key: None for key in AVAILABLE_TYPES}

# Cache instances together with their constructor configuration. The
# transcriber choice and Whisper model size can be changed from the frontend,
# so caching by transcriber type alone would keep using the first loaded model.
_transcriber_configs = {key: None for key in _transcribers}
_transcriber_init_lock = threading.Lock()

# 公共实例初始化函数
def _init_transcriber(key: TranscriberType, cls, *args, **kwargs):
    init_config = (args, tuple(sorted(kwargs.items())))
    with _transcriber_init_lock:
        instance = _transcribers[key]
        if instance is None or _transcriber_configs[key] != init_config:
            action = "创建" if instance is None else "按新配置重新创建"
            logger.info(f'{action} {cls.__name__} 实例: {key}')
            try:
                new_instance = cls(*args, **kwargs)
            except Exception as e:
                logger.error(f"{cls.__name__} 创建失败: {e}")
                raise
            _transcribers[key] = new_instance
            _transcriber_configs[key] = init_config
            logger.info(f'{cls.__name__} 创建成功')
        return _transcribers[key]

# 各类型获取方法
def get_openai_asr_transcriber(base_url: str, api_key: str, model: str,
                               timeout=600, chunk_size_mb=18, name: str = "",
                               api_style: str = "transcriptions",
                               max_speech_chunks: int = 120, silence_noise_db: float = -30.0,
                               min_silence_seconds: float = 0.5, max_rpm: float = 30,
                               chunk_concurrency: int | None = None,
                               silence_split: bool | None = None):
    """openai 兼容 ASR。所有参数都是标量，保证 _init_transcriber 的配置缓存能正确失效。

    api_style: transcriptions=Whisper 风格 /audio/transcriptions；chat=chat/completions + input_audio
    """
    return _init_transcriber(
        TranscriberType.OPENAI_ASR,
        OpenAIASRTranscriber,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        chunk_size_mb=chunk_size_mb,
        name=name,
        api_style=api_style,
        max_speech_chunks=max_speech_chunks,
        silence_noise_db=silence_noise_db,
        min_silence_seconds=min_silence_seconds,
        max_rpm=max_rpm,
        **({"chunk_concurrency": chunk_concurrency} if chunk_concurrency is not None else {}),
        **({"silence_split": silence_split} if silence_split is not None else {}),
    )

def get_whisper_transcriber(model_size="base", device="auto", compute_type=None,
                            cpu_threads=0, num_workers=1):
    return _init_transcriber(
        TranscriberType.FAST_WHISPER,
        WhisperTranscriber,
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        num_workers=num_workers,
    )

# 通用入口
def get_transcriber(transcriber_type="fast-whisper", model_size=None, device="auto",
                    transcriber_options=None, compute_type=None, cpu_threads=0,
                    num_workers=1):
    """
    获取指定类型的转录器实例

    参数:
        transcriber_type: 支持 "fast-whisper", "openai-asr"
        model_size: 模型大小，适用于 whisper；未提供时才读取环境变量默认值
        device: 设备类型（auto / cpu / cuda），仅 whisper 使用
        transcriber_options: openai-asr 的端点配置 dict（base_url/api_key/model/timeout/chunk_size_mb/name/api_style）
        compute_type: 计算类型（auto/float16/int8/...），仅 fast-whisper
        cpu_threads: CPU 推理线程数（0=自动），仅 fast-whisper
        num_workers: faster-whisper 推理 worker 数，仅 fast-whisper

    返回:
        对应类型的转录器实例
    """
    logger.info(f'请求转录器类型: {transcriber_type}')

    try:
        transcriber_enum = TranscriberType(transcriber_type)
    except ValueError:
        logger.warning(f'未知转录器类型 "{transcriber_type}"，默认使用 fast-whisper')
        transcriber_enum = TranscriberType.FAST_WHISPER

    # The explicit value normally comes from the persisted frontend setting and
    # must take precedence over Docker's startup default.
    whisper_model_size = model_size or os.environ.get("WHISPER_MODEL_SIZE", "base")

    if transcriber_enum == TranscriberType.FAST_WHISPER:
        return get_whisper_transcriber(whisper_model_size, device=device,
                                       compute_type=compute_type,
                                       cpu_threads=cpu_threads,
                                       num_workers=num_workers)

    options = transcriber_options or {}
    return get_openai_asr_transcriber(
        base_url=options.get("base_url", ""),
        api_key=options.get("api_key", ""),
        model=options.get("model", ""),
        timeout=options.get("timeout", 600),
        chunk_size_mb=options.get("chunk_size_mb", 18),
        name=options.get("name", ""),
        api_style=options.get("api_style", "transcriptions"),
        max_speech_chunks=options.get("max_speech_chunks", 120),
        silence_noise_db=options.get("silence_noise_db", -30.0),
        min_silence_seconds=options.get("min_silence_seconds", 0.5),
        max_rpm=options.get("max_rpm", 30),
        chunk_concurrency=options.get("chunk_concurrency"),
        silence_split=options.get("silence_split"),
    )
