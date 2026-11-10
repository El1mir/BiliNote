import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/ember/lib/cn'
import { useOverlayFocus } from '@/ember/lib/overlayFocus'
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
 *
 * 焦点：打开时移进面板，Tab 在面板内回绕，关闭后还给触发元素（见 useOverlayFocus）。
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
  className,
}: DialogProps) {
  const { t } = useI18n()
  const panelRef = useRef<HTMLDivElement>(null)
  const generatedId = useId().replace(/:/g, '')
  const titleId = `dialog-title-${generatedId}`
  const descriptionId = `dialog-desc-${generatedId}`

  useOverlayFocus({ open, onClose, panelRef })

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div
        className="ember-overlay bg-ink/25 absolute inset-0 backdrop-blur-[2px]"
        data-state="open"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        data-state="open"
        className={cn(
          'ember-dialog rounded-t-surface border-line bg-canvas shadow-float sm:rounded-surface relative w-full border outline-none',
          SIZE[size],
          className
        )}
      >
        {(title || description) && (
          <header className="border-line flex items-start justify-between gap-4 border-b px-5 py-4">
            <div className="flex flex-col gap-1">
              {title ? (
                <h2 id={titleId} className="font-display text-subhead leading-snug">
                  {title}
                </h2>
              ) : null}
              {description ? (
                <p id={descriptionId} className="text-small text-ink-soft">
                  {description}
                </p>
              ) : null}
            </div>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('common.close')}
              onClick={onClose}
              className="-mt-1 -mr-1 px-2"
            >
              <X className="size-4" />
            </Button>
          </header>
        )}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <footer className="border-line flex items-center justify-end gap-2 border-t px-5 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body
  )
}
