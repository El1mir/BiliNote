import type { ReactNode } from 'react'
import { RefreshCw, TriangleAlert } from 'lucide-react'
import { cn } from '@/ember/lib/cn'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'

type SettingsSectionProps = {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}

/** A titled block inside a settings screen. Headings are the only Playfair text here. */
export function SettingsSection({ title, description, actions, children, className }: SettingsSectionProps) {
  return (
    <section className={cn('flex flex-col gap-4', className)}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="font-display text-section leading-tight">{title}</h2>
          {description ? <p className="max-w-2xl text-small text-ink-soft">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}

type SettingsLoadErrorProps = {
  /** 失败的是什么；缺省只说明"未能读取设置"。 */
  detail?: ReactNode
  onRetry: () => void
  className?: string
}

/**
 * 读失败时的统一落点：说明 + 重试，且**不渲染任何可编辑控件**。
 *
 * 设置页的加载失败以前会被当成"空配置"渲染（数值回落 0、字符串回落空串），
 * 用户一按保存就把空值写回后端。所以这里的原则是"读不到就不给改"，
 * 每个分区在 error 分支直接替换成这个组件，而不是把错误提示叠在表单上方。
 */
export function SettingsLoadError({ detail, onRetry, className }: SettingsLoadErrorProps) {
  const { t } = useI18n()

  return (
    <Card role="alert" className={cn('bg-canvas p-5', className)}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-small font-semibold text-danger">
          <TriangleAlert className="size-4" />
          {t('settings.loadFailed')}
        </div>
        <p className="max-w-2xl text-caption text-ink-soft">
          {detail ?? t('settings.loadFailedHint')}
        </p>
        <Button size="sm" variant="secondary" onClick={onRetry} className="self-start">
          <RefreshCw className="size-3.5" />
          {t('common.retry')}
        </Button>
      </div>
    </Card>
  )
}

type SettingRowProps = {
  label: ReactNode
  hint?: ReactNode
  control: ReactNode
  className?: string
}

/** Label + hint on the left, control on the right; stacks on narrow screens. */
export function SettingRow({ label, hint, control, className }: SettingRowProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 border-b border-line/70 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-small font-semibold text-ink">{label}</span>
        {hint ? <span className="text-caption text-ink-soft">{hint}</span> : null}
      </div>
      <div className="shrink-0 sm:w-64">{control}</div>
    </div>
  )
}
