import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/ember/lib/cn'
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
 */
export function Drawer({ open, onClose, title, side = 'left', children, className }: DrawerProps) {
  const { t } = useI18n()
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="ember-overlay absolute inset-0 bg-ink/25 backdrop-blur-[2px]" data-state="open" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        data-state="open"
        className={cn(
          'ember-drawer absolute inset-y-0 flex w-[min(88vw,320px)] flex-col border-line bg-canvas shadow-float',
          side === 'left' ? 'left-0 border-r' : 'right-0 border-l',
          className,
        )}
      >
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <span className="font-display text-subhead">{title}</span>
          <Button variant="ghost" size="sm" aria-label={t('common.close')} onClick={onClose} className="px-2">
            <X className="size-4" />
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
      </aside>
    </div>,
    document.body,
  )
}
