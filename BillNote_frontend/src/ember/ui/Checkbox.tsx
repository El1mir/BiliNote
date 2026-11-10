import { Check } from 'lucide-react'
import { cn } from '@/ember/lib/cn'

type CheckboxProps = {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  id?: string
  label?: string
  className?: string
}

/** Terracotta check mark on a warm surface; the mark fades in, nothing moves. */
export function Checkbox({ checked, onChange, disabled, id, label, className }: CheckboxProps) {
  return (
    <button
      type="button"
      id={id}
      role="checkbox"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'ember-press inline-flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border',
        checked ? 'border-ember bg-ember text-white' : 'border-line bg-surface',
        disabled && 'cursor-not-allowed opacity-50',
        className
      )}
    >
      <Check
        className={cn(
          'size-3 transition-opacity duration-[var(--dur-hover)] ease-[var(--ease)]',
          checked ? 'opacity-100' : 'opacity-0'
        )}
        strokeWidth={3}
      />
    </button>
  )
}
