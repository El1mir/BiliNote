/**
 * 任务状态的小工具（spec 010）。
 *
 * **真正的判定在后端**（`backend/app/services/task_cleanup.py` 的运行登记表 + 状态文件）。
 * 前端这一份只用来把明显删不掉的入口置灰，避免用户点了才发现不行。
 *
 * 批量删除**不**用它在本地过滤：选中的 id 全部发给后端，由后端逐条返回
 * `deleted` / `failed`。两边各判一次必然会漂移，而漂移的表现就是「点了删除但什么
 * 也没发生」—— 用户最没法排查的那种。
 */

/** 终态。与后端 `task_cleanup.FINISHED_STATUSES` 保持一致。 */
export const FINISHED_TASK_STATUSES = ['SUCCESS', 'FAILED'] as const

/**
 * 已知的「进行中」状态。与后端 `app/enmus/task_status_enums.py` 的 `TaskStatus` 对齐。
 *
 * 这里**列举**而不是「不在终态里就算进行中」，是刻意的：后一种写法遇到后端新增的
 * 状态会一律判成进行中，于是一批任务在前端的删除入口全被置灰 —— 而用户没有别的
 * 出口，那就是死路。列举法遇到未知状态会放行，交给后端拒绝并给出原因，最坏也只是
 * 一次「任务仍在执行」的 toast。
 */
export const IN_FLIGHT_TASK_STATUSES = [
  'PENDING',
  'PARSING',
  'DOWNLOADING',
  'TRANSCRIBING',
  'SUMMARIZING',
  'FORMATTING',
  'SAVING',
] as const

/** 任务是否仍在执行。未知状态一律按「不在执行」处理（见上）。 */
export const isTaskInFlight = (status: string | null | undefined): boolean => {
  if (!status) return false
  return (IN_FLIGHT_TASK_STATUSES as readonly string[]).includes(status)
}
