/**
 * 「任务是否还在进行中」的唯一判定（spec 010）。
 *
 * 真正的判定在后端（删除时后端还会再挡一次），前端这份只用来置灰按钮。
 * 未知状态一律按「不在进行中」处理：后端新增一个状态不该让一批任务在前端
 * 永远删不掉。
 */
export const FINISHED_TASK_STATUSES = ['SUCCESS', 'FAILED'] as const

/** 已知的「还在跑」状态（与后端 TaskStatus 一致，另加前端的 RUNNING）。 */
const IN_FLIGHT_STATUSES = [
  'PENDING',
  'PARSING',
  'DOWNLOADING',
  'TRANSCRIBING',
  'SUMMARIZING',
  'FORMATTING',
  'SAVING',
  'RUNNING',
] as const

export const isTaskInFlight = (status: string | null | undefined): boolean => {
  if (!status) return false
  return (IN_FLIGHT_STATUSES as readonly string[]).includes(status)
}

/** 后端写入的阶段详情：切片数 / 帧数 / 网格数这类计数。 */
export type TaskDetail = Record<string, unknown>

/**
 * 后端写入的阶段详情一律是 dict（`services/note.py` 的 `detail or {}`），
 * 里面是切片数 / 帧数 / 网格数这类计数。历史记录里可能残留字符串或数组，
 * 那些形状没有可渲染的字段，一律当「没有详情」处理，不要让调用方去猜。
 */
export const toDetailPayload = (value: unknown): TaskDetail | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as TaskDetail
}

/** `normalizeTaskStatus` 输出的形状：字段名与前端 `Task` 一致，不再是后端的下划线形状。 */
export type NormalizedTaskStatus = {
  status?: string
  stage: string | null
  stageLabel: string | null
  progress: number | null
  stageProgress: number | null
  message: string | null
  detail: TaskDetail | null
  updatedAt: string | null
}

/** `normalizeTaskStatus` 的入参：两套命名都认。 */
export type RawTaskStatus = {
  status?: string
  stage?: string | null
  stage_label?: string | null
  stageLabel?: string | null
  progress?: number | null
  stage_progress?: number | null
  stageProgress?: number | null
  message?: string | null
  detail?: unknown
  updated_at?: string | null
  updatedAt?: string | null
}

/**
 * 把轻量状态收敛成前端形状。
 *
 * 后端同一件事有两个名字（`stage_label` / `stageLabel`、`updated_at` /
 * `updatedAt`）：轻量端点是手写的，read model 端点由 pydantic 序列化。
 * 这里两套键都认，否则换个端点前端就整片字段变成 null。
 *
 * 它住在 utils 而不是 useTaskPolling 里，是因为轮询 Hook 会牵进 React / axios /
 * toast —— 那样这个纯数据映射就没法单独测了。
 */
export const normalizeTaskStatus = (lite: RawTaskStatus): NormalizedTaskStatus => ({
  status: lite.status,
  stage: lite.stage ?? null,
  stageLabel: lite.stage_label ?? lite.stageLabel ?? null,
  progress: typeof lite.progress === 'number' ? lite.progress : null,
  stageProgress:
    typeof lite.stage_progress === 'number'
      ? lite.stage_progress
      : typeof lite.stageProgress === 'number'
        ? lite.stageProgress
        : null,
  message: lite.message ?? null,
  detail: toDetailPayload(lite.detail),
  updatedAt: lite.updated_at ?? lite.updatedAt ?? null,
})
