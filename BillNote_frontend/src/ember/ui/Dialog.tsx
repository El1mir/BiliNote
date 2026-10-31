import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/ember/lib/cn'
import { Button } from '@/ember/ui/Button'
import { useI18n } from '@/ember/i18n/context'

type DialogProps = {
  open: boolean
  onClose: () => void
  title?: ReactNode
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  /** sm 420px · md 560px · lg 760px · xl 960px */
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

const SIZE = { sm: 'max-w-[420px]', md: 'max-w-[560px]', lg: 'max-w-[760px]', xl: 'max-w-[960px]' }

/**
 * Modal surface. Modals are exempt from trigger-origin scaling and stay centred.
 * Enter: fade + 8px rise + scale(0.97) — never scale(0). 240ms ease-out.
 */
export function Dialog({ open, onClose, title, description, children, footer, size = 'md', className }: DialogProps) {
  const { t } = useI18n()
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panelRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div
        className="ember-overlay absolute inset-0 bg-ink/25 backdrop-blur-[2px]"
        data-state="open"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        data-state="open"
        className={cn(
          'ember-dialog relative w-full rounded-t-surface border border-line bg-canvas shadow-float outline-none sm:rounded-surface',
          SIZE[size],
          className,
        )}
      >
        {(title || description) && (
          <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="flex flex-col gap-1">
              {title ? <h2 className="font-display text-subhead leading-snug">{title}</h2> : null}
              {description ? <p className="text-small text-ink-soft">{description}</p> : null}
            </div>
            <Button variant="ghost" size="sm" aria-label={t('common.close')} onClick={onClose} className="-mr-1 -mt-1 px-2">
              <X className="size-4" />
            </Button>
          </header>
        )}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer ? <footer className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  )
}
