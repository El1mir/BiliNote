import type { MessageKey } from '@/ember/i18n/strings'
import type { Task, TaskStatus } from '@/store/taskStore'
import { toPercent } from '@/utils/progress'
import { isTaskInFlight } from '@/utils/taskStatus'

export type TaskTone = 'neutral' | 'ember' | 'accent' | 'success' | 'warning' | 'danger'

const STATUS_TONE: Record<string, TaskTone> = {
  PENDING: 'neutral',
  PARSING: 'ember',
  DOWNLOADING: 'ember',
  TRANSCRIBING: 'ember',
  SUMMARIZING: 'ember',
  FORMATTING: 'ember',
  SAVING: 'ember',
  RUNNING: 'ember',
  SUCCESS: 'success',
  FAILED: 'danger',
  FAILD: 'danger',
}

/** Normalize the backend's many in-flight statuses into one of five tones. */
export const statusTone = (status: TaskStatus | string | undefined): TaskTone =>
  STATUS_TONE[String(status ?? 'PENDING')] ?? 'neutral'

export const statusKey = (status: TaskStatus | string | undefined): MessageKey => {
  const value = String(status ?? 'PENDING')
  if (value === 'SUCCESS') return 'task.status.succeeded'
  if (value === 'FAILED' || value === 'FAILD') return 'task.status.failed'
  if (value === 'PENDING') return 'task.status.queued'
  return 'task.status.running'
}

/** Icon kind paired with `statusKey` — the second channel next to the colour. */
export type StatusIconKind = 'queued' | 'running' | 'done' | 'failed'

export const statusIconKind = (status: TaskStatus | string | undefined): StatusIconKind => {
  const value = String(status ?? 'PENDING')
  if (value === 'SUCCESS') return 'done'
  if (value === 'FAILED' || value === 'FAILD') return 'failed'
  if (value === 'PENDING') return 'queued'
  return 'running'
}

/** True while the task is still being produced — used to gate SSE subscriptions. */
export const isTaskActive = (task: Task | undefined): boolean => {
  if (!task) return false
  const value = String(task.status)
  // FAILD 是历史遗留的拼写错误，同样算终态（判定本身统一走 isTaskInFlight）。
  if (value === 'FAILD') return false
  return isTaskInFlight(value)
}

/** 0–1 progress, preferring the stage-level number when the task-level one is absent. */
export const taskProgress = (task: Task | undefined): number => {
  if (!task) return 0
  const stage = typeof task.stageProgress === 'number' ? task.stageProgress : null
  const overall = typeof task.progress === 'number' ? task.progress : null
  const raw = overall ?? stage ?? 0
  // 后端给的是 0–100；老数据里偶有 0–1 的小数，按比例放大后再交给 toPercent 收敛。
  const percent = toPercent(raw <= 1 ? raw * 100 : raw) ?? 0
  return percent / 100
}

/**
 * 后端 14 个阶段 → 一条文案。
 *
 * 阶段是进度条上"走到哪一步"的唯一来源：`success` / `failed` 不再被折叠成聚合值
 * （见 `backend/app/services/task_read_model.py` 的 `_PHASE_ALIASES`），所以这里
 * 必须认得每一个 —— 认不出就返回 null，让调用方回落到状态文案，绝不能猜成
 * "已完成"。历史数据里的 `success` 直接复用"完成"。
 */
export const stageKey = (stage: string | null | undefined): MessageKey | null => {
  switch (stage) {
    case 'queued':
      return 'task.stage.queued'
    case 'parsing':
    case 'downloading_video':
    case 'downloading_audio':
    case 'fetching_subtitles':
      return 'task.stage.downloading'
    case 'transcribing':
      return 'task.stage.transcribing'
    case 'planning_frames':
    case 'extracting_frames':
    case 'building_grids':
      return 'task.stage.frames'
    case 'summarizing':
      return 'task.stage.summarizing'
    case 'post_processing':
      return 'task.stage.postProcessing'
    case 'saving':
      return 'task.stage.saving'
    case 'success':
      return 'task.stage.done'
    case 'failed':
      return 'task.stage.failed'
    default:
      return null
  }
}

/**
 * 阶段详情的一行摘要：`{current: 3, total: 12, unit: 'frames'}` → `3 / 12 帧`。
 *
 * 后端的 detail 是自由 dict（切片数 / 帧数 / 网格数都塞在这里），形状不止一种，
 * 所以这里只挑能认出来的键；认不出来就当没有详情，卡片上不渲染空行。
 */
export const detailSummary = (
  detail: Record<string, unknown> | null | undefined,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string | null => {
  if (!detail) return null
  const current = typeof detail.current === 'number' ? detail.current : null
  const total = typeof detail.total === 'number' ? detail.total : null
  const unit = typeof detail.unit === 'string' ? detail.unit : null
  if (current !== null && total !== null) {
    const label = unit ? unitKey(unit) : null
    return label ? t(label, { current, total }) : `${current} / ${total}`
  }
  if (current !== null) return String(current)
  return null
}

const unitKey = (unit: string): MessageKey | null => {
  switch (unit) {
    case 'frames':
      return 'task.detail.frames'
    case 'grids':
      return 'task.detail.grids'
    case 'segments':
      return 'task.detail.segments'
    default:
      return null
  }
}

export const taskTitle = (task: Task): string =>
  task.audioMeta?.title || task.formData?.video_url || task.id
