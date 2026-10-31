"""通用设置（spec 007，缓存边界字段见 spec 009 / ticket 07）。

单行表，``id`` 恒为 1，与 ``media_settings`` 同一套路。放这里的都是「跟具体
供应商/引擎无关、全局生效」的开关。
"""

from sqlalchemy import Column, Float, Integer, String

from app.db.engine import Base

#: 最大笔记并行任务数量：后端同时执行的笔记生成任务数上限。
#:
#: 默认 3（spec 009 决策 3，此前是 1）。原来一批任务实际串行的根因不在这个数字 ——
#: ``/generate_notes`` 用 FastAPI ``BackgroundTasks`` 逐条 ``add_task``，而 Starlette
#: 的 ``BackgroundTasks.__call__`` 是 ``for task in self.tasks: await task()``，
#: **严格串行**，所以不管这个值调多大，一批任务的实际并发度恒为 1。spec 009 把批量
#: 入口改成受并行闸门约束的分发池之后，这个数字才真正生效。
#:
#: 为什么是 3 而不是更高：上游供应商自带 ``DEFAULT_PROVIDER_CONCURRENCY = 4`` 的
#: 限流，SQLite 也只有一个写者；3 能拿到接近 3 倍的吞吐，又不至于把两者打到报错。
DEFAULT_MAX_PARALLEL_NOTES = 3

#: 允许的上限，防止手改配置把并发开到把机器/供应商打爆。
MAX_PARALLEL_NOTES_LIMIT = 8

#: 本地媒体缓存总量上限（字节）。默认 10 GiB；**0 表示不限**。
#: 长批量（200 个视频）下音视频 + 截图轻松写满磁盘，所以要有个容量维度，
#: 和时间维度（media_settings 的保留天数）互补。
DEFAULT_CACHE_LIMIT_BYTES = 10 * 1024**3

#: 缓存上限的允许最大值（1 TiB）：手改数据库写个天文数字会让「超限才清理」
#: 永远不触发，等同于悄悄关掉这个功能，所以设个天花板。
MAX_CACHE_LIMIT_BYTES = 1024**4

#: 磁盘剩余空间门禁（字节）。默认 5 GiB：剩余低于这个值就不再启动新任务，
#: 避免把磁盘写满导致 SQLite/ffmpeg 直接失败。
DEFAULT_MIN_FREE_DISK_BYTES = 5 * 1024**3

#: 磁盘门禁的允许最大值（1 TiB）。
MAX_MIN_FREE_DISK_BYTES = 1024**4

#: 连续失败多少次后熔断（暂停继续派发新任务）。默认 5；**0 表示关闭熔断**。
#: 供应商挂掉时，批量任务会一个接一个地失败刷屏，熔断让用户先修问题再继续。
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 5

#: 熔断阈值的允许最大值，防止误填导致熔断形同虚设。
MAX_CIRCUIT_BREAKER_THRESHOLD = 100


# ---------------------------------------------------------------------------
# ASR 输入上限（2026-10-17 补齐：此前完全没有上限，超长音频直接整段发给上游）
# ---------------------------------------------------------------------------

#: 单个音频文件允许转写的最大体积（MB）。**0 表示不限**。
#:
#: 为什么需要它：上游 ASR 端点普遍有硬性请求体上限（chat 风格还要再叠一层
#: base64 膨胀），超限时返回的是一个语焉不详的 413/400，用户看到的是「转写失败」，
#: 根本不知道是自己这条音频太长。本地先拦一次，错误信息才能指向真正的原因。
DEFAULT_ASR_MAX_FILE_MB = 0

#: 体积上限的允许最大值（20 GiB）：再大就不该走在线转写，应当先切段。
MAX_ASR_MAX_FILE_MB = 20 * 1024

#: 单个音频允许转写的最大时长（分钟）。**0 表示不限**。
#:
#: 体积与时长是两道独立的闸门：低码率音频可以「体积不大但长达数小时」，
#: 按体积拦不住；而 320kbps 的一小时音频体积已经很大但内容正常。两者都要有。
DEFAULT_ASR_MAX_DURATION_MINUTES = 0

#: 时长上限的允许最大值（24 小时）。
MAX_ASR_MAX_DURATION_MINUTES = 24 * 60

# ---------------------------------------------------------------------------
# 静音拆分（全局默认；端点上的同名字段视为「自定义覆盖」，见 runtime_limits）
# ---------------------------------------------------------------------------

#: 是否按静音边界切片。默认开：切出来的每片起点是真实语音边界，时间轴准确。
#: 关掉后跳过整轮「完整解码 + silencedetect」，改按字节等长切割 —— 长音频上
#: 这是实打实的耗时节省，代价是时间轴退化为等分估算。
DEFAULT_ASR_SILENCE_SPLIT = True

#: silencedetect 的噪声门限（dB）。越低越「听得见安静」，切得越碎。
DEFAULT_ASR_SILENCE_NOISE_DB = -30.0
MIN_ASR_SILENCE_NOISE_DB = -80.0
MAX_ASR_SILENCE_NOISE_DB = -5.0

#: 多长的停顿算一次「说完了」（秒）。
DEFAULT_ASR_MIN_SILENCE_SECONDS = 0.5
MIN_ASR_MIN_SILENCE_SECONDS = 0.05
MAX_ASR_MIN_SILENCE_SECONDS = 30.0

# ---------------------------------------------------------------------------
# LLM 请求体预算
# ---------------------------------------------------------------------------

#: 单次 LLM 请求允许的最大请求体（字节）。分块器（RequestChunker）与判定层的
#: 图片分批都以此为预算切分，所以它直接决定「一次能带几张图」。
#:
#: 默认 9 MiB 与 universal_gpt.GATEWAY_MAX_REQUEST_BYTES 的历史默认值一致；
#: 换成自建网关、上限更宽的用户可以在这里调大（上限 128 MiB）。
DEFAULT_LLM_MAX_REQUEST_BYTES = 9 * 1024**2
MIN_LLM_MAX_REQUEST_BYTES = 256 * 1024
MAX_LLM_MAX_REQUEST_BYTES = 128 * 1024**2

#: 判定层（哪些画面值得编入笔记）留给图片的字节预算。
#:
#: 必须显著低于请求体上限：历史事故里判定层贴着网关上限切批次，于是每个批次
#: 都大到被网关断连，而错误码还是误导性的 model_not_found。
DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES = 3 * 1024**2

#: 单次 LLM 调用的最大重试次数（含首次）。
DEFAULT_LLM_RETRY_ATTEMPTS = 3
MAX_LLM_RETRY_ATTEMPTS = 10

#: 重试的指数退避基数（秒）。
DEFAULT_LLM_RETRY_BACKOFF_SECONDS = 1.5
MAX_LLM_RETRY_BACKOFF_SECONDS = 60.0

# ---------------------------------------------------------------------------
# OCR / 插图阶段
# ---------------------------------------------------------------------------

#: OCR 阶段单帧处理的并发数。每帧要跑一次 ffmpeg 抽图 + 一次视觉模型调用，
#: 并发太高会同时压垮 CPU 与上游配额，所以默认 4 并设 32 的上限。
DEFAULT_OCR_STAGE_CONCURRENCY = 4
MAX_OCR_STAGE_CONCURRENCY = 32

#: 单篇笔记的插图上限。判定再准也要有硬闸门，否则一篇笔记会被图片淹没。
DEFAULT_NOTE_MAX_IMAGES = 30
MAX_NOTE_MAX_IMAGES = 500

# ---------------------------------------------------------------------------
# 失败预算（2026-10-17 第二轮补齐：此前只能改环境变量，改完还得重启后端）
# ---------------------------------------------------------------------------

#: 一条笔记任务失败后自动重试几次（首次之外）。**0 表示不重试**。
#:
#: 每次重试都重跑整条流水线（重下载、重转写、重调 LLM），一次重试可能就是
#: 十分钟和一笔 token 费用。所以这个数字不是「越大越稳」：网络抖动值得重试，
#: 而模型不存在的错误重试一百次也不会好（那类错误走 last_error_non_retryable，
#: 不消耗这个预算）。
DEFAULT_NOTE_MAX_RETRIES = 3
MAX_NOTE_MAX_RETRIES = 10

#: 重试退避基数（秒）：第 n 次重试等待 base * 3^(n-1)，即 5 / 15 / 45 秒。
#: 固定间隔会让上游在同一个限流窗口里被反复撞到。
DEFAULT_NOTE_RETRY_BACKOFF_SECONDS = 5.0
MAX_NOTE_RETRY_BACKOFF_SECONDS = 300.0

#: 撞上 429 后的全局冷却窗口（秒）。窗口内**所有**供应商请求一起停 ——
#: 429 说明配额已经打空，这时继续换着请求发只会延长封禁。
DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS = 300.0
MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS = 3600.0

#: 429 累计等待多久之后把任务交还队列（秒）。等满就 park，把 worker 让给
#: 别的任务 —— 配额恢复可能要几小时，而 worker 数量有限。
DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS = 3600.0
MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS = 24 * 3600.0

#: 429 等待期间每隔多久探一次配额（秒）。太小会自己把限流撞回去，
#: 太大会让配额恢复后还要空等很久。
DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS = 300.0
MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS = 10.0
MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS = 3600.0

#: 下载阶段的重试次数（yt-dlp 的 retries / fragment_retries）。
#:
#: 必须显式给值：yt-dlp 的 Python API 不套用命令行那套默认值，不设置时
#: HttpFD 拿到 None，``RetryManager`` 会把它当成 0 —— 一次网络抖动整条任务失败。
DEFAULT_DOWNLOAD_RETRIES = 3
MAX_DOWNLOAD_RETRIES = 10

#: 下载阶段的 socket 超时（秒）。B 站 CDN 镜像偶发卡住不返回，没有超时
#: 就是永久挂起 —— 用户看到的是任务永远停在「下载中」。
DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS = 30
MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS = 5
MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS = 300

# 2026-10-17 第三轮：截图编码与 ffmpeg 超时。
#
# 这三个值决定「一张图有多大」，而图片字节数直接决定一次请求能塞进几张图 ——
# 也就是 llm_max_request_bytes 的真实可用容量。原先截图固定 `-q:v 2` 且不缩放，
# 4K 视频一张截图就能吃掉几百 KB（base64 还要再涨 1/3）。
DEFAULT_SCREENSHOT_MAX_WIDTH = 0  # 0 = 保持原始分辨率（与历史行为一致）
MAX_SCREENSHOT_MAX_WIDTH = 7680
DEFAULT_SCREENSHOT_QUALITY = 2  # ffmpeg -q:v，1 最好、31 最差
MIN_SCREENSHOT_QUALITY = 1
MAX_SCREENSHOT_QUALITY = 31
DEFAULT_FFMPEG_TIMEOUT_SECONDS = 60
MIN_FFMPEG_TIMEOUT_SECONDS = 10
MAX_FFMPEG_TIMEOUT_SECONDS = 600
# 一次判定最多看多少个候选时间点：候选越多提示词越长，和图片抢同一份请求预算。
DEFAULT_OCR_MAX_JUDGE_CANDIDATES = 200
MAX_OCR_MAX_JUDGE_CANDIDATES = 1000
class GeneralSettings(Base):
    __tablename__ = "general_settings"

    id = Column(Integer, primary_key=True, default=1)
    max_parallel_notes = Column(
        Integer, nullable=False, default=DEFAULT_MAX_PARALLEL_NOTES
    )
    # 以下三列是 spec 009 / ticket 07 新增的「缓存边界」。
    # 都用 Integer 存字节/次数：SQLite 的 INTEGER 是 64 位，10 GiB 甚至 1 TiB
    # 都远在范围内，不需要 BigInteger（换库时 BigInteger 反而有兼容差异）。
    # nullable=True 是为了兼容老库迁移（ALTER TABLE 加的列在 SQLite 里只能是
    # 可空或带常量默认值），DAO 读取时统一走 normalize 兜底。
    cache_limit_bytes = Column(
        Integer, nullable=True, default=DEFAULT_CACHE_LIMIT_BYTES
    )
    min_free_disk_bytes = Column(
        Integer, nullable=True, default=DEFAULT_MIN_FREE_DISK_BYTES
    )
    circuit_breaker_threshold = Column(
        Integer, nullable=True, default=DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    )
    active_provider_id = Column(String, nullable=True)
    active_model_name = Column(String, nullable=True)

    # 2026-10-17：ASR 输入上限 + 静音拆分 + LLM 请求体预算 + OCR 阶段参数。
    # 与上面三个缓存边界列同样的写法：nullable=True 兼容老库的 ALTER TABLE，
    # 读的时候一律过 normalize 兜底。布尔用 Integer(0/1) 存 —— SQLite 的
    # ADD COLUMN 只接受常量默认值，Integer 最稳，换库时也不会有方言差异。
    asr_max_file_mb = Column(Integer, nullable=True, default=DEFAULT_ASR_MAX_FILE_MB)
    asr_max_duration_minutes = Column(
        Integer, nullable=True, default=DEFAULT_ASR_MAX_DURATION_MINUTES
    )
    asr_silence_split = Column(
        Integer, nullable=True, default=1 if DEFAULT_ASR_SILENCE_SPLIT else 0
    )
    asr_silence_noise_db = Column(
        Float, nullable=True, default=DEFAULT_ASR_SILENCE_NOISE_DB
    )
    asr_min_silence_seconds = Column(
        Float, nullable=True, default=DEFAULT_ASR_MIN_SILENCE_SECONDS
    )
    llm_max_request_bytes = Column(
        Integer, nullable=True, default=DEFAULT_LLM_MAX_REQUEST_BYTES
    )
    llm_judge_image_budget_bytes = Column(
        Integer, nullable=True, default=DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES
    )
    llm_retry_attempts = Column(Integer, nullable=True, default=DEFAULT_LLM_RETRY_ATTEMPTS)
    llm_retry_backoff_seconds = Column(
        Float, nullable=True, default=DEFAULT_LLM_RETRY_BACKOFF_SECONDS
    )
    ocr_stage_concurrency = Column(
        Integer, nullable=True, default=DEFAULT_OCR_STAGE_CONCURRENCY
    )
    note_max_images = Column(Integer, nullable=True, default=DEFAULT_NOTE_MAX_IMAGES)

    # 2026-10-17 第二轮：失败预算（任务重试 / 429 冷却 / 下载重试）。
    # 这些值原先散落在 os.getenv 里，改完必须重启后端，而且设置页完全看不到。
    note_max_retries = Column(Integer, nullable=True, default=DEFAULT_NOTE_MAX_RETRIES)
    note_retry_backoff_seconds = Column(
        Float, nullable=True, default=DEFAULT_NOTE_RETRY_BACKOFF_SECONDS
    )
    llm_rate_limit_cooldown_seconds = Column(
        Float, nullable=True, default=DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS
    )
    llm_rate_limit_max_wait_seconds = Column(
        Float, nullable=True, default=DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS
    )
    llm_rate_limit_resume_interval_seconds = Column(
        Float, nullable=True, default=DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS
    )
    download_retries = Column(Integer, nullable=True, default=DEFAULT_DOWNLOAD_RETRIES)
    download_socket_timeout_seconds = Column(
        Integer, nullable=True, default=DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS
    )

    # 2026-10-17 第三轮：截图编码（决定单图字节数，进而决定一次请求能带几张图）
    # 与 ffmpeg 超时（网络盘/长视频下 60 秒可能不够，超时会静默丢图）。
    screenshot_max_width = Column(
        Integer, nullable=True, default=DEFAULT_SCREENSHOT_MAX_WIDTH
    )
    screenshot_quality = Column(Integer, nullable=True, default=DEFAULT_SCREENSHOT_QUALITY)
    ffmpeg_timeout_seconds = Column(
        Integer, nullable=True, default=DEFAULT_FFMPEG_TIMEOUT_SECONDS
    )
    ocr_max_judge_candidates = Column(
        Integer, nullable=True, default=DEFAULT_OCR_MAX_JUDGE_CANDIDATES
    )