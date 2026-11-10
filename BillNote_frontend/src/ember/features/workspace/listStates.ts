/**
 * 「列表里没有卡片」有四种不同的样子，必须是四个不同的分支：
 *
 * - `loading`：第一次请求还没回来 → 骨架屏
 * - `error`：请求失败 → 错误态 + 重试（绝不能说「还没有历史记录」）
 * - `emptySearch`：搜索/筛选没命中 → 提示换关键词或清空筛选
 * - `empty`：真的一条都没有 → 引导去生成第一条
 * - `list`：有东西可显示
 *
 * 顺序即优先级：加载中不该先闪一下空态，失败也不该被当成"用户还没建过笔记"。
 */
export type ListDisplay = 'loading' | 'error' | 'emptySearch' | 'empty' | 'list'

export type ListDisplayInput = {
  /** 第一次请求进行中（已经有任务时不覆盖列表）。 */
  loading: boolean
  /** 上一次请求的失败原因。 */
  error?: string | null
  /** 过滤后还剩几条。 */
  count: number
  /** 是否处在搜索或非「全部」筛选下。 */
  narrowed: boolean
}

export const listDisplay = ({ loading, error, count, narrowed }: ListDisplayInput): ListDisplay => {
  if (loading) return 'loading'
  if (error) return 'error'
  if (count > 0) return 'list'
  return narrowed ? 'emptySearch' : 'empty'
}
