import { cn } from '@/ember/lib/cn'

type SpinnerProps = {
  className?: string
  label?: string
}

/** Continuous rotation is the one legitimate looping animation. */
export function Spinner({ className, label }: SpinnerProps) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)} role="status">
      <span
        aria-hidden="true"
        className="ember-spin inline-block size-4 rounded-full border-2 border-current border-t-transparent"
      />
      {label ? <span className="text-small">{label}</span> : null}
    </span>
  )
}
