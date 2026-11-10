import { useContext } from 'react'
import { cn } from '@/ember/lib/cn'
import { I18nContext } from '@/ember/i18n/context'

type ProgressProps = {
  /** 0–1. Values outside the range are clamped. */
  value: number
  label?: string
  className?: string
}

/**
 * 4px rounded track with a terracotta fill.
 * The fill is driven by transform:scaleX so only a GPU property animates.
 *
 * 没有 label 时进度条仍然需要可访问名 —— 读屏用户听不到"某某，44%"，只听到一个
 * 空名字的 progressbar。这里退回通用的"进度"文案；i18n 上下文缺失时（单测、SSR）
 * 用中性的英文兜底，避免为了一个 aria-label 抛错。
 */
export function Progress({ value, label, className }: ProgressProps) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0))
  const i18n = useContext(I18nContext)
  const accessibleLabel = label ?? (i18n ? i18n.t('task.progress') : 'Progress')
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {label ? (
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-caption text-ink-soft">{label}</span>
          <span className="text-caption font-semibold text-ink-soft tabular-nums">
            {Math.round(clamped * 100)}%
          </span>
        </div>
      ) : null}
      <div
        className="h-1 w-full overflow-hidden rounded-full bg-raised"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped * 100)}
        aria-label={accessibleLabel}
      >
        <div
          className="ember-progress-fill h-full w-full rounded-full bg-ember"
          style={{ transform: `scaleX(${clamped})` }}
        />
      </div>
    </div>
  )
}
