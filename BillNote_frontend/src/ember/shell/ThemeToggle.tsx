import { Monitor, Moon, Sun } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { useTheme, type Theme } from '@/ember/theme/theme'
import { Button } from '@/ember/ui/Button'

type Props = { compact?: boolean }

const ICON: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Monitor }
const KEY: Record<Theme, 'shell.theme.light' | 'shell.theme.dark' | 'shell.theme.system'> = {
  light: 'shell.theme.light',
  dark: 'shell.theme.dark',
  system: 'shell.theme.system',
}

/**
 * Three-state theme switch: light → dark → system → light.
 *
 * The choice is persisted and painted on <html> before React mounts (see
 * initTheme), so a reload never flashes the wrong palette. 'system' keeps
 * following the OS while the app is open.
 */
export function ThemeToggle({ compact }: Props) {
  const { t } = useI18n()
  const { theme, cycle } = useTheme()
  const Icon = ICON[theme]
  const current = t(KEY[theme])

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={cycle}
      aria-label={`${t('shell.theme.label')}: ${current}`}
      title={`${t('shell.theme.label')}: ${current}`}
      className="gap-2"
    >
      <Icon className="size-4" aria-hidden="true" />
      {compact ? null : <span>{current}</span>}
    </Button>
  )
}