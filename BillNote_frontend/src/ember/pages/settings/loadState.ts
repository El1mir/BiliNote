/**
 * 设置分区的读取状态判定（T-062 / 上游 UI 计划 §5 数据安全五项）。
 *
 * 背景：设置页的每个分区都用 useAsync 拉一份配置，然后把它当表单初始值。
 * 拉失败时 data 是 undefined，各分区又会给缺字段兜底（数值兜 0、字符串兜空串），
 * 于是"读不到"被渲染成了"配置就是空/0"，用户一按保存就把空值写回后端 ——
 * 对 base_prompt_override、下载 Cookie、保留天数这些字段都是静默的数据破坏。
 *
 * 所以判定收敛到这里，规则只有一条：**读不回来，就不给改**。
 * 抽成纯函数是为了能脱离 DOM 单测（本仓库测试栈没有 jsdom）。
 */

export type AsyncLoadState<T> = {
  data: T | undefined
  loading: boolean
  error: unknown
}

export type LoadPhase = 'loading' | 'error' | 'ready'

/** loading 优先：重试期间 error 已被 useAsync 清空，二者不会同时为真。 */
export function loadPhase(state: AsyncLoadState<unknown>): LoadPhase {
  if (state.error) return 'error'
  if (state.loading && state.data === undefined) return 'loading'
  return 'ready'
}

/**
 * 保存是否必须被拦住（读失败时 true）。
 * loading 不拦：此时表单还没渲染出来，保存按钮通常已是 disabled。
 */
export function shouldBlockSave(state: AsyncLoadState<unknown>): boolean {
  return Boolean(state.error)
}
