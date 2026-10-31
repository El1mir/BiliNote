import { useState } from 'react'
import toast from 'react-hot-toast'
import { HardDrive, Trash2 } from 'lucide-react'
import {
  getRecentCleanupRuns,
  getRetentionSettings,
  previewMediaCleanup,
  runMediaCleanup,
  saveRetentionSettings,
  type CleanupPreview,
} from '@/services/media'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Input } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { SettingRow, SettingsSection } from '@/ember/pages/settings/Section'

const RESOURCE_TYPES = ['video', 'audio', 'screenshot']

const formatBytes = (bytes: number): string => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

/** Retention plus manual cleanup. The preview is the confirmation step before deleting anything. */
export function MediaSection() {
  const { t } = useI18n()
  const retention = useAsync(getRetentionSettings)
  const runs = useAsync(getRecentCleanupRuns)
  const [draft, setDraft] = useState<Record<string, number>>({})
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [busy, setBusy] = useState(false)

  const screenshotDays = draft.screenshot_retention_days ?? retention.data?.screenshot_retention_days ?? 0
  const mediaDays = draft.media_retention_days ?? retention.data?.media_retention_days ?? 0

  const save = async () => {
    setBusy(true)
    try {
      await saveRetentionSettings({
        screenshot_retention_days: screenshotDays,
        media_retention_days: mediaDays,
      })
      toast.success(t('settings.saved'))
      setDraft({})
      retention.reload()
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const refreshPreview = async () => {
    setBusy(true)
    try {
      setPreview(await previewMediaCleanup(RESOURCE_TYPES, true))
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const clean = async (expiredOnly: boolean) => {
    setBusy(true)
    try {
      const outcome = await runMediaCleanup(RESOURCE_TYPES, expiredOnly)
      toast.success(
        `${t('settings.media.deleted', { count: outcome.result.deleted })} · ${t('settings.media.freed', {
          size: formatBytes(outcome.result.bytes),
        })}`,
      )
      runs.reload()
      setPreview(null)
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  if (retention.loading && !retention.data) return <Skeleton className="h-72 w-full" />

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection
        title={t('settings.media.retention')}
        description={t('settings.media.retentionHint')}
        actions={
          <Button size="sm" variant="primary" onClick={save} loading={busy}>
            {t('common.save')}
          </Button>
        }
      >
        <Card className="bg-canvas px-4 sm:px-5">
          <SettingRow
            label={t('settings.media.screenshotDays')}
            control={
              <Input
                type="number"
                min={0}
                value={screenshotDays}
                onChange={event =>
                  setDraft(current => ({ ...current, screenshot_retention_days: Number(event.target.value) }))
                }
              />
            }
          />
          <SettingRow
            label={t('settings.media.mediaDays')}
            control={
              <Input
                type="number"
                min={0}
                value={mediaDays}
                onChange={event =>
                  setDraft(current => ({ ...current, media_retention_days: Number(event.target.value) }))
                }
              />
            }
          />
        </Card>
      </SettingsSection>

      <SettingsSection title={t('settings.media.cleanup')} description={t('settings.media.retentionHint')}>
        <Card className="bg-canvas p-4 sm:p-5">
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" onClick={refreshPreview} loading={busy}>
                {t('settings.media.refreshPreview')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => clean(true)} disabled={busy}>
                <Trash2 className="size-3.5" />
                {t('settings.media.cleanupExpired')}
              </Button>
              <Button size="sm" variant="destructive" onClick={() => clean(false)} disabled={busy}>
                {t('settings.media.cleanupAll')}
              </Button>
            </div>

            {preview ? (
              <div className="ember-enter flex items-center gap-3 rounded-control bg-surface px-3 py-2.5">
                <HardDrive className="size-4 text-ink-mute" />
                <span className="text-small text-ink">
                  {t('settings.media.deleted', { count: preview.count })} ·{' '}
                  {t('settings.media.freed', { size: formatBytes(preview.bytes) })}
                </span>
              </div>
            ) : null}

            <div className="flex flex-col gap-2">
              <span className="ember-overline">{t('settings.media.recentRuns')}</span>
              {runs.data?.length ? (
                <ul className="flex flex-col divide-y divide-line/70">
                  {runs.data.slice(0, 6).map((run, index) => (
                    <li key={index} className="flex items-center justify-between gap-3 py-2 text-caption">
                      <span className="text-ink-soft">{new Date(run.completed_at).toLocaleString()}</span>
                      <span className="text-ink">
                        {t('settings.media.deleted', { count: run.deleted })} ·{' '}
                        {t('settings.media.freed', { size: formatBytes(run.bytes_freed) })}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-caption text-ink-mute">{t('settings.media.noRuns')}</span>
              )}
            </div>
          </div>
        </Card>
      </SettingsSection>
    </div>
  )
}
