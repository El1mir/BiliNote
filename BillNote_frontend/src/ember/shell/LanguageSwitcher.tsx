import { Languages } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'

type Props = { compact?: boolean }

/**
 * Locale toggle.
 *
 * Reads the Ember i18n context, which owns the `bilinote-locale` key — the
 * preserved data layer exposes `changeLocale` under a different name, and
 * calling the wrong one threw `setLocale is not a function` on click.
 */
export function LanguageSwitcher({ compact }: Props) {
  const { locale, setLocale } = useI18n()
  const next = locale === 'zh-CN' ? 'en-US' : 'zh-CN'
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setLocale(next)}
      aria-label={locale === 'zh-CN' ? 'Switch to English' : '切换为中文'}
      className="gap-2"
    >
      <Languages className="size-4" />
      {compact ? null : <span>{locale === 'zh-CN' ? '中文' : 'EN'}</span>}
    </Button>
  )
}
