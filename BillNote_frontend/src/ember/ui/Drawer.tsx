import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/ember/lib/cn'
import { useOverlayFocus } from '@/ember/lib/overlayFocus'
import { Button } from '@/ember/ui/Button'
import { useI18n } from '@/ember/i18n/context'

type DrawerProps = {
  open: boolean
  onClose: () => void
  title?: ReactNode
  side?: 'left' | 'right'
  children: ReactNode
  className?: string
}

/**
 * Mobile navigation / side panel. Slides in from the edge it dismisses to,
 * so the exit path mirrors the entry path. 280ms drawer curve.
 *
 * 焦点与滚动锁和 Dialog 共用一套（useOverlayFocus）：打开时移进面板、
 * Tab 回绕、Escape 关闭、关闭后还给触发元素；body 滚动在这里一并锁住。
 */
export function Drawer({ open, onClose, title, side = 'left', children, className }: DrawerProps) {
  const { t } = useI18n()
  const panelRef = useRef<HTMLElement>(null)
  const generatedId = useId().replace(/:/g, '')
  const titleId = `drawer-title-${generatedId}`

  useOverlayFocus({ open, onClose, panelRef })

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 lg:hidden">
      <div
        className="ember-overlay bg-ink/25 absolute inset-0 backdrop-blur-[2px]"
        data-state="open"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        data-state="open"
        className={cn(
          'ember-drawer border-line bg-canvas shadow-float absolute inset-y-0 flex w-[min(88vw,320px)] flex-col outline-none',
          side === 'left' ? 'left-0 border-r' : 'right-0 border-l',
          className
        )}
      >
        <header className="border-line flex items-center justify-between gap-3 border-b px-4 py-3">
          <span id={titleId} className="font-display text-subhead">
            {title}
          </span>
          <Button
            variant="ghost"
            size="sm"
            aria-label={t('common.close')}
            onClick={onClose}
            className="px-2"
          >
            <X className="size-4" />
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
      </aside>
    </div>,
    document.body
  )
}
