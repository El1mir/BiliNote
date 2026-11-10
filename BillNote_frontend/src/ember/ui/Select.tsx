import { ChevronDown } from 'lucide-react'
import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'
import { useFieldControlA11y } from '@/ember/ui/fieldContext'

export type SelectOption = { value: string; label: string; disabled?: boolean }

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[]
}

/**
 * Native select styled to the Ember input spec — 8px radius, surface fill,
 * terracotta focus ring. Native keeps keyboard and mobile behaviour free.
 *
 * 焦点环用 focus-visible（鼠标点击不留环）；在 <Field> 内时自动继承
 * id / aria-describedby / aria-invalid，调用方显式传入的值优先。
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, options, id, 'aria-describedby': describedBy, 'aria-invalid': invalid, ...rest },
  ref
) {
  const field = useFieldControlA11y()
  return (
    <div className="relative">
      <select
        ref={ref}
        id={id ?? field?.controlId}
        aria-describedby={describedBy ?? field?.describedBy}
        aria-invalid={invalid ?? (field?.invalid ? true : undefined)}
        className={cn(
          'rounded-control border-line bg-surface text-body text-ink h-10 w-full appearance-none border py-0 pr-9 pl-3',
          'transition-[border-color,box-shadow] duration-150 focus-visible:border-ember focus-visible:ring-[3px] focus-visible:ring-ember-ring focus-visible:outline-none',
          'aria-[invalid=true]:border-danger',
          'disabled:cursor-not-allowed disabled:opacity-50',
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
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-mute"
      />
    </div>
  )
})