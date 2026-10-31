import { cn } from '@/ember/lib/cn'

type ProgressProps = {
  /** 0–1. Values outside the range are clamped. */
  value: number
  label?: string
  className?: string
}

/**
 * 4px rounded track with a terracotta fill.
 * The fill is driven by transform:scaleX so only a GPU property animates.
 */
export function Progress({ value, label, className }: ProgressProps) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0))
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
        aria-label={label}
      >
        <div
          className="ember-progress-fill h-full w-full rounded-full bg-ember"
          style={{ transform: `scaleX(${clamped})` }}
        />
      </div>
    </div>
  )
}
