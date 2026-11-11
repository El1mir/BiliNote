import { useId, type ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'
import { FieldContext } from '@/ember/ui/fieldContext'

type FieldProps = {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  error?: ReactNode
  required?: boolean
  className?: string
  children: ReactNode
}

/**
 * Label (14px semibold) above the control, hint and error beneath.
 *
 * 错误/提示节点带 id，控件通过 FieldContext 取到它写进 aria-describedby，
 * 并在有错误时置 aria-invalid —— 否则读屏用户只听到"输入框"，
 * 听不到"这个值不合法，原因是……"。
 */
export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  const generatedId = useId()
  const controlId = htmlFor ?? `field-${generatedId.replace(/:/g, '')}`
  const messageId = `${controlId}-message`
  const hasMessage = Boolean(error) || Boolean(hint)

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={controlId} className="text-small font-semibold text-ink">
        {label}
        {required ? <span className="ml-0.5 text-primary">*</span> : null}
      </label>
      <FieldContext.Provider
        value={{
          controlId,
          describedBy: hasMessage ? messageId : undefined,
          invalid: Boolean(error),
        }}
      >
        {children}
      </FieldContext.Provider>
      {error ? (
        <p id={messageId} className="text-caption text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={messageId} className="text-caption text-ink-soft">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
