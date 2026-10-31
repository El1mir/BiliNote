import { useI18n } from '@/ember/i18n/context'
import { Card } from '@/ember/ui/Card'
import { Badge } from '@/ember/ui/Badge'
import { SettingsSection } from '@/ember/pages/settings/Section'

const STACK = [
  'React 19',
  'TypeScript',
  'Vite 6',
  'Tailwind CSS 4',
  'FastAPI',
  'SQLite',
  'faster-whisper',
]

export function AboutSection() {
  const { t } = useI18n()
  return (
    <SettingsSection title={t('settings.about')} description={t('settings.about.description')}>
      <Card className="bg-canvas p-5">
        <div className="flex flex-col gap-4">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-headline leading-none">BiliNote</span>
            <Badge tone="ember">v1.0.0</Badge>
          </div>
          <p className="max-w-2xl text-small leading-relaxed text-ink-soft">{t('settings.about.description')}</p>
          <div className="flex flex-col gap-2">
            <span className="ember-overline">{t('settings.about.stack')}</span>
            <div className="flex flex-wrap gap-1.5">
              {STACK.map(item => (
                <Badge key={item} tone="neutral">
                  {item}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </Card>
    </SettingsSection>
  )
}
