import type { DragEvent } from 'react'
import { CheckSquare, Square } from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { useI18n } from '@/ember/i18n/context'
import { Progress } from '@/ember/ui/Progress'
import { cn } from '@/ember/lib/cn'
import { StatusBadge } from './StatusBadge'
import { detailSummary, stageKey, taskProgress, taskTitle } from './taskState'

type TaskCardProps = {
  task: Task
  active: boolean
  selecting: boolean
  checked: boolean
  draggable: boolean
  onClick: () => void
  onDragStart: (event: DragEvent<HTMLButtonElement>) => void
  onDragEnd: () => void
}

/**
 * One row in the history rail.
 *
 * 卡片除了标题与状态徽标，还必须回答"现在到哪一步了、走到多少"——否则用户在
 * 一屏十几条任务里只看得到一排"生成中"。阶段文案优先用后端写的 `stage_label`，
 * 回落前端映射；计数（切片/帧/网格）来自 `detail`；`progress` 为 null 时
 * 不画进度条，因为一条停在 0% 的条比没有条更误导。
 *
 * 选中态用"左侧 3px 强调条 + 染色底"表达，不用整块描边：列表里同时有 hover、
 * 拖拽目标和选中三种状态，抢眼的粗边框会让它们互相淹没。
 */
export function TaskCard({
  task,
  active,
  selecting,
  checked,
  draggable,
  onClick,
  onDragStart,
  onDragEnd,
}: TaskCardProps) {
  const { t, locale } = useI18n()
  const stage = stageKey(task.stage)
  const stageLabel = task.stageLabel || (stage ? t(stage) : null)
  const detail = detailSummary(task.detail, t)
  const showProgress = task.progress !== null && task.progress !== undefined

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'true' : undefined}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={cn(
        'ember-press group relative flex w-full cursor-pointer flex-col gap-1.5 rounded-control border py-2.5 pr-3 pl-3 text-left',
        'transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]',
        active
          ? 'border-accent/40 bg-accent-soft pl-3.5'
          : 'border-line bg-surface hover:border-line-strong hover:bg-raised/60'
      )}
    >
      {active ? (
        <span
          aria-hidden="true"
          className="absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-accent"
        />
      ) : null}

      <span className="flex items-start gap-2">
        {selecting ? (
          checked ? (
            <CheckSquare className="mt-0.5 size-4 shrink-0 text-accent" />
          ) : (
            <Square className="mt-0.5 size-4 shrink-0 text-ink-muted" />
          )
        ) : null}
        <span className="line-clamp-2 min-w-0 flex-1 text-card leading-snug font-semibold text-ink">
          {taskTitle(task)}
        </span>
        <StatusBadge status={task.status} className="shrink-0 translate-y-[1px]" />
      </span>

      {stageLabel || detail ? (
        <span className="flex items-center gap-2 text-caption text-ink-soft" data-testid="task-card-stage">
          {stageLabel ? <span className="truncate">{stageLabel}</span> : null}
          {detail ? (
            <>
              <span aria-hidden="true">·</span>
              <span className="shrink-0 tabular-nums">{detail}</span>
            </>
          ) : null}
        </span>
      ) : null}

      {showProgress ? <Progress value={taskProgress(task)} /> : null}

      <span className="flex items-center gap-2 text-caption text-ink-muted">
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
}

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
