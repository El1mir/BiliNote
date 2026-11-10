import { cn } from '@/ember/lib/cn'

type SwitchProps = {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  id?: string
  label?: string
  className?: string
}

/**
 * Toggle. The knob travels on transform only; the track changes colour.
 * Interruptible: a transition retargets from the current position mid-flight.
 */
export function Switch({ checked, onChange, disabled, id, label, className }: SwitchProps) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]',
        checked ? 'border-ember bg-ember' : 'border-line bg-raised',
        disabled && 'cursor-not-allowed opacity-50',
        className
      )}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none inline-block size-4 rounded-full bg-white shadow-sm transition-transform duration-[var(--dur-press)] ease-[var(--ease)]"
        style={{ transform: checked ? 'translateX(22px)' : 'translateX(3px)' }}
      />
    </button>
  )
}
