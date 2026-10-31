import request from '@/utils/request.ts'

// opts.silent: 让本次请求失败时不弹全局红 toast（调用方自行 catch 处理，
// 比如 onboarding 撞名重试这种预期内失败）
interface CallOpts {
  silent?: boolean
}
const cfg = (o?: CallOpts) => (o?.silent ? { suppressToast: true } : undefined)

export interface ProviderSummary {
  id: string
  name: string
  logo: string
  api_key: string
  base_url: string
  type: string
  enabled: number
  max_concurrency?: number
  max_rpm?: number
}

export interface EnabledModelSummary {
  id: string
  provider_id: string
  model_name: string
  created_at?: string
}

export const getProviderList = async (opts?: CallOpts): Promise<ProviderSummary[]> => {
  return await request.get('/get_all_providers', cfg(opts))
}
export const getProviderById = async (id: string) => {
  return await request.get(`/get_provider_by_id/${id}`)
}
/** POST /add_provider —— 新建供应商时必填的四个字段，logo 可由后端补。 */
export interface ProviderCreatePayload {
  name: string
  base_url: string
  api_key: string
  type: string
  logo?: string
}

/** POST /update_provider —— 只提交要改的字段，id 必填。 */
export interface ProviderUpdatePayload {
  id: string
  name?: string
  base_url?: string
  api_key?: string
  type?: string
  logo?: string
  enabled?: number
}

/**
 * POST /connect_test —— 后端接受两种形态：按已存供应商 id + 模型名测，
 * 或按 provider_id 测整条链路。用联合类型写出来，调用点传错字段会当场报错。
 */
export type ConnectionTestPayload = { id: string; model: string } | { provider_id: string }

export const updateProviderById = async (data: ProviderUpdatePayload, opts?: CallOpts) => {
  return await request.post('/update_provider', data, cfg(opts))
}

export const addProvider = async (data: ProviderCreatePayload, opts?: CallOpts) => {
  return await request.post('/add_provider', data, cfg(opts))
}

export const testConnection = async (data: ConnectionTestPayload, opts?: CallOpts) => {
  return await request.post('/connect_test', data, cfg(opts))
}

/** 供应商侧真实可用的模型（走它的 /v1/models）。拿不到时后端把原因放在 error 里。 */
export interface RemoteModel {
  id: string
  owned_by?: string
}

export interface RemoteModelList {
  models: RemoteModel[]
  error?: string
}

export const fetchModels = async (providerId: string): Promise<RemoteModelList> => {
  return await request.get('/model_list/' + providerId)
}

/** 已保存（启用）的模型 —— 只有 id 与 model_name，比全量列表更适合按供应商渲染。 */
export interface SavedModel {
  id: number
  model_name: string
}

export const fetchEnableModelById = async (id: string): Promise<SavedModel[]> => {
  return await request.get('/model_enable/' + id)
}

export async function addModel(data: { provider_id: string; model_name: string }, opts?: CallOpts) {
  return request.post('/models', data, cfg(opts))
}

export const fetchEnableModels = async (): Promise<EnabledModelSummary[]> => {
  return await request.get('/model_list')
}

export const deleteModelById = async (modelId: number) => {
  return await request.get(`/models/delete/${modelId}`)
}
