import { getDownloaderCookie, updateDownloaderCookie } from '@/services/downloader'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Field } from '@/ember/ui/Field'
import { Textarea } from '@/ember/ui/Input'
import { Badge } from '@/ember/ui/Badge'
import { Skeleton } from '@/ember/ui/Skeleton'
import { SaveStatus, SettingsLoadError, SettingsSection } from '@/ember/pages/settings/Section'
import { useSectionDraft } from '@/ember/pages/settings/useSectionDraft'
import { useSaveFeedback } from '@/ember/pages/settings/saveFeedback'

/** Only Bilibili remains in the generation chain, so this is a single field. */
export function DownloadSection() {
  const { t } = useI18n()
  const cookie = useAsync(async () => {
    const value = await getDownloaderCookie('bilibili')
    return typeof value === 'string' ? value : ((value as { cookie?: string })?.cookie ?? '')
  })
  // 草稿跨分区保留：Cookie 往往是从浏览器里粘出来的长串，切走丢一次就得重新复制。
  const [draft, setDraft] = useSectionDraft<string>('download')
  const { state: saveState, saving, run: runSave } = useSaveFeedback()

  const value = draft ?? cookie.data ?? ''
  // 读失败时 cookie.data 是 undefined、value 会回落成空串，
  // 此时保存就是拿空串覆盖服务端已有的 Cookie，所以直接禁掉。
  const blocked = Boolean(cookie.error) || cookie.loading

  const save = async () => {
    if (blocked) return
    await runSave(async () => {
      await updateDownloaderCookie({ cookie: value, platform: 'bilibili' })
      setDraft(undefined)
      cookie.reload()
    })
  }

  if (cookie.loading && !cookie.data) {
    return (
      <SettingsSection title={t('settings.download')} description={t('settings.download.cookieHint')}>
        <Skeleton className="h-40 w-full" />
      </SettingsSection>
    )
  }

  if (cookie.error) {
    return (
      <SettingsSection title={t('settings.download')} description={t('settings.download.cookieHint')}>
        <SettingsLoadError onRetry={cookie.reload} />
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title={t('settings.download')}
      description={t('settings.download.cookieHint')}
      actions={
        <>
          <SaveStatus state={saveState} />
          <Button
            variant="primary"
            size="sm"
            onClick={save}
            loading={saving}
            disabled={blocked}
          >
            {t('common.save')}
          </Button>
        </>
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
              value={value}
              spellCheck={false}
              placeholder="SESSDATA=…; bili_jct=…"
              onChange={event => setDraft(event.target.value)}
              className="font-mono text-caption"
            />
          </Field>
        </div>
      </Card>
    </SettingsSection>
  )
}
