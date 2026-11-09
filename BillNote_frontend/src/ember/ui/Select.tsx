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
  ref
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          'rounded-control border-line bg-surface text-body text-ink h-10 w-full appearance-none border py-0 pr-9 pl-3',
          'focus:border-ember focus:ring-ember-ring transition-[border-color,box-shadow] duration-[var(--dur-hover)] ease-[var(--ease)] focus:ring-[3px] focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-60',
          className
        )}
        {...rest}
      >
        {options.map(o => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="text-ink-mute pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2"
      />
    </div>
  )
})
