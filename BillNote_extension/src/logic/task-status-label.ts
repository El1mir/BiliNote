import type { TaskStatus } from './types'

export const STAGE_LABELS: Record<TaskStatus, string> = {
  PENDING: '排队中',
  PARSING: '解析中',
  DOWNLOADING: '下载中',
  TRANSCRIBING: '转写中',
  SUMMARIZING: '总结中',
  FORMATTING: '格式化',
  SAVING: '保存中',
  SUCCESS: '完成',
  FAILED: '失败',
}

export function statusIcon(status: TaskStatus): string {
  return status === 'SUCCESS' ? '✓' : status === 'FAILED' ? '✕' : '◔'
}

export function statusLabel(status: TaskStatus): string {
  return STAGE_LABELS[status] ?? status
}
