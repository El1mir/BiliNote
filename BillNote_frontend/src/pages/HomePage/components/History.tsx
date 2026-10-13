import NoteHistory from '@/pages/HomePage/components/NoteHistory.tsx'
import GroupPanel from '@/pages/HomePage/components/GroupPanel.tsx'
import { useTaskStore } from '@/store/taskStore'
import { Clock, Download, RotateCcw, Trash2 } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { Button } from '@/components/ui/button.tsx'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog.tsx'
import { useCallback, useEffect, useState } from 'react'
import { downloadNoteArchives, retryFailedTasks } from '@/services/note'
import {
  UNGROUPED_ID,
  assignTaskToGroup,
  assignTasksToGroup,
  createNoteGroup,
  deleteNoteGroup,
  listGroupTaskIds,
  listNoteGroups,
  renameNoteGroup,
  type NoteGroup,
} from '@/services/noteGroup.ts'
import { sanitizeFileName } from '@/utils/fileName.ts'
import toast from 'react-hot-toast'

/** 「未分组」哨兵 → 后端要的 null。真实组 id 原样透传。 */
const toApiGroupId = (groupId: string | null): string | null =>
  groupId === UNGROUPED_ID ? null : groupId

/** 触发一次浏览器下载。文件名已清洗，zip 内部顶层目录由后端按组名写入。 */
const saveBlob = (blob: Blob, fileName: string) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  // Chromium may start handling the download asynchronously; revoking in the same
  // task can leave the browser with a success toast but no actual download.
  window.setTimeout(() => {
    URL.revokeObjectURL(url)
    link.remove()
  }, 1000)
}

/**
 * 重试条数的确认阈值（决策 4）。超过它就先弹确认 ——
 * 重试会真的重新下载 + 转写，点错一次的代价是几十条长任务一起跑。
 */
const RETRY_CONFIRM_THRESHOLD = 200

const History = () => {
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const tasks = useTaskStore(state => state.tasks)
  const removeTasks = useTaskStore(state => state.removeTasks)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  // —— 分组状态 ——
  const [groups, setGroups] = useState<NoteGroup[]>([])
  const [ungroupedCount, setUngroupedCount] = useState(0)
  const [maxGroups, setMaxGroups] = useState(200)
  const [maxNameLength, setMaxNameLength] = useState(30)
  const [groupsLoading, setGroupsLoading] = useState(true)
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null)
  /** 该组内任务的 id；null 表示「不按组过滤」。 */
  const [activeTaskIds, setActiveTaskIds] = useState<string[] | null>(null)
  const [checkedGroupIds, setCheckedGroupIds] = useState<string[]>([])

  // —— 拖拽 / 新建 / 下载的状态 ——
  const [draggingIds, setDraggingIds] = useState<string[]>([])
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)
  /**
   * 收起的分组 id。**默认全部收起**（用户决策 m08608 第三条）：195 篇笔记
   * 一屏全铺开既找不到东西也拖不动。`null` 表示「还没初始化」—— 分组列表
   * 第一次加载回来时才把每个组塞进去，这样「默认收起」只发生一次，
   * 不会把用户手动展开过的组又收回去。
   */
  const [collapsed, setCollapsed] = useState<string[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [downloadingSelected, setDownloadingSelected] = useState(false)
  const [downloadingSingle, setDownloadingSingle] = useState(false)
  /** 待确认删除的分组；非 null 时弹确认框。 */
  const [pendingDelete, setPendingDelete] = useState<NoteGroup | null>(null)
  /** 删除分组时是否连组内笔记一起删（默认只解绑，保持原有行为）。 */
  const [deleteGroupTasks, setDeleteGroupTasks] = useState(false)
  const [deletingSelected, setDeletingSelected] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [confirmRetryOpen, setConfirmRetryOpen] = useState(false)

  const refreshGroups = useCallback(async () => {
    try {
      const data = await listNoteGroups()
      const next = data.groups ?? []
      setGroups(next)
      setUngroupedCount(data.ungrouped_count ?? 0)
      if (data.max_groups) setMaxGroups(data.max_groups)
      if (data.max_name_length) setMaxNameLength(data.max_name_length)
      // 首次拿到分组列表 → 全部收起一次。之后再刷新不回退用户的展开操作。
      setCollapsed(prev => (prev === null ? [...next.map(group => group.id), UNGROUPED_ID] : prev))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '分组列表加载失败')
      // 拉取失败也要脱离「未初始化」，否则用户永远展开不了任何分组。
      setCollapsed(prev => prev ?? [])
    } finally {
      setGroupsLoading(false)
    }
  }, [])

  useEffect(() => {
    // StrictMode 会跑两遍 effect，这个请求幂等，多打一次也无妨。
    void refreshGroups()
  }, [refreshGroups])

  /** 选中某个分组（UNGROUPED_ID = 未分组）；传 null 回到「全部」。 */
  const selectGroup = useCallback(async (groupId: string | null) => {
    setActiveGroupId(groupId)
    if (groupId === null) {
      setActiveTaskIds(null)
      return
    }
    try {
      const data = await listGroupTaskIds(toApiGroupId(groupId))
      setActiveTaskIds(data.task_ids ?? [])
    } catch (error) {
      setActiveTaskIds([])
      toast.error(error instanceof Error ? error.message : '读取分组任务失败')
    }
  }, [])

  const visibleTasks = activeTaskIds ? tasks.filter(task => activeTaskIds.includes(task.id)) : tasks
  /**
   * 「全选」只覆盖**当前可见**的任务。选中一批看不见的笔记、再顺手点「删除选中」，
   * 是最容易误伤的操作 —— 而删除是不可撤销的。
   */
  const allVisibleSelected =
    visibleTasks.length > 0 && visibleTasks.every(task => selectedIds.includes(task.id))

  // 删掉任务 / 换组后，别让已消失的 id 留在选中集合里。
  useEffect(() => {
    const alive = new Set(tasks.map(task => task.id))
    setSelectedIds(prev => {
      const next = prev.filter(id => alive.has(id))
      return next.length === prev.length ? prev : next
    })
  }, [tasks])

  /** 让某条任务乐观地换组，返回可回滚的快照。 */
  const patchTaskGroupLocally = (taskIds: string[], groupId: string | null) => {
    const { tasks: snapshot, updateTaskContent } = useTaskStore.getState()
    const groupName = groupId ? (groups.find(g => g.id === groupId)?.name ?? '') : ''
    taskIds.forEach(id =>
      updateTaskContent(id, { groupId, groupName } as never as Parameters<
        typeof updateTaskContent
      >[1])
    )
    return snapshot
  }

  const restoreTasks = (snapshot: ReturnType<typeof useTaskStore.getState>['tasks']) => {
    useTaskStore.setState({ tasks: snapshot })
  }

  /** 拖拽落点：把拖着的（或批量选中的）任务移进目标组。 */
  const dropOnGroup = async (targetRowId: string) => {
    setDropTargetId(null)
    const ids = draggingIds
    setDraggingIds([])
    if (!ids.length) return

    const targetGroupId = toApiGroupId(targetRowId)
    const snapshot = patchTaskGroupLocally(ids, targetGroupId)
    try {
      if (ids.length === 1) {
        await assignTaskToGroup(ids[0], targetGroupId)
      } else {
        await assignTasksToGroup(ids, targetGroupId)
      }
      const label = targetGroupId
        ? (groups.find(g => g.id === targetGroupId)?.name ?? '分组')
        : '未分组'
      toast.success(`已把 ${ids.length} 条笔记移入「${label}」`)
      await refreshGroups()
    } catch (error) {
      restoreTasks(snapshot)
      toast.error(error instanceof Error ? error.message : '移动分组失败')
    }
  }

  const handleCreateGroup = async (name: string) => {
    setCreating(true)
    try {
      await createNoteGroup(name)
      await refreshGroups()
      toast.success(`已新建分组「${name}」`)
    } catch (error) {
      // 后端 MAX_GROUPS / 重名 / 超长都会走这里，直接把 message 抛给用户。
      toast.error(error instanceof Error ? error.message : '新建分组失败')
    } finally {
      setCreating(false)
    }
  }

  const handleRenameGroup = async (groupId: string, name: string) => {
    if (name.length > maxNameLength) {
      toast.error(`分组名最多 ${maxNameLength} 个字`)
      return
    }
    try {
      await renameNoteGroup(groupId, name)
      await refreshGroups()
      toast.success('分组已重命名')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '重命名失败')
    }
  }

  /**
   * 删除分组（spec 010）：由对话框里的复选框决定「只删组」还是「连组内笔记一起删」。
   *
   * 组内**进行中**的笔记后端会跳过并退回未分组 —— 必须如实说出来，否则用户会以为
   * 它们也删掉了，下次刷新却又看见它们。
   */
  const confirmDeleteGroup = async () => {
    const group = pendingDelete
    const alsoDeleteTasks = deleteGroupTasks
    setPendingDelete(null)
    setDeleteGroupTasks(false)
    if (!group) return
    try {
      const res = await deleteNoteGroup(group.id, alsoDeleteTasks)
      if (activeGroupId === group.id) {
        setActiveGroupId(null)
        setActiveTaskIds(null)
      }
      setCheckedGroupIds(prev => prev.filter(id => id !== group.id))
      if (alsoDeleteTasks) {
        const deletedIds = res?.deleted_tasks ?? []
        setSelectedIds(prev => prev.filter(id => !deletedIds.includes(id)))
      }
      await refreshGroups()
      if (alsoDeleteTasks) {
        const removed = res?.deleted_tasks?.length ?? 0
        const skipped = res?.skipped_tasks?.length ?? 0
        toast.success(
          skipped
            ? `已删除分组「${group.name}」及其 ${removed} 篇笔记，${skipped} 篇仍在生成中，已移入未分组`
            : `已删除分组「${group.name}」及其 ${removed} 篇笔记`
        )
      } else {
        toast.success(
          res?.affected
            ? `已删除分组「${group.name}」，${res.affected} 条笔记已移入未分组`
            : `已删除分组「${group.name}」`
        )
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '删除分组失败')
    }
  }

  /**
   * 批量删除选中的笔记（spec 010）。
   *
   * 后端逐条隔离，所以**必须**如实汇报失败条目：批量删除最忌讳「看起来成功了，
   * 其实有几条没删」。失败原因由后端给（多数是「任务仍在执行」）。
   */
  const deleteSelected = async () => {
    if (!selectedIds.length || deletingSelected) return
    const ids = [...selectedIds]
    setDeletingSelected(true)
    try {
      const result = await removeTasks(ids)
      setSelectedIds([])
      if (!result) {
        toast.error('批量删除请求失败，请稍后重试')
        return
      }
      const failed = result.failed ?? []
      if (result.deleted.length) toast.success(`已删除 ${result.deleted.length} 篇笔记`)
      if (failed.length) {
        // 只报第一条原因，避免一次弹出一屏 toast。
        toast.error(
          `${failed.length} 篇未能删除：${failed[0].error}${failed.length > 1 ? ' 等' : ''}`
        )
      } else if (!result.deleted.length) {
        toast('没有需要删除的笔记')
      }
    } finally {
      setDeletingSelected(false)
    }
  }

  /**
   * 当前可见范围对应的重试请求参数（决策 1）。
   * `activeGroupId === null` 是「全部分组」视图 = 整库；未分组传 null。
   */
  const retryScope = (): { scope: 'all' | 'group'; groupId: string | null } => {
    if (!activeGroupId) return { scope: 'all', groupId: null }
    return { scope: 'group', groupId: toApiGroupId(activeGroupId) }
  }

  const runRetryFailed = async () => {
    if (retrying) return
    const { scope, groupId } = retryScope()
    setRetrying(true)
    try {
      const result = await retryFailedTasks(scope, groupId)
      // 如实汇报三类结果：重试成功、跳过（带原因）、已不存在。
      // 静默跳过等于让用户以为全都重试了。
      if (result.requeued.length) {
        toast.success(`${result.requeued.length} 篇失败笔记已重新排队`)
      }
      if (result.skipped.length) {
        toast(`${result.skipped.length} 篇未重试：${result.skipped[0].reason}`)
      }
      if (result.missing.length) {
        toast.error(`${result.missing.length} 篇已不存在，已跳过`)
      }
      if (!result.requeued.length && !result.skipped.length && !result.missing.length) {
        toast('当前范围内没有失败的任务')
      }
    } catch (e) {
      // 门禁类错误（转写模型未就绪 / 磁盘不足）后端已给出原因，拦截器会自动弹 toast；
      // 这里只在没有业务码时兜底，避免重复提示。
      console.warn('重试失败任务出错', e)
    } finally {
      setRetrying(false)
      setConfirmRetryOpen(false)
    }
  }

  /** 超过阈值先确认；否则直接跑（决策 4）。 */
  const requestRetryFailed = () => {
    if (visibleTasks.length > RETRY_CONFIRM_THRESHOLD) {
      setConfirmRetryOpen(true)
      return
    }
    void runRetryFailed()
  }

  /** 单个分组的「下载本组笔记」：只收该组内部已生成的笔记。 */
  const downloadOneGroup = async (rowId: string) => {
    const groupName =
      rowId === UNGROUPED_ID ? '未分组' : (groups.find(g => g.id === rowId)?.name ?? '分组')
    setDownloadingSingle(true)
    try {
      const data = await listGroupTaskIds(toApiGroupId(rowId))
      const idSet = new Set(data.task_ids ?? [])
      const ready = tasks.filter(task => idSet.has(task.id) && task.status === 'SUCCESS')
      const skipped = (data.task_ids ?? []).length - ready.length
      if (!ready.length) {
        toast.error(
          `「${groupName}」还没有已生成的笔记${skipped ? `（${skipped} 条未生成，已跳过）` : ''}`
        )
        return
      }
      if (skipped > 0) toast(`已跳过 ${skipped} 条尚未生成笔记的任务`, { icon: '⚠️' })
      const blob = await downloadNoteArchives(ready.map(task => task.id))
      saveBlob(blob, `${sanitizeFileName(groupName)}.zip`)
      toast.success(`已下载「${groupName}」的 ${ready.length} 篇笔记`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '分组归档下载失败')
    } finally {
      setDownloadingSingle(false)
    }
  }

  const toggleGroupChecked = (groupId: string) =>
    setCheckedGroupIds(prev =>
      prev.includes(groupId) ? prev.filter(id => id !== groupId) : [...prev, groupId]
    )

  /** 多组下载：并集去重，只收 SUCCESS。 */
  const downloadCheckedGroups = async () => {
    if (!checkedGroupIds.length) return
    setDownloadingSelected(true)
    try {
      const results = await Promise.all(
        checkedGroupIds.map(groupId => listGroupTaskIds(toApiGroupId(groupId)))
      )
      const idSet = new Set<string>()
      results.forEach(res => (res.task_ids ?? []).forEach(id => idSet.add(id)))
      const ready = tasks.filter(task => idSet.has(task.id) && task.status === 'SUCCESS')
      const skipped = idSet.size - ready.length
      if (!ready.length) {
        toast.error(
          `所选分组里还没有已生成的笔记${skipped ? `（${skipped} 条未生成，已跳过）` : ''}`
        )
        return
      }
      if (skipped > 0) toast(`已跳过 ${skipped} 条尚未生成笔记的任务`, { icon: '⚠️' })
      const blob = await downloadNoteArchives(ready.map(task => task.id))
      const fileName =
        checkedGroupIds.length === 1
          ? `${sanitizeFileName(
              checkedGroupIds[0] === UNGROUPED_ID
                ? '未分组'
                : (groups.find(g => g.id === checkedGroupIds[0])?.name ?? '笔记归档')
            )}.zip`
          : `笔记归档-${ready.length}篇.zip`
      saveBlob(blob, fileName)
      toast.success(`已下载 ${ready.length} 篇笔记`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量归档下载失败')
    } finally {
      setDownloadingSelected(false)
    }
  }

  /** 勾选框式批量下载（保留原有入口）。 */
  const downloadSelected = async () => {
    if (!selectedIds.length) return
    setDownloadingSingle(true)
    try {
      const blob = await downloadNoteArchives(selectedIds)
      // 单选一条时用它的真实标题命名，多条用篇数。
      const fileName =
        selectedIds.length === 1
          ? `${sanitizeFileName(
              visibleTasks.find(task => task.id === selectedIds[0])?.audioMeta?.title ?? ''
            )}.zip`
          : `笔记归档-${selectedIds.length}篇.zip`
      saveBlob(blob, fileName)
      toast.success(`已下载 ${selectedIds.length} 篇笔记`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量归档下载失败')
    } finally {
      setDownloadingSingle(false)
    }
  }

  const downloading = downloadingSelected || downloadingSingle

  return (
    <div className="flex h-full w-full flex-col gap-4 px-2.5 py-1.5">
      <div className="my-4 flex min-h-[40px] items-center gap-2">
        <Clock className="h-4 w-4 text-neutral-500" />
        <h2 className="text-base font-medium text-neutral-900">生成历史</h2>
        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!selectedIds.length || downloading}
            onClick={downloadSelected}
          >
            <Download className="mr-1 h-4 w-4" />
            {downloadingSelected
              ? '打包中…'
              : `下载选中${selectedIds.length ? ` (${selectedIds.length})` : ''}`}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={retrying || !visibleTasks.length}
            onClick={requestRetryFailed}
          >
            <RotateCcw className="mr-1 h-4 w-4" />
            {retrying ? '重试中…' : '重试失败'}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={!selectedIds.length || deletingSelected}
            onClick={() => void deleteSelected()}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            {deletingSelected
              ? '删除中…'
              : `删除选中${selectedIds.length ? ` (${selectedIds.length})` : ''}`}
          </Button>
        </div>
      </div>

      <GroupPanel
        groups={groups}
        ungroupedCount={ungroupedCount}
        loading={groupsLoading}
        maxGroups={maxGroups}
        maxNameLength={maxNameLength}
        activeGroupId={activeGroupId}
        selectedGroupIds={checkedGroupIds}
        downloading={downloadingSelected}
        creating={creating}
        dropTargetId={dropTargetId}
        onSelect={groupId => void selectGroup(groupId)}
        onToggleChecked={toggleGroupChecked}
        onCheckAll={checked =>
          setCheckedGroupIds(checked ? [...groups.map(group => group.id), UNGROUPED_ID] : [])
        }
        onCreate={name => void handleCreateGroup(name)}
        onRename={(groupId, name) => void handleRenameGroup(groupId, name)}
        onDelete={group => {
          setDeleteGroupTasks(false)
          setPendingDelete(group)
        }}
        onDownload={() => void downloadCheckedGroups()}
        onDragOverGroup={setDropTargetId}
        onDragLeaveGroup={groupId => setDropTargetId(prev => (prev === groupId ? null : prev))}
        onDropOnGroup={target => void dropOnGroup(target)}
        collapsed={collapsed ?? []}
        onToggleCollapsed={groupId =>
          setCollapsed(prev => {
            const current = prev ?? []
            return current.includes(groupId)
              ? current.filter(id => id !== groupId)
              : [...current, groupId]
          })
        }
      />

      <label className="flex items-center gap-2 text-xs text-neutral-500">
        <input
          type="checkbox"
          checked={allVisibleSelected}
          onChange={event =>
            setSelectedIds(event.target.checked ? visibleTasks.map(task => task.id) : [])
          }
        />
        全选{visibleTasks.length ? ` (${visibleTasks.length})` : ''}
      </label>
      <ScrollArea className="w-full sm:h-[480px] md:h-[720px] lg:h-[92%]">
        <NoteHistory
          onSelect={setCurrentTask}
          selectedId={currentTaskId}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          groupFilterIds={activeTaskIds}
          collapsedGroupIds={collapsed ?? []}
          onToggleCollapsedGroup={groupId =>
            setCollapsed(prev => {
              const current = prev ?? []
              return current.includes(groupId)
                ? current.filter(id => id !== groupId)
                : [...current, groupId]
            })
          }
          onDragTaskStart={setDraggingIds}
          onDownloadGroup={rowId => void downloadOneGroup(rowId)}
        />
      </ScrollArea>

      <Dialog open={confirmRetryOpen} onOpenChange={open => !retrying && setConfirmRetryOpen(open)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>重试当前范围内的失败笔记？</DialogTitle>
            <DialogDescription>
              当前范围有 {visibleTasks.length} 篇笔记，重试会重新下载并转写其中的失败项。
              只有失败的任务会真的重跑；已完成和生成中的会被跳过并告知原因。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={retrying}
              onClick={() => setConfirmRetryOpen(false)}
            >
              取消
            </Button>
            <Button type="button" disabled={retrying} onClick={() => void runRetryFailed()}>
              {retrying ? '重试中…' : '开始重试'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!pendingDelete}
        onOpenChange={open => {
          if (!open) {
            setPendingDelete(null)
            setDeleteGroupTasks(false)
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除分组「{pendingDelete?.name}」？</DialogTitle>
            <DialogDescription>
              {deleteGroupTasks
                ? '组内的笔记会一起被彻底删除，此操作不可撤销。'
                : '组内的笔记不会被删除，它们会被移动到「未分组」。'}
            </DialogDescription>
          </DialogHeader>
          <label className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={deleteGroupTasks}
              onChange={event => setDeleteGroupTasks(event.target.checked)}
            />
            <span>同时删除组内的全部笔记（不可恢复；生成中的笔记会被保留并移入未分组）</span>
          </label>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setPendingDelete(null)}>
              取消
            </Button>
            <Button type="button" variant="destructive" onClick={() => void confirmDeleteGroup()}>
              删除分组
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default History
