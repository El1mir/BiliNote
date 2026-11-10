import { useMemo, useState } from 'react'
import { Archive, CheckSquare, FolderInput, Search, Trash2, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useSearchParams } from 'react-router-dom'
import { useTaskStore, type Task } from '@/store/taskStore'
import { downloadNoteArchives } from '@/services/note'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Chip } from '@/ember/ui/Chip'
import { Input } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { EmptyState } from '@/ember/ui/EmptyState'
import { cn } from '@/ember/lib/cn'
import { taskTitle } from '@/ember/features/workspace/taskState'
import { TaskCard } from '@/ember/features/workspace/TaskCard'
import { Dialog } from '@/ember/ui/Dialog'
import { UNGROUPED_ID } from '@/services/noteGroup'
import { retryScopeForGroup } from '@/ember/features/workspace/retryFailed'
import { readTaskId, writeTaskId } from '@/ember/lib/taskUrl'
import { RetryFailedAction } from '@/ember/features/workspace/RetryFailedAction'

type Filter = 'all' | 'ready' | 'running' | 'failed'

type TaskListProps = {
  /** True until the first server list lands, so we show skeletons instead of an empty state. */
  loading?: boolean
  className?: string
  /** null shows every task; UNGROUPED_ID shows only tasks with no group; otherwise that group. */
  activeGroupId?: string | null
  /** Called when a card starts being dragged, with the ids that should move together. */
  onDragTasks?: (ids: string[]) => void
  onDragEnd?: () => void
  /** Real groups, offered as a keyboard/touch alternative to dragging. */
  groups?: { id: string; name: string }[]
  onMoveTasks?: (ids: string[], groupId: string | null) => void
  onRetryFailedTasks?: (
    selectedIds: string[],
    scope: 'all' | 'group',
    groupId: string | null
  ) => Promise<void>
}

const isReady = (task: Task) => String(task.status) === 'SUCCESS'
const isFailed = (task: Task) => ['FAILED', 'FAILD'].includes(String(task.status))
const isRunning = (task: Task) => !isReady(task) && !isFailed(task)

/**
 * The history rail. One flat, searchable list — groups narrow the list instead of
 * nesting it, because a nested tree inside a 340px rail hides most of the content.
 * Dragging a card onto a group row files it; select mode offers the same move as a
 * menu for keyboard and touch.
 */
export function TaskList({
  loading,
  className,
  activeGroupId = null,
  onDragTasks,
  onDragEnd,
  groups = [],
  onMoveTasks,
  onRetryFailedTasks,
}: TaskListProps) {
  const { t } = useI18n()
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const [searchParams, setSearchParams] = useSearchParams()
  // 列表高亮以地址栏为准：store 只是镜像，URL 才是刷新/分享后仍然有效的那一份。
  const urlTaskId = readTaskId(searchParams.toString())
  const removeTasks = useTaskStore(state => state.removeTasks)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [exporting, setExporting] = useState(false)
  const [moving, setMoving] = useState(false)
  const selectedFailedCount = selected.filter(id => {
    const task = tasks.find(item => item.id === id)
    if (!task || !isFailed(task)) return false
    if (activeGroupId === null) return true
    if (activeGroupId === UNGROUPED_ID) return !task.groupId
    return task.groupId === activeGroupId
  }).length

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return tasks
      .filter(task => {
        if (!activeGroupId) return true
        if (activeGroupId === UNGROUPED_ID) return !task.groupId
        return task.groupId === activeGroupId
      })
      .filter(task => {
        if (filter === 'ready') return isReady(task)
        if (filter === 'running') return isRunning(task)
        if (filter === 'failed') return isFailed(task)
        return true
      })
      .filter(task => {
        if (!needle) return true
        return (
          taskTitle(task).toLowerCase().includes(needle) ||
          (task.formData?.video_url ?? '').toLowerCase().includes(needle)
        )
      })
  }, [tasks, filter, query, activeGroupId])

  const toggleSelected = (id: string) =>
    setSelected(current =>
      current.includes(id) ? current.filter(item => item !== id) : [...current, id]
    )

  const exitSelection = () => {
    setSelecting(false)
    setSelected([])
  }

  const deleteSelected = async () => {
    if (!selected.length) return
    await removeTasks(selected)
    exitSelection()
  }

  /**
   * Zips the selected notes' folders into one download. The endpoint answers
   * HTTP 200 with a JSON body when none of the ids has a finished note, so the
   * failure has to reach the user as a toast rather than an empty file.
   */
  const exportSelected = async () => {
    if (!selected.length || exporting) return
    setExporting(true)
    try {
      const blob = await downloadNoteArchives(selected)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `bilinote-notes-${selected.length}.zip`
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success(t('group.archiveDone', { count: selected.length }))
      exitSelection()
    } catch (error) {
      toast.error(
        t('note.exportFailed', {
          detail: error instanceof Error && error.message ? error.message : t('common.error'),
        })
      )
    } finally {
      setExporting(false)
    }
  }

  const moveSelected = async (groupId: string | null) => {
    if (!selected.length || !onMoveTasks) return
    onMoveTasks(selected, groupId)
    setMoving(false)
    exitSelection()
  }

  const retryFailedInScope = async () => {
    if (!onRetryFailedTasks || filter !== 'failed' || selectedFailedCount === 0) return
    const { scope, groupId } = retryScopeForGroup(activeGroupId)
    await onRetryFailedTasks(selected, scope, groupId)
    exitSelection()
  }

  const filters: { id: Filter; label: string }[] = [
    { id: 'all', label: t('history.filter.all') },
    { id: 'running', label: t('history.filter.running') },
    { id: 'ready', label: t('history.filter.ready') },
    { id: 'failed', label: t('history.filter.failed') },
  ]

  return (
    <div className={cn('flex min-h-0 flex-col gap-3', className)}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-subhead">{t('history.title')}</h2>
        <div className="flex items-center gap-1">
          {selecting ? (
            <>
              <Button size="sm" variant="ghost" onClick={exitSelection}>
                {t('common.cancel')}
              </Button>
              {onMoveTasks && groups.length ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={!selected.length}
                  onClick={() => setMoving(true)}
                >
                  <FolderInput className="size-3.5" />
                  {t('group.move')}
                </Button>
              ) : null}
              {onRetryFailedTasks ? (
                <RetryFailedAction
                  disabled={selectedFailedCount === 0}
                  failedFilterActive={filter === 'failed'}
                  scope={activeGroupId ? 'group' : 'all'}
                  onRetry={() => void retryFailedInScope()}
                />
              ) : null}
              <Button
                size="sm"
                variant="ghost"
                disabled={!selected.length}
                loading={exporting}
                onClick={() => void exportSelected()}
              >
                <Archive className="size-3.5" />
                {t('history.exportSelected')}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={!selected.length}
                onClick={deleteSelected}
              >
                <Trash2 className="size-3.5" />
                {selected.length
                  ? t('history.selected', { count: selected.length })
                  : t('common.delete')}
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelecting(true)}
              disabled={!tasks.length}
            >
              <CheckSquare className="size-3.5" />
              {t('common.more')}
            </Button>
          )}
        </div>
      </div>

      <div className="relative">
        <Search
          aria-hidden="true"
          className="text-ink-mute pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
        />
        <Input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={t('history.searchPlaceholder')}
          className="h-9 pl-9"
          aria-label={t('common.search')}
        />
        {query ? (
          <button
            type="button"
            aria-label={t('common.clear')}
            onClick={() => setQuery('')}
            className="ember-press rounded-control text-ink-mute hover:bg-raised absolute top-1/2 right-1 flex size-11 -translate-y-1/2 items-center justify-center"
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {filters.map(item => (
          <Chip
            key={item.id}
            active={filter === item.id}
            onClick={() => setFilter(item.id)}
            className="px-3 py-1"
          >
            {item.label}
          </Chip>
        ))}
      </div>

      <div className="-mr-1 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {loading && !tasks.length ? (
          <>
            <Skeleton className="h-[92px] w-full" />
            <Skeleton className="h-[92px] w-full" />
            <Skeleton className="h-[92px] w-full" />
          </>
        ) : visible.length ? (
          visible.map(task => {
            const active = task.id === (urlTaskId ?? currentTaskId)
            const checked = selected.includes(task.id)
            return (
              <TaskCard
                key={task.id}
                task={task}
                active={active}
                selecting={selecting}
                checked={checked}
                draggable={!selecting && Boolean(onDragTasks)}
                onClick={() => {
                  if (selecting) {
                    toggleSelected(task.id)
                    return
                  }
                  // 选中态写进地址栏，store 只跟着走（S2：刷新/分享都不能丢当前任务）。
                  setCurrentTask(task.id)
                  setSearchParams(
                    prev => new URLSearchParams(writeTaskId(prev.toString(), task.id)),
                    { replace: false }
                  )
                }}
                onDragStart={event => {
                  // Dragging in select mode takes the whole checked set; otherwise just this card.
                  const ids = selecting && checked ? [...selected] : [task.id]
                  event.dataTransfer.effectAllowed = 'move'
                  event.dataTransfer.setData('text/plain', ids.join(','))
                  onDragTasks?.(ids)
                }}
                onDragEnd={() => onDragEnd?.()}
              />
            )
          })
        ) : (
          <EmptyState title={t('history.empty')} description={t('workspace.noTaskDescription')} />
        )}
      </div>

      <Dialog
        open={moving}
        onClose={() => setMoving(false)}
        size="sm"
        title={t('group.move')}
        description={t('history.selected', { count: selected.length })}
      >
        <div className="flex flex-col gap-0.5">
          {groups.map(group => (
            <button
              key={group.id}
              type="button"
              onClick={() => void moveSelected(group.id)}
              className="rounded-control text-small text-ink-soft hover:bg-surface hover:text-ink flex items-center gap-2 px-2 py-1.5 text-left transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]"
            >
              <FolderInput className="size-3.5 shrink-0" />
              <span className="truncate">{group.name}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => void moveSelected(UNGROUPED_ID)}
            className="rounded-control text-small text-ink-soft hover:bg-surface hover:text-ink flex items-center gap-2 px-2 py-1.5 text-left transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]"
          >
            <FolderInput className="size-3.5 shrink-0" />
            <span className="truncate">{t('group.moveToNone')}</span>
          </button>
        </div>
      </Dialog>
    </div>
  )
}