import { Moon, Sun } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { useTheme } from '@/ember/theme/theme'
import { Button } from '@/ember/ui/Button'

type Props = { compact?: boolean }

/**
 * Light/dark switch. Light is the default; the choice is persisted and painted
 * on <html> before React mounts (see initTheme), so a reload never flashes the
 * wrong palette.
 */
export function ThemeToggle({ compact }: Props) {
  const { t } = useI18n()
  const { theme, toggle } = useTheme()
  const dark = theme === 'dark'
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggle}
      aria-label={dark ? t('shell.theme.toLight') : t('shell.theme.toDark')}
      title={t('shell.theme.label')}
      className="gap-2"
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
      {compact ? null : <span>{t('shell.theme.label')}</span>}
    </Button>
  )
}