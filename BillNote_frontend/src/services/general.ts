import request from '@/utils/request'

/**
 * 通用设置（spec 007；缓存边界字段见 spec 009 / ticket 07）。
 *
 * 后端 `get_general_settings()` 对每个可调字段都同时下发「当前值 + 上限 + 默认值」，
 * 前端不用把常量再抄一遍（抄了就会跟后端漂移）。三个缓存边界字段的语义：
 * - `cache_limit_bytes`：本地媒体缓存总量上限，**0 = 不限**；
 * - `min_free_disk_bytes`：磁盘剩余空间门禁，**0 = 不检查**；
 * - `circuit_breaker_threshold`：连续失败熔断阈值，**0 = 关闭熔断**。
 * 注意 0 是合法取值，不是「没设置」—— 所以不能把 0 当成空值丢掉。
 */
export interface GeneralSettings {
  max_parallel_notes: number
  /** 只读上限，由后端下发 */
  max_parallel_notes_limit: number

  cache_limit_bytes: number
  cache_limit_bytes_default: number
  cache_limit_bytes_limit: number

  min_free_disk_bytes: number
  min_free_disk_bytes_default: number
  min_free_disk_bytes_limit: number

  circuit_breaker_threshold: number
  circuit_breaker_threshold_default: number
  circuit_breaker_threshold_limit: number
  /* 全局模型不在这里（spec 019）：它指向「启用服务商下的某个模型」，候选由
     getGlobalModelOptions() 下发，指针只允许在『模型提供商』页改动。 */

  /* ---- 事务边界（2026-10-17）：决定「一次事务能做多大」，都在生成热路径上 ----
   *
   * 0 的语义各不相同，逐个看 hint：ASR 两个上限里 0 = 不限，其余字段 0 会被后端
   * 夹取到各自下限。前端只负责渲染后端下发的值/上下界，不抄常量。
   */
  /** 单个音频允许转写的最大体积（MB），0 = 不限 */
  asr_max_file_mb: number
  asr_max_file_mb_default: number
  asr_max_file_mb_limit: number
  /** 单个音频允许转写的最大时长（分钟），0 = 不限 */
  asr_max_duration_minutes: number
  asr_max_duration_minutes_default: number
  asr_max_duration_minutes_limit: number
  /** 全局默认的静音拆分开关；端点级配置优先 */
  asr_silence_split: boolean
  asr_silence_split_default: boolean
  asr_silence_noise_db: number
  asr_silence_noise_db_default: number
  asr_silence_noise_db_min: number
  asr_silence_noise_db_max: number
  asr_min_silence_seconds: number
  asr_min_silence_seconds_default: number
  asr_min_silence_seconds_min: number
  asr_min_silence_seconds_max: number

  /** 单次 LLM 请求体预算（字节）；网关硬上限仍会再收敛一次 */
  llm_max_request_bytes: number
  llm_max_request_bytes_default: number
  llm_max_request_bytes_min: number
  llm_max_request_bytes_max: number
  /** 判定层留给图片的字节预算；上界由 llm_max_request_bytes 推导 */
  llm_judge_image_budget_bytes: number
  llm_judge_image_budget_bytes_default: number
  llm_retry_attempts: number
  llm_retry_attempts_default: number
  llm_retry_attempts_limit: number
  llm_retry_backoff_seconds: number
  llm_retry_backoff_seconds_default: number
  llm_retry_backoff_seconds_limit: number

  /** OCR 阶段并发（每帧一次 ffmpeg + 一次视觉模型调用） */
  ocr_stage_concurrency: number
  ocr_stage_concurrency_default: number
  ocr_stage_concurrency_limit: number
  /** 单篇笔记最多编入多少张截图 */
  note_max_images: number
  note_max_images_default: number
  note_max_images_limit: number

  /* ---- 截图编码（2026-10-17 第三轮）：决定「一张图有多大」 ----
   *
   * 图片字节数直接决定 llm_max_request_bytes 能塞进几张图。4K 视频原尺寸截图
   * 一张就有几百 KB，base64 再涨 1/3 —— 所以宽度与质量要和请求预算一起看。
   * screenshot_max_width 为 0 表示保持原始分辨率（历史行为）。
   */
  screenshot_max_width: number
  screenshot_max_width_default: number
  screenshot_max_width_limit: number
  screenshot_quality: number
  screenshot_quality_default: number
  screenshot_quality_min: number
  screenshot_quality_max: number
  ffmpeg_timeout_seconds: number
  ffmpeg_timeout_seconds_default: number
  ffmpeg_timeout_seconds_min: number
  ffmpeg_timeout_seconds_max: number
  ocr_max_judge_candidates: number
  ocr_max_judge_candidates_default: number
  ocr_max_judge_candidates_limit: number

  /* ---- 失败预算（2026-10-17 第二轮）：一次失败之后怎么重来 ----
   *
   * 这些值原先只认环境变量，改完必须重启后端。现在同样走运行时门面，保存即生效。
   * 注意 `note_max_retries` 与 `llm_retry_attempts` 是两层不同的重试：前者重跑
   * **整条流水线**（重下载、重转写、重调模型），后者只重试**单次请求**。
   */
  /** 任务失败后重跑整条流水线的次数，0 = 不重试 */
  note_max_retries: number
  note_max_retries_default: number
  note_max_retries_limit: number
  /** 重试退避基数（秒）：第 n 次等待 base × 3^(n-1) */
  note_retry_backoff_seconds: number
  note_retry_backoff_seconds_default: number
  note_retry_backoff_seconds_limit: number
  /** 撞上 429 后的全局冷却窗口（秒） */
  llm_rate_limit_cooldown_seconds: number
  llm_rate_limit_cooldown_seconds_default: number
  llm_rate_limit_cooldown_seconds_limit: number
  /** 429 累计等待多久后把任务交还队列（秒） */
  llm_rate_limit_max_wait_seconds: number
  llm_rate_limit_max_wait_seconds_default: number
  llm_rate_limit_max_wait_seconds_limit: number
  /** 429 等待期间的配额探测间隔（秒） */
  llm_rate_limit_resume_interval_seconds: number
  llm_rate_limit_resume_interval_seconds_default: number
  llm_rate_limit_resume_interval_seconds_min: number
  llm_rate_limit_resume_interval_seconds_max: number
  /** 下载阶段的重试次数（yt-dlp retries / fragment_retries） */
  download_retries: number
  download_retries_default: number
  download_retries_limit: number
  /** 下载阶段的 socket 超时（秒）；不允许 0，否则卡住的连接永不超时 */
  download_socket_timeout_seconds: number
  download_socket_timeout_seconds_default: number
  download_socket_timeout_seconds_min: number
  download_socket_timeout_seconds_max: number
}

/**
 * 部分更新请求体：只放要改的字段。
 * 后端把「未传（undefined / 不出现）」解释为「保持原值」，所以这里**不能**
 * 用 `null` 表达清零 —— 想关掉缓存上限或熔断请显式传 `0`。
 */
export interface GeneralSettingsPatch {
  max_parallel_notes?: number
  cache_limit_bytes?: number
  min_free_disk_bytes?: number
  circuit_breaker_threshold?: number
  asr_max_file_mb?: number
  asr_max_duration_minutes?: number
  asr_silence_split?: boolean
  asr_silence_noise_db?: number
  asr_min_silence_seconds?: number
  llm_max_request_bytes?: number
  llm_judge_image_budget_bytes?: number
  llm_retry_attempts?: number
  llm_retry_backoff_seconds?: number
  ocr_stage_concurrency?: number
  note_max_images?: number
  note_max_retries?: number
  note_retry_backoff_seconds?: number
  llm_rate_limit_cooldown_seconds?: number
  llm_rate_limit_max_wait_seconds?: number
  llm_rate_limit_resume_interval_seconds?: number
  download_retries?: number
  download_socket_timeout_seconds?: number
  screenshot_max_width?: number
  screenshot_quality?: number
  ffmpeg_timeout_seconds?: number
  ocr_max_judge_candidates?: number
}

export const getGeneralSettings = async (): Promise<GeneralSettings> => {
  return await request.get('/general/settings')
}

export const activateGlobalModel = async (providerId: string, modelName: string): Promise<void> => {
  await request.post('/general/active_model', { provider_id: providerId, model_name: modelName })
}

/** 全局模型候选：只含启用服务商，且服务商下必须有模型（后端已过滤）。 */
export type GlobalModelSelection = { provider_id: string; model_name: string }

export type GlobalModelProviderGroup = {
  provider_id: string
  provider_name: string
  models: { id: number; model_name: string }[]
}

export type GlobalModelOptions = {
  active: GlobalModelSelection | null
  providers: GlobalModelProviderGroup[]
}

export const getGlobalModelOptions = async (): Promise<GlobalModelOptions> => {
  return await request.get('/general/active_model/options')
}

export const updateGeneralSettings = async (
  patch: GeneralSettingsPatch
): Promise<GeneralSettings> => {
  return await request.post('/general/settings', patch)
}
