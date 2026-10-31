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
