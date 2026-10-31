import type { BatchGenerateItem, BatchGeneratePayload } from '@/services/note'

/** 生成参数里除「这一批要什么」之外的部分（质量、场景、采样……）。 */
export type BatchProfile = Omit<
  BatchGeneratePayload,
  'platform' | 'items' | 'group_name' | 'merge' | 'merge_title' | 'merge_polish'
>

type Options = {
  /** spec 018 决策 3：合并任务不建组，只产生一条任务。 */
  merge: boolean
  groupName?: string
  mergeTitle?: string
  mergePolish?: boolean
}

/**
 * 组装 `/generate_notes` 的请求体。
 *
 * 单独抽成纯函数（而不是写在组件里）是为了让「合并 / 不合并」这两条路径
 * 能被单测钉住：合并时**不能**带 `group_name`（带了后端也忽略，但语义上
 * 让人以为会建组），非合并时**必须**带非空 `group_name`。
 */
export const buildBatchPayload = (
  profile: BatchProfile,
  items: BatchGenerateItem[],
  options: Options,
): BatchGeneratePayload => {
  if (options.merge) {
    return {
      platform: 'bilibili',
      items,
      ...profile,
      merge: true,
      merge_title: (options.mergeTitle ?? '').trim(),
      merge_polish: Boolean(options.mergePolish),
    }
  }
  return {
    platform: 'bilibili',
    items,
    ...profile,
    group_name: (options.groupName ?? '').trim(),
  }
}
