import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { getDownloaderCookie, updateDownloaderCookie } from '@/services/downloader'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Field } from '@/ember/ui/Field'
import { Textarea } from '@/ember/ui/Input'
import { Badge } from '@/ember/ui/Badge'
import { SettingsSection } from '@/ember/pages/settings/Section'

/** Only Bilibili remains in the generation chain, so this is a single field. */
export function DownloadSection() {
  const { t } = useI18n()
  const [cookie, setCookie] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    getDownloaderCookie('bilibili')
      .then(value => {
        if (cancelled) return
        setCookie(typeof value === 'string' ? value : ((value as { cookie?: string })?.cookie ?? ''))
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await updateDownloaderCookie({ cookie, platform: 'bilibili' })
      toast.success(t('settings.download.saved'))
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <SettingsSection
      title={t('settings.download')}
      description={t('settings.download.cookieHint')}
      actions={
        <Button variant="primary" size="sm" onClick={save} loading={saving} disabled={loading}>
          {t('common.save')}
        </Button>
      }
    >
      <Card className="bg-canvas p-4 sm:p-5">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="ember-overline">{t('settings.download.platform')}</span>
            <Badge tone="ember">{t('platform.bilibili')}</Badge>
          </div>
          <Field label={t('settings.download.cookie')} htmlFor="cookie" hint={t('settings.download.cookieHint')}>
            <Textarea
              id="cookie"
              rows={5}
              value={cookie}
              spellCheck={false}
              placeholder="SESSDATA=…; bili_jct=…"
              onChange={event => setCookie(event.target.value)}
              className="font-mono text-caption"
            />
          </Field>
        </div>
      </Card>
    </SettingsSection>
  )
}
