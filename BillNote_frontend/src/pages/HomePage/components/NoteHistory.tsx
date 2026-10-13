import { useTaskStore, type Task, type TaskStatus } from '@/store/taskStore'
import { cn } from '@/lib/utils.ts'
import { Trash, Download, GripVertical, ChevronDown, ChevronRight, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button.tsx'
import Fuse from 'fuse.js'
import { asText } from '@/utils/text'
import { isTaskInFlight } from '@/utils/taskStatus.ts'

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import { FC, useState, useEffect, useMemo } from 'react'

interface NoteHistoryProps {
  onSelect: (taskId: string) => void
  selectedId: string | null
  selectedIds?: string[]
  onSelectionChange?: (ids: string[]) => void
  /** 非 null 时只显示这些 task_id（由外部分组过滤算出）。 */
  groupFilterIds?: string[] | null
  /** 收起的 groupId 列表，收起后不渲染该组的行。 */
  collapsedGroupIds?: string[]
  /** 点分组标题时切换收起/展开。 */
  onToggleCollapsedGroup?: (groupId: string) => void
  /** 开始拖动任务时把「要一起移动的 id 列表」交给上层。 */
  onDragTaskStart?: (taskIds: string[]) => void
  /** 「下载本组笔记」。参数是分组行 id（UNGROUPED_ID 表示未分组）。 */
  onDownloadGroup?: (groupId: string) => void
}

/** 一次渲染的一段：要么是一个分组，要么是未归组的那部分。 */
interface TaskSection {
  key: string
  label: string
  /** null = 不提供「下载本组」按钮（例如全部混显的兜底段）。 */
  groupRowId: string | null
  tasks: Task[]
}

/**
 * 状态筛选的可选项。`null` = 不过滤。
 *
 * 「进行中」刻意收成一个选项而不是把 PENDING / PARSING / DOWNLOADING /
 * TRANSCRIBING / SUMMARIZING 全列出来 —— 用户找的是「还没好的那些」，
 * 不是某个内部阶段名。
 */
const STATUS_FILTERS: { value: TaskStatus | null; label: string }[] = [
  { value: null, label: '全部' },
  { value: 'SUCCESS', label: '已完成' },
  { value: 'FAILED', label: '失败' },
  { value: 'PENDING', label: '进行中' },
]

/** 「进行中」这一档实际匹配的状态集合。 */
const IN_FLIGHT_STATUSES: TaskStatus[] = [
  'PENDING',
  'PARSING',
  'DOWNLOADING',
  'TRANSCRIBING',
  'SUMMARIZING',
]

/** 一条任务落在当前状态筛选的第几档。 */
const matchStatusFilter = (status: TaskStatus | undefined, filter: TaskStatus | null) => {
  if (!filter) return true
  if (filter === 'PENDING') return IN_FLIGHT_STATUSES.includes(status as TaskStatus)
  return status === filter
}

const NoteHistory: FC<NoteHistoryProps> = ({
  onSelect,
  selectedId,
  selectedIds = [],
  onSelectionChange,
  groupFilterIds = null,
  collapsedGroupIds = [],
  onToggleCollapsedGroup,
  onDragTaskStart,
  onDownloadGroup,
}) => {
  const tasks = useTaskStore(state => state.tasks)
  const removeTask = useTaskStore(state => state.removeTask)
  const [rawSearch, setRawSearch] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<TaskStatus | null>(null)
  /** 搜索命中的组：临时展开，让用户立刻看到搜到的东西在哪。 */
  const [searchExpanded, setSearchExpanded] = useState<string[]>([])

  const fuse = useMemo(
    () =>
      new Fuse(tasks, {
        // 标题之外还检索分组名与正文：用户记得的往往是「那篇讲导数的」，
        // 而不是标题原文。正文权重压低，避免长文压过标题命中。
        keys: [
          { name: 'audioMeta.title', weight: 0.6 },
          { name: 'groupName', weight: 0.25 },
          { name: 'markdown', weight: 0.15 },
        ],
        threshold: 0.4, // 匹配精度（越低越严格）
        ignoreLocation: true,
        minMatchCharLength: 1,
      }),
    [tasks]
  )
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(rawSearch)
    }, 300) // 300ms 防抖

    return () => clearTimeout(timer)
  }, [rawSearch])

  const keyword = search.trim()
  /** 关键词命中的任务 id；没搜索时为 null（表示「不做关键词过滤」）。 */
  const hitIds = useMemo(
    () => (keyword ? new Set(fuse.search(keyword).map(result => result.item.id)) : null),
    [fuse, keyword]
  )

  const filteredTasks = useMemo(() => {
    let next = tasks
    if (groupFilterIds) next = next.filter(task => groupFilterIds.includes(task.id))
    if (hitIds) next = next.filter(task => hitIds.has(task.id))
    if (statusFilter) next = next.filter(task => matchStatusFilter(task.status, statusFilter))
    return next
  }, [tasks, groupFilterIds, hitIds, statusFilter])

  const searching = Boolean(keyword) || statusFilter !== null

  /** 按 groupName 切段：有名字的先按出现顺序成段，无归组的最后合成「未分组」段。 */
  const sections: TaskSection[] = useMemo(() => {
    const buckets = new Map<string, TaskSection>()
    const loose: Task[] = []
    filteredTasks.forEach(task => {
      // groupId/groupName 由 taskStore 提供（并行改动），取不到就当作未分组。
      const groupName = (task as Task & { groupName?: string }).groupName
      const groupId = (task as Task & { groupId?: string | null }).groupId ?? null
      if (!groupId || !groupName) {
        loose.push(task)
        return
      }
      const existing = buckets.get(groupId)
      if (existing) {
        existing.tasks.push(task)
      } else {
        buckets.set(groupId, { key: groupId, label: groupName, groupRowId: groupId, tasks: [task] })
      }
    })
    const result = [...buckets.values()]
    if (loose.length) {
      result.push({ key: '__loose__', label: '未分组', groupRowId: null, tasks: loose })
    }
    return result
  }, [filteredTasks])

  /** 搜索时把命中的分组临时展开（不改用户自己的收起集合）。 */
  useEffect(() => {
    const hitSections = sections
      .filter(section => section.tasks.some(task => hitIds?.has(task.id)))
      .map(section => section.key)
    setSearchExpanded(hitSections)
  }, [sections, hitIds])

  const isSectionCollapsed = (key: string) => {
    // 搜索期间：命中的组强制展开，没命中的组不显示内容。
    if (searching) return !searchExpanded.includes(key)
    return collapsedGroupIds.includes(key)
  }

  const statusCounts = useMemo(() => {
    const base = groupFilterIds ? tasks.filter(task => groupFilterIds.includes(task.id)) : tasks
    return {
      all: base.length,
      success: base.filter(task => task.status === 'SUCCESS').length,
      failed: base.filter(task => task.status === 'FAILED').length,
      running: base.filter(task => IN_FLIGHT_STATUSES.includes(task.status)).length,
    }
  }, [tasks, groupFilterIds])

  const countForFilter = (filter: TaskStatus | null) => {
    if (filter === 'SUCCESS') return statusCounts.success
    if (filter === 'FAILED') return statusCounts.failed
    if (filter === 'PENDING') return statusCounts.running
    return statusCounts.all
  }

  const searchBox = (
    <div className="mb-3 flex flex-col gap-2">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-neutral-400" />
        <input
          type="text"
          placeholder="搜索标题、分组或笔记内容…"
          className="focus:border-primary w-full rounded-md border border-neutral-300 py-1.5 pr-7 pl-8 text-xs outline-none"
          value={rawSearch}
          onChange={e => setRawSearch(e.target.value)}
        />
        {rawSearch && (
          <button
            type="button"
            aria-label="清空搜索"
            onClick={() => {
              setRawSearch('')
              setSearch('')
            }}
            className="absolute top-1/2 right-2 -translate-y-1/2 cursor-pointer text-neutral-400 hover:text-neutral-600"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {STATUS_FILTERS.map(item => {
          const active = statusFilter === item.value
          return (
            <button
              key={item.label}
              type="button"
              onClick={() => setStatusFilter(item.value)}
              className={cn(
                'cursor-pointer rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                active
                  ? 'border-primary bg-primary text-white'
                  : 'border-neutral-200 text-neutral-500 hover:bg-neutral-50'
              )}
            >
              {item.label}
              <span className={cn('ml-1', active ? 'text-white/70' : 'text-neutral-400')}>
                {countForFilter(item.value)}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )

  if (filteredTasks.length === 0) {
    return (
      <>
        {searchBox}
        <div className="rounded-md border border-neutral-200 bg-neutral-50 py-6 text-center">
          <p className="text-sm text-neutral-500">{searching ? '没有匹配的笔记' : '暂无记录'}</p>
          {searching && (
            <button
              type="button"
              className="text-primary mt-1 cursor-pointer text-xs hover:underline"
              onClick={() => {
                setRawSearch('')
                setSearch('')
                setStatusFilter(null)
              }}
            >
              清空筛选条件
            </button>
          )}
        </div>
      </>
    )
  }

  /** 拖拽开始时，若这条任务在批量勾选里，就整批一起拖；否则只拖它自己。 */
  const startDrag = (task: Task, event: React.DragEvent) => {
    const ids = selectedIds.includes(task.id) && selectedIds.length > 1 ? selectedIds : [task.id]
    onDragTaskStart?.(ids)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', ids.join(','))
  }

  const renderTask = (task: Task) => (
    <div
      key={task.id}
      draggable
      onDragStart={event => startDrag(task, event)}
      onDragEnd={() => onDragTaskStart?.([])}
      onClick={() => onSelect(task.id)}
      className={cn(
        'flex cursor-pointer flex-col rounded-md border border-neutral-200 p-3',
        selectedId === task.id && 'border-primary bg-primary-light'
      )}
    >
      {onSelectionChange && (
        <label
          className="mb-2 flex items-center gap-2 text-xs text-neutral-500"
          onClick={event => event.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={selectedIds.includes(task.id)}
            onChange={event =>
              onSelectionChange(
                event.target.checked
                  ? [...selectedIds, task.id]
                  : selectedIds.filter(id => id !== task.id)
              )
            }
          />
          选中
        </label>
      )}
      <div className={cn('flex min-w-0 items-center gap-3')}>
        {/* 标题 + 状态：文字优先，封面图按需加载（见 cover_url 处理） */}
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="line-clamp-2 min-w-0 flex-1 overflow-hidden text-sm text-ellipsis">
                  {asText(task.audioMeta?.title, '未命名笔记')}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>{asText(task.audioMeta?.title, '未命名笔记')}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
      <div className={'mt-2 flex items-center justify-between text-[10px]'}>
        <div className="flex shrink-0 items-center gap-1">
          <GripVertical className="h-3 w-3 cursor-grab text-neutral-400" />
          {task.status === 'SUCCESS' && (
            <div className={'bg-primary w-10 rounded p-0.5 text-center text-white'}>已完成</div>
          )}
          {task.status !== 'SUCCESS' && task.status !== 'FAILED' ? (
            <div className={'w-10 rounded bg-green-500 p-0.5 text-center text-white'}>等待中</div>
          ) : (
            <></>
          )}
          {task.status === 'FAILED' && (
            <div className={'w-10 rounded bg-red-500 p-0.5 text-center text-white'}>失败</div>
          )}
        </div>

        <div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={isTaskInFlight(task.status)}
                  onClick={e => {
                    e.stopPropagation()
                    removeTask(task.id)
                  }}
                  className="shrink-0"
                >
                  <Trash className="text-muted-foreground h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{isTaskInFlight(task.status) ? '生成中，暂不能删除' : '删除'}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  )

  return (
    <>
      {searchBox}
      <div className="flex flex-col gap-3 overflow-hidden">
        {sections.map(section => {
          const collapsed = isSectionCollapsed(section.key)
          const readyCount = section.tasks.filter(task => task.status === 'SUCCESS').length
          return (
            // OneNote 式的「分区」观感：整块带底色与左侧色条，展开后组内内容
            // 缩进并落在同一块底里，一眼能看出「这些属于这一组」。
            <div
              key={section.key}
              className="overflow-hidden rounded-lg border border-neutral-200 bg-neutral-50/60"
            >
              <div
                className={cn(
                  'border-primary/60 flex cursor-pointer items-center gap-1.5 bg-white px-2 py-1.5 text-[11px] transition-colors hover:bg-neutral-50',
                  !collapsed && 'border-b bg-neutral-100/80'
                )}
                onClick={() => {
                  if (searching) return
                  onToggleCollapsedGroup?.(section.key)
                }}
              >
                {!searching &&
                  (collapsed ? (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
                  ))}
                <span
                  className="min-w-0 truncate font-semibold text-neutral-700"
                  title={section.label}
                >
                  {section.label}
                </span>
                <span className="shrink-0 text-neutral-400">({section.tasks.length})</span>
                {collapsed ? (
                  <span className="ml-auto shrink-0 text-neutral-400">已收起</span>
                ) : null}
                {section.groupRowId && onDownloadGroup ? (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="ml-auto h-6 shrink-0 px-2 text-[11px]"
                          disabled={!readyCount}
                          onClick={event => {
                            event.stopPropagation()
                            onDownloadGroup(section.groupRowId!)
                          }}
                        >
                          <Download className="mr-1 h-3 w-3" />
                          下载本组{readyCount ? ` (${readyCount})` : ''}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>下载本组内已生成的笔记；未生成的会被跳过</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : null}
              </div>
              {!collapsed && (
                <div className="border-primary/50 flex flex-col gap-1.5 border-l-2 py-1.5 pr-1.5 pl-2">
                  {section.tasks.map(renderTask)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}

export default NoteHistory
