import type { ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'

type FieldProps = {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  error?: ReactNode
  required?: boolean
  className?: string
  children: ReactNode
}

/** Label (14px semibold) above the control, hint and error beneath. */
export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={htmlFor} className="text-small font-semibold text-ink">
        {label}
        {required ? <span className="ml-0.5 text-ember">*</span> : null}
      </label>
      {children}
      {error ? (
        <p className="text-caption text-danger">{error}</p>
      ) : hint ? (
        <p className="text-caption text-ink-soft">{hint}</p>
      ) : null}
    </div>
  )
}
