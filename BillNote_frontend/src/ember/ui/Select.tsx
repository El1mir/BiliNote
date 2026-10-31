import { ChevronDown } from 'lucide-react'
import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'

export type SelectOption = { value: string; label: string; disabled?: boolean }

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[]
}

/**
 * Native select styled to the Ember input spec — 8px radius, surface fill,
 * terracotta focus ring. Native keeps keyboard and mobile behaviour free.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, options, ...rest },
  ref,
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          'h-10 w-full appearance-none rounded-control border border-line bg-surface py-0 pr-9 pl-3 text-body text-ink',
          'transition-[border-color,box-shadow] duration-150 focus:border-ember focus:ring-[3px] focus:ring-ember-ring focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-60',
          className,
        )}
        {...rest}
      >
        {options.map(o => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-mute" />
    </div>
  )
})
