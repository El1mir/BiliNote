import { useMemo, useState } from 'react'
import { CheckSquare, FolderInput, Search, Square, Trash2, X } from 'lucide-react'
import { useTaskStore, type Task } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Chip } from '@/ember/ui/Chip'
import { Input } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { EmptyState } from '@/ember/ui/EmptyState'
import { cn } from '@/ember/lib/cn'
import { statusKey, statusTone, taskTitle } from '@/ember/features/workspace/taskState'
import { Dialog } from '@/ember/ui/Dialog'
import { UNGROUPED_ID } from '@/services/noteGroup'

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
}

const isReady = (task: Task) => String(task.status) === 'SUCCESS'
const isFailed = (task: Task) => ['FAILED', 'FAILD'].includes(String(task.status))
const isRunning = (task: Task) => !isReady(task) && !isFailed(task)

const relativeTime = (iso: string, locale: string): string => {
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return ''
  const diff = Date.now() - then
  const minutes = Math.floor(diff / 60000)
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  if (minutes < 1) return formatter.format(0, 'minute')
  if (minutes < 60) return formatter.format(-minutes, 'minute')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return formatter.format(-hours, 'hour')
  return formatter.format(-Math.floor(hours / 24), 'day')
}

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
}: TaskListProps) {
  const { t, locale } = useI18n()
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const removeTasks = useTaskStore(state => state.removeTasks)

  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [moving, setMoving] = useState(false)

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
    setSelected(current => (current.includes(id) ? current.filter(item => item !== id) : [...current, id]))

  const exitSelection = () => {
    setSelecting(false)
    setSelected([])
  }

  const deleteSelected = async () => {
    if (!selected.length) return
    await removeTasks(selected)
    exitSelection()
  }

  const moveSelected = async (groupId: string | null) => {
    if (!selected.length || !onMoveTasks) return
    onMoveTasks(selected, groupId)
    setMoving(false)
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
                <Button size="sm" variant="ghost" disabled={!selected.length} onClick={() => setMoving(true)}>
                  <FolderInput className="size-3.5" />
                  {t('group.move')}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="destructive"
                disabled={!selected.length}
                onClick={deleteSelected}
              >
                <Trash2 className="size-3.5" />
                {selected.length ? t('history.selected', { count: selected.length }) : t('common.delete')}
              </Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setSelecting(true)} disabled={!tasks.length}>
              <CheckSquare className="size-3.5" />
              {t('common.more')}
            </Button>
          )}
        </div>
      </div>

      <div className="relative">
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-mute" />
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
            className="absolute top-1/2 right-2 -translate-y-1/2 rounded-control p-1 text-ink-mute hover:bg-raised"
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {filters.map(item => (
          <Chip key={item.id} active={filter === item.id} onClick={() => setFilter(item.id)} className="px-3 py-1">
            {item.label}
          </Chip>
        ))}
      </div>

      <div className="-mr-1 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {loading && !tasks.length ? (
          <>
            <Skeleton className="h-[68px] w-full" />
            <Skeleton className="h-[68px] w-full" />
            <Skeleton className="h-[68px] w-full" />
          </>
        ) : visible.length ? (
          visible.map(task => {
            const active = task.id === currentTaskId
            const checked = selected.includes(task.id)
            return (
              <button
                key={task.id}
                type="button"
                onClick={() => (selecting ? toggleSelected(task.id) : setCurrentTask(task.id))}
                aria-current={active ? 'true' : undefined}
                draggable={!selecting && Boolean(onDragTasks)}
                onDragStart={event => {
                  // Dragging in select mode takes the whole checked set; otherwise just this card.
                  const ids = selecting && checked ? [...selected] : [task.id]
                  event.dataTransfer.effectAllowed = 'move'
                  event.dataTransfer.setData('text/plain', ids.join(','))
                  onDragTasks?.(ids)
                }}
                onDragEnd={() => onDragEnd?.()}
                className={cn(
                  'ember-press group relative flex w-full flex-col gap-1.5 rounded-surface border px-3 py-2.5 text-left transition-colors',
                  active ? 'border-ember/40 bg-ember-soft/60' : 'border-line bg-surface hover:border-ink-mute/40',
                )}
              >
                <span className="flex items-start gap-2">
                  {selecting ? (
                    checked ? (
                      <CheckSquare className="mt-0.5 size-4 shrink-0 text-ember" />
                    ) : (
                      <Square className="mt-0.5 size-4 shrink-0 text-ink-mute" />
                    )
                  ) : null}
                  <span className="line-clamp-2 min-w-0 flex-1 text-small font-semibold text-ink">
                    {taskTitle(task)}
                  </span>
                  <Badge tone={statusTone(task.status)}>{t(statusKey(task.status))}</Badge>
                </span>
                <span className="flex items-center gap-2 text-caption text-ink-mute">
                  <span className="shrink-0 whitespace-nowrap tabular-nums">
                    {relativeTime(task.createdAt, locale)}
                  </span>
                  {task.groupName ? (
                    <>
                      <span aria-hidden="true">·</span>
                      <span className="truncate">{task.groupName}</span>
                    </>
                  ) : null}
                </span>
              </button>
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
              className="flex items-center gap-2 rounded-control px-2 py-1.5 text-left text-small text-ink-soft transition-colors hover:bg-surface hover:text-ink"
            >
              <FolderInput className="size-3.5 shrink-0" />
              <span className="truncate">{group.name}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => void moveSelected(UNGROUPED_ID)}
            className="flex items-center gap-2 rounded-control px-2 py-1.5 text-left text-small text-ink-soft transition-colors hover:bg-surface hover:text-ink"
          >
            <FolderInput className="size-3.5 shrink-0" />
            <span className="truncate">{t('group.moveToNone')}</span>
          </button>
        </div>
      </Dialog>
    </div>
  )
}
