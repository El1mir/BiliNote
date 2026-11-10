import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'
import { Spinner } from '@/ember/ui/Spinner'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    'bg-primary text-on-primary border border-transparent hover:bg-primary-hover hover:shadow-primary disabled:hover:bg-primary',
  secondary:
    'bg-transparent text-ink border border-line-strong hover:bg-surface hover:border-ink-mute disabled:hover:bg-transparent',
  ghost: 'bg-transparent text-ink-soft border border-transparent hover:bg-surface hover:text-ink',
  destructive: 'bg-danger text-on-danger border border-transparent hover:opacity-90',
}

const SIZE: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-small gap-1.5',
  md: 'h-10 px-4 text-body gap-2',
  lg: 'h-12 px-6 text-subhead gap-2',
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

/**
 * Ember Studio button — 8px radius, semibold, 150ms transition.
 * Press feedback scales to 0.975; hover glow is reserved for the primary variant.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = 'secondary', size = 'md', loading, disabled, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'ember-press inline-flex shrink-0 items-center justify-center rounded-control font-semibold whitespace-nowrap',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="size-3.5" /> : null}
      {children}
    </button>
  )
})
