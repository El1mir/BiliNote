import { describe, expect, it } from 'vitest'
import {
  buildGlobalModelOptions,
  globalModelValue,
  parseGlobalModelValue,
} from '../../src/utils/globalModel'

const providers = [
  {
    provider_id: 'p-1',
    provider_name: '主供应商',
    models: [
      { id: 1, model_name: 'gpt-4o-mini' },
      { id: 2, model_name: 'deepseek-chat' },
    ],
  },
  { provider_id: 'p-empty', provider_name: '空供应商', models: [] },
  { provider_id: 'p-2', provider_name: '备用', models: [{ id: 3, model_name: 'qwen-max' }] },
]

describe('全局模型选择器的取值', () => {
  it('value 可以在供应商与模型之间无损往返', () => {
    const value = globalModelValue('p-1', 'deepseek-chat')

    expect(value).toBe('p-1::deepseek-chat')
    expect(parseGlobalModelValue(value)).toEqual({ providerId: 'p-1', modelName: 'deepseek-chat' })
  })

  it('models 里带 :: 或缺字段的值一律判为无效', () => {
    expect(parseGlobalModelValue('')).toBeNull()
    expect(parseGlobalModelValue('p-1')).toBeNull()
    expect(parseGlobalModelValue('::model')).toBeNull()
    expect(parseGlobalModelValue('p-1::')).toBeNull()
  })

  it('候选按供应商顺序展开并跳过没有模型的供应商', () => {
    expect(buildGlobalModelOptions(providers)).toEqual([
      { value: 'p-1::gpt-4o-mini', label: '主供应商 · gpt-4o-mini' },
      { value: 'p-1::deepseek-chat', label: '主供应商 · deepseek-chat' },
      { value: 'p-2::qwen-max', label: '备用 · qwen-max' },
    ])
  })

  it('没有候选时返回空数组', () => {
    expect(buildGlobalModelOptions([])).toEqual([])
  })
})
