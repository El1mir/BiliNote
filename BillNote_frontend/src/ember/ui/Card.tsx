import { forwardRef, type HTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'

type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** Terracotta 4px stripe on the leading edge — marks the active/selected item. */
  stripe?: string
  /** Selected state — terracotta inset ring. Never changes the box, so content cannot shift by a pixel. */
  selected?: boolean
  /** Lift 2px with a soft shadow on pointer-fine hover. */
  interactive?: boolean
}

/**
 * Ember Studio card — warm surface, 1px border, 12px radius, 16px padding.
 * Floats flat at rest and gains elevation on hover.
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { className, stripe, selected, interactive, children, style, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        'relative overflow-hidden rounded-surface border border-line bg-surface',
        // A left border would eat 2px out of the 1px box and shift every child.
        // An inset ring paints inside the existing border without touching layout.
        selected && 'border-ember ring-1 ring-ember ring-inset',
        interactive && 'ember-lift cursor-pointer',
        className,
      )}
      style={style}
      {...rest}
    >
      {stripe ? (
        <span aria-hidden="true" className="absolute inset-y-0 left-0 w-1" style={{ background: stripe }} />
      ) : null}
      {children}
    </div>
  )
})

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex items-start justify-between gap-3 px-4 pt-4', className)} {...rest} />
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn('font-display text-subhead leading-snug', className)} {...rest} />
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-4 py-4', className)} {...rest} />
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex items-center gap-2 border-t border-line px-4 py-3', className)} {...rest} />
}
