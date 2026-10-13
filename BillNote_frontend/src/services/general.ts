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
  active_provider_id: string | null
  active_model_name: string | null
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
}

export const getGeneralSettings = async (): Promise<GeneralSettings> => {
  return await request.get('/general/settings')
}

export const activateGlobalModel = async (providerId: string, modelName: string): Promise<void> => {
  await request.post('/general/active_model', { provider_id: providerId, model_name: modelName })
}

export const updateGeneralSettings = async (
  patch: GeneralSettingsPatch
): Promise<GeneralSettings> => {
  return await request.post('/general/settings', patch)
}
