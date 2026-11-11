import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'
import { useFieldControlA11y } from '@/ember/ui/fieldContext'

const BASE =
  'w-full rounded-control border border-line-strong bg-surface px-3 py-2.5 text-body text-ink ' +
  'placeholder:text-ink-mute transition-[border-color,box-shadow] ease-[var(--ease)] duration-[var(--dur-hover)] ' +
  'focus-visible:border-primary focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring ' +
  'aria-[invalid=true]:border-danger ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

/**
 * BiliNote workbench input — surface fill, 8px radius, 12px padding, Accent focus ring.
 *
 * 焦点环用 focus-visible：鼠标点击不再留环，键盘 Tab 到时才出现。
 * 在 <Field> 内时自动继承 id / aria-describedby / aria-invalid，调用方显式传入的值优先。
 */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input(
    { className, id, 'aria-describedby': describedBy, 'aria-invalid': invalid, ...rest },
    ref
  ) {
    const field = useFieldControlA11y()
    return (
      <input
        ref={ref}
        id={id ?? field?.controlId}
        aria-describedby={describedBy ?? field?.describedBy}
        aria-invalid={invalid ?? (field?.invalid ? true : undefined)}
        className={cn(BASE, 'h-10 py-0', className)}
        {...rest}
      />
    )
  }
)

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea(
  { className, id, 'aria-describedby': describedBy, 'aria-invalid': invalid, ...rest },
  ref
) {
  const field = useFieldControlA11y()
  return (
    <textarea
      ref={ref}
      id={id ?? field?.controlId}
      aria-describedby={describedBy ?? field?.describedBy}
      aria-invalid={invalid ?? (field?.invalid ? true : undefined)}
      className={cn(BASE, 'resize-y leading-relaxed', className)}
      {...rest}
    />
  )
})
