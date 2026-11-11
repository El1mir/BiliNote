/**
 * 地址栏里的「当前任务」（S2 状态可寻址）。
 *
 * 选中态的唯一来源是 URL：刷新、收藏、把链接发给别人之后，页面必须回到同一条
 * 笔记。store 里的 `currentTaskId` 只是它的内存镜像，用来让列表高亮和阅读区
 * 不必各自解析地址栏。
 *
 * 只通过 react-router 的 `useSearchParams` 读取 search 串，所以这里只做纯字符串
 * 处理，不碰 `window.location` —— 离开 Router 也能单测，换路由实现也不用改。
 */

/** 查询参数名。用 query 而不是 `/note/:id`：工作区只有一块阅读区，多一条路由反而多一层空态。 */
export const TASK_PARAM = 'task'

/** 归一化任务 id：去空白；空串、纯空白一律当作「没有选中」。 */
export function normalizeTaskId(value: string | null | undefined): string | null {
  const trimmed = (value ?? '').trim()
  return trimmed ? trimmed : null
}

/** 从 search 串（含不带 `?` 的写法）里读任务 id。 */
export function readTaskId(search: string): string | null {
  const raw = search.startsWith('?') ? search.slice(1) : search
  return normalizeTaskId(new URLSearchParams(raw).get(TASK_PARAM))
}

/** 写回任务 id，保留其它查询参数；传 null / 空白表示删掉这个参数。 */
export function writeTaskId(search: string, taskId: string | null): string {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const id = normalizeTaskId(taskId)
  if (id) params.set(TASK_PARAM, id)
  else params.delete(TASK_PARAM)
  const next = params.toString()
  return next ? '?' + next : ''
}

/**
 * 地址栏 id 的解析状态。
 *
 * `probe` 是「内存里没有这条时，有没有单独问过后端」的结果：列表接口只回元信息，
 * 刷新后直接深链到某条笔记时列表里本来就可能有它，所以不能一发现不在列表里就判定
 * 无效 —— 先问一次（`GET /api/task_status/{id}`），问过还没有才算 missing。
 */
export type TaskSelectionStatus = 'none' | 'waiting' | 'selected' | 'missing'

export function taskSelectionStatus(input: {
  urlTaskId: string | null
  /** 任务列表是否还在加载：加载中不下结论，否则会把合法深链误判成失效。 */
  listLoading: boolean
  knownIds: readonly string[]
  probe: 'unprobed' | 'found' | 'missing'
}): TaskSelectionStatus {
  const id = normalizeTaskId(input.urlTaskId)
  if (!id) return 'none'
  if (input.knownIds.includes(id)) return 'selected'
  if (input.probe === 'found') return 'selected'
  if (input.probe === 'missing') return 'missing'
  // 还没问过后端：列表加载完就是该问的信号，加载中则再等等。
  return 'waiting'
}

/** waiting 状态下是否需要发起这次单独查询。 */
export function shouldProbeTask(input: {
  status: TaskSelectionStatus
  listLoading: boolean
  probe: 'unprobed' | 'found' | 'missing'
}): boolean {
  return input.status === 'waiting' && !input.listLoading && input.probe === 'unprobed'
}
