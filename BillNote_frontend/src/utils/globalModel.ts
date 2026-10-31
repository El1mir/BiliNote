/**
 * 全局模型选择器的取值与候选构造（spec 019）。
 *
 * 选择器是「启用供应商 × 其下模型」的二维结构，落到原生 `<select>` 上必须压成一维
 * value：`providerId::modelName`。供应商 id 是 uuid、模型名里不会出现 `::`，所以
 * 拆回来是安全的；反过来，把供应商名和模型名拼成 label 只是给人看的。
 */
export const GLOBAL_MODEL_SEPARATOR = '::'

export type GlobalModelProvider = {
  provider_id: string
  provider_name: string
  models: { id: number; model_name: string }[]
}

export type GlobalModelOption = { value: string; label: string }

export function globalModelValue(providerId: string, modelName: string): string {
  return providerId + GLOBAL_MODEL_SEPARATOR + modelName
}

export function parseGlobalModelValue(
  value: string
): { providerId: string; modelName: string } | null {
  const index = value.indexOf(GLOBAL_MODEL_SEPARATOR)
  if (index <= 0) return null
  const providerId = value.slice(0, index)
  const modelName = value.slice(index + GLOBAL_MODEL_SEPARATOR.length)
  if (!providerId || !modelName) return null
  return { providerId, modelName }
}

/**
 * 候选按「供应商 → 模型」展开，顺序沿用后端下发顺序（供应商在前、模型保持库里的顺序），
 * 这样同一份数据在列表和选择器里看到的次序是一致的。没有模型的供应商直接跳过：
 * 一个空分组在选择器里只会变成一个选不动的标签。
 */
export function buildGlobalModelOptions(providers: GlobalModelProvider[]): GlobalModelOption[] {
  return providers
    .filter(provider => provider.models.length > 0)
    .flatMap(provider =>
      provider.models.map(model => ({
        value: globalModelValue(provider.provider_id, model.model_name),
        label: provider.provider_name + ' · ' + model.model_name,
      }))
    )
}
