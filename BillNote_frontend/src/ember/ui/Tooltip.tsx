import { useState, type ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'

type TooltipProps = {
  label: string
  children: ReactNode
  side?: 'top' | 'bottom'
  className?: string
}

/**
 * Tooltips are occasional, so a 160ms fade + 2px rise is affordable.
 * Never on a keyboard-triggered high-frequency control.
 */
export function Tooltip({ label, children, side = 'top', className }: TooltipProps) {
  const [open, setOpen] = useState(false)
  return (
    <span
      className={cn('relative inline-flex', className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open ? (
        <span
          role="tooltip"
          className={cn(
            'ember-enter pointer-events-none absolute left-1/2 z-40 -translate-x-1/2 rounded-control border border-line bg-canvas px-2 py-1 text-caption whitespace-nowrap text-ink shadow-raise',
            side === 'top' ? 'bottom-[calc(100%+6px)]' : 'top-[calc(100%+6px)]',
          )}
        >
          {label}
        </span>
      ) : null}
    </span>
  )
}
