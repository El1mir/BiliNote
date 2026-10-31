import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { useTaskStore } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { downloadNoteArchives } from '@/services/note'
import {
  UNGROUPED_ID,
  assignTasksToGroup,
  createNoteGroup,
  deleteNoteGroup,
  listNoteGroups,
  renameNoteGroup,
  type NoteGroup,
} from '@/services/noteGroup'
import { sanitizeFileName, saveBlob } from '@/ember/features/workspace/archive'

/**
 * Which slice of the history is on screen: null means every task, UNGROUPED_ID means
 * only tasks that belong to no group, anything else is a real group id.
 */
export type GroupFilter = string | null

const toApiGroupId = (groupId: GroupFilter): string | null =>
  !groupId || groupId === UNGROUPED_ID ? null : groupId

/**
 * Note-group state for the history rail: the server is the source of truth, the store
 * holds the tasks. Assignment is written through the API and then re-read, because a
 * group's task_count lives on the server and the rail shows it.
 */
export function useNoteGroups() {
  const { t } = useI18n()
  const tasks = useTaskStore(state => state.tasks)
  const loadTasks = useTaskStore(state => state.loadTasks)

  const [groups, setGroups] = useState<NoteGroup[]>([])
  const [ungroupedCount, setUngroupedCount] = useState(0)
  const [maxGroups, setMaxGroups] = useState(200)
  const [maxNameLength, setMaxNameLength] = useState(64)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [activeGroupId, setActiveGroupId] = useState<GroupFilter>(null)
  const [checkedGroupIds, setCheckedGroupIds] = useState<string[]>([])
  const [draggingIds, setDraggingIds] = useState<string[]>([])
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const data = await listNoteGroups()
      setGroups(data.groups ?? [])
      setUngroupedCount(data.ungrouped_count ?? 0)
      if (data.max_groups) setMaxGroups(data.max_groups)
      if (data.max_name_length) setMaxNameLength(data.max_name_length)
    } catch (error) {
      console.warn('分组列表读取失败', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const createGroup = useCallback(
    async (name: string) => {
      const trimmed = name.trim()
      if (!trimmed) return false
      setBusy(true)
      try {
        await createNoteGroup(trimmed)
        await refresh()
        return true
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('group.createFailed'))
        return false
      } finally {
        setBusy(false)
      }
    },
    [refresh, t],
  )

  const renameGroup = useCallback(
    async (groupId: string, name: string) => {
      const trimmed = name.trim()
      if (!trimmed) return false
      setBusy(true)
      try {
        await renameNoteGroup(groupId, trimmed)
        await refresh()
        return true
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('group.renameFailed'))
        return false
      } finally {
        setBusy(false)
      }
    },
    [refresh, t],
  )

  const removeGroup = useCallback(
    async (groupId: string, deleteTasks: boolean) => {
      setBusy(true)
      try {
        const result = await deleteNoteGroup(groupId, deleteTasks)
        if (activeGroupId === groupId) setActiveGroupId(null)
        setCheckedGroupIds(current => current.filter(id => id !== groupId))
        await Promise.all([refresh(), loadTasks()])
        if (result?.skipped_tasks?.length) {
          toast(t('group.deleteSkipped', { count: result.skipped_tasks.length }))
        }
        return true
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('group.deleteFailed'))
        return false
      } finally {
        setBusy(false)
      }
    },
    [activeGroupId, loadTasks, refresh, t],
  )

  /** Move tasks into a group (or out of every group). Re-reads so counts stay honest. */
  const moveTasks = useCallback(
    async (taskIds: string[], groupId: GroupFilter) => {
      if (!taskIds.length) return false
      try {
        await assignTasksToGroup(taskIds, toApiGroupId(groupId))
        await Promise.all([refresh(), loadTasks()])
        return true
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('group.moveFailed'))
        return false
      }
    },
    [loadTasks, refresh, t],
  )

  const toggleGroupChecked = useCallback(
    (groupId: string) =>
      setCheckedGroupIds(current =>
        current.includes(groupId) ? current.filter(id => id !== groupId) : [...current, groupId],
      ),
    [],
  )

  const setAllChecked = useCallback(
    (checked: boolean) =>
      setCheckedGroupIds(checked ? [...groups.map(group => group.id), UNGROUPED_ID] : []),
    [groups],
  )

  /** Every completed note that sits in one of the checked groups, de-duplicated. */
  const selectedReadyTasks = useMemo(() => {
    if (!checkedGroupIds.length) return []
    const wanted = new Set(checkedGroupIds)
    return tasks.filter(task => {
      const key = task.groupId || UNGROUPED_ID
      return wanted.has(key) && String(task.status) === 'SUCCESS'
    })
  }, [checkedGroupIds, tasks])

  const downloadCheckedGroups = useCallback(async () => {
    if (!checkedGroupIds.length) return
    setDownloading(true)
    try {
      const ready = selectedReadyTasks
      if (!ready.length) {
        toast.error(t('group.archiveNone'))
        return
      }
      const blob = await downloadNoteArchives(ready.map(task => task.id))
      const onlyGroup = checkedGroupIds.length === 1 ? checkedGroupIds[0] : null
      const name =
        onlyGroup && onlyGroup !== UNGROUPED_ID
          ? (groups.find(group => group.id === onlyGroup)?.name ?? t('history.group.ungrouped'))
          : t('group.archiveBundle')
      saveBlob(blob, `${sanitizeFileName(name)}.zip`)
      toast.success(t('group.archiveDone', { count: ready.length }))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('history.archiveFailed'))
    } finally {
      setDownloading(false)
    }
  }, [checkedGroupIds, groups, selectedReadyTasks, t])

  /** Group id a task is displayed under — ungrouped tasks report the sentinel. */
  const groupKeyOf = useCallback(
    (groupId: string | null | undefined) => groupId || UNGROUPED_ID,
    [],
  )

  return {
    groups,
    ungroupedCount,
    maxGroups,
    maxNameLength,
    loading,
    busy,
    refresh,
    createGroup,
    renameGroup,
    removeGroup,
    moveTasks,
    activeGroupId,
    setActiveGroupId,
    checkedGroupIds,
    toggleGroupChecked,
    setAllChecked,
    downloadCheckedGroups,
    downloading,
    draggingIds,
    setDraggingIds,
    dropTargetId,
    setDropTargetId,
    groupKeyOf,
  }
}
