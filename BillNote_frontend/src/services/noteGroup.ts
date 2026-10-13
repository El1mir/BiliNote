import request from '@/utils/request'

/**
 * 笔记分组接口。分组的存储全在后端数据库（用户决策 m04951：前端不再做数据存储），
 * 这里只负责转发；`group_id` 传 `null` / `UNGROUPED_ID` / 空串一律表示「未分组」。
 */

/** 「未分组」虚拟区哨兵。真实组 id 是 uuid hex，不会撞上它。 */
export const UNGROUPED_ID = '__ungrouped__'

export interface NoteGroup {
  id: string
  name: string
  position: number
  /** 组内任务数；「未分组」虚拟区不带这个字段。 */
  task_count?: number
}

export interface NoteGroupList {
  groups: NoteGroup[]
  ungrouped_id: string
  ungrouped_count: number
  max_groups: number
  max_name_length: number
}

/** 列出所有分组，外加「未分组」虚拟区的成员数。 */
export const listNoteGroups = async (): Promise<NoteGroupList> => {
  return await request.get('/note_group')
}

/** 新建一个分组，返回新建的行。 */
export const createNoteGroup = async (name: string): Promise<{ group: NoteGroup }> => {
  return await request.post('/note_group', { name })
}

/** 重命名分组。 */
export const renameNoteGroup = async (
  groupId: string,
  name: string
): Promise<{ group: NoteGroup }> => {
  return await request.post('/note_group/rename', { group_id: groupId, name })
}

/** `POST /api/note_group/delete` 的响应体（spec 010）。 */
export interface GroupDeleteResult {
  /** 退回「未分组」的条数。 */
  affected: number
  /** 连组一起删掉的笔记。 */
  deleted_tasks: string[]
  /** 因仍在执行而跳过的笔记（会被退回未分组）。 */
  skipped_tasks: { task_id: string; reason: string }[]
}

/**
 * 删除分组（spec 010）。
 *
 * - `deleteTasks=false`（默认）：组内笔记退回未分组，笔记本身不删。
 * - `deleteTasks=true`：连组内笔记一起彻底删除。
 *
 * 组内**进行中**的笔记会被后端跳过并退回未分组，原因在 `skipped_tasks` 里。
 */
export const deleteNoteGroup = async (
  groupId: string,
  deleteTasks = false
): Promise<GroupDeleteResult> => {
  return await request.post('/note_group/delete', {
    group_id: groupId,
    delete_tasks: deleteTasks,
  })
}

/** 单个任务移入/移出分组（拖拽）。`groupId` 传 UNGROUPED_ID 即移出。 */
export const assignTaskToGroup = async (
  taskId: string,
  groupId: string | null
): Promise<{ task_id: string; group_id: string | null }> => {
  return await request.post('/note_group/assign', { task_id: taskId, group_id: groupId })
}

/** 批量移入/移出分组（多选拖拽）。 */
export const assignTasksToGroup = async (
  taskIds: string[],
  groupId: string | null
): Promise<{ affected: number }> => {
  return await request.post('/note_group/assign_batch', {
    task_ids: taskIds,
    group_id: groupId,
  })
}

/** 列出某个分组（不传 = 未分组）里的全部 task_id。 */
export const listGroupTaskIds = async (
  groupId: string | null
): Promise<{ task_ids: string[]; total: number }> => {
  return await request.get('/note_group/tasks', {
    params: groupId && groupId !== UNGROUPED_ID ? { group_id: groupId } : {},
  })
}
