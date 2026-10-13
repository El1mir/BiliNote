import request from '@/utils/request'

/** 高级（兼容性）字段的默认值，由后端下发，只读 */
export interface OcrDefaults {
  base_url: string
  model_name: string
  timeout: number
  max_file_mb: number
  max_pages: number
}

export interface OcrConfig {
  enabled: boolean
  base_url: string
  /** GET 返回的是打码值（带 *），保存时原样回传即代表不修改 */
  api_key: string
  model_name: string
  timeout: number
  max_file_mb: number
  max_pages: number
  /** 只读，不要回传 */
  _defaults: OcrDefaults
}

/** 保存 / 测试的请求体：只提交改动过的字段 */
export type OcrConfigInput = Partial<{
  enabled: boolean
  base_url: string
  api_key: string
  model_name: string
  timeout: number
  max_file_mb: number
  max_pages: number
}>

export interface OcrTestSuccess {
  ok: true
  message: string
  protocol: string
  model_name: string
  preview: string
  blocks: number
}

export interface OcrTestFailure {
  ok: false
  message: string
  /** 上游原始响应正文，务必原样展示 */
  detail: string
  code: string | null
  status_code: number | null
}

export type OcrTestResult = OcrTestSuccess | OcrTestFailure

export const getOcrConfig = async (): Promise<OcrConfig> => {
  return await request.get('/ocr_config')
}

export const updateOcrConfig = async (data: OcrConfigInput): Promise<OcrConfig> => {
  return await request.post('/ocr_config', data)
}

export const testOcrConfig = async (data: OcrConfigInput): Promise<OcrTestResult> => {
  // suppressToast：失败信息由页面自己用原始上游正文展示，避免全局红 toast 重复
  return await request.post('/ocr_config/test', data, { suppressToast: true })
}
