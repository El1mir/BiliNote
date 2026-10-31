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
    case 'saving':
    case 'success':
      return 'task.stage.done'
    default:
      return null
  }
}

export const taskTitle = (task: Task): string =>
  task.audioMeta?.title || task.formData?.video_url || task.id
