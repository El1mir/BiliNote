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
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Dialog } from '@/ember/ui/Dialog'
import { Input } from '@/ember/ui/Input'
import { scopeExpiredOnly, type CleanupScope } from '@/ember/pages/settings/cleanupScopes'
import { Skeleton } from '@/ember/ui/Skeleton'
import { SaveStatus, SettingRow, SettingsLoadError, SettingsSection } from '@/ember/pages/settings/Section'
import { useSectionDraft } from '@/ember/pages/settings/useSectionDraft'
import { useSaveFeedback } from '@/ember/pages/settings/saveFeedback'

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
  // 保留天数草稿跨分区保留：切去 Prompt 看一眼再回来，改过的天数还在。
  const [draft, setDraft] = useSectionDraft<Record<string, number>>('media')
  const [preview, setPreview] = useState<{ scope: CleanupScope; data: CleanupPreview } | null>(null)
  const [busy, setBusy] = useState(false)
  const { state: saveState, saving, run: runSave } = useSaveFeedback()
  /** 待确认的动作；非 null 时弹出确认框。清理会删文件，不能只有一次点击。 */
  const [pending, setPending] = useState<CleanupScope | null>(null)

  const screenshotDays = draft?.screenshot_retention_days ?? retention.data?.screenshot_retention_days ?? 0
  const mediaDays = draft?.media_retention_days ?? retention.data?.media_retention_days ?? 0

  const readFailed = Boolean(retention.error)

  const save = async () => {
    // 读失败时 retention_days 会回落成 0，保存等于把保留期改成 0（立即过期）。
    if (readFailed) return
    await runSave(async () => {
      await saveRetentionSettings({
        screenshot_retention_days: screenshotDays,
        media_retention_days: mediaDays,
      })
      setDraft(undefined)
      retention.reload()
    })
  }

  const refreshPreview = async (scope: CleanupScope) => {
    setBusy(true)
    try {
      // 预览与执行共用同一个 expired_only 口径，数字才对得上。
      setPreview({ scope, data: await previewMediaCleanup(RESOURCE_TYPES, scopeExpiredOnly(scope)) })
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const clean = async (scope: CleanupScope) => {
    setPending(null)
    setBusy(true)
    try {
      const outcome = await runMediaCleanup(RESOURCE_TYPES, scopeExpiredOnly(scope))
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

  if (readFailed) {
    return (
      <div className="flex flex-col gap-8">
        <SettingsSection title={t('settings.media.retention')} description={t('settings.media.retentionHint')}>
          <SettingsLoadError onRetry={retention.reload} />
        </SettingsSection>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection
        title={t('settings.media.retention')}
        description={t('settings.media.retentionHint')}
        actions={
          <>
            <SaveStatus state={saveState} />
            <Button size="sm" variant="primary" onClick={save} loading={saving} disabled={readFailed}>
              {t('common.save')}
            </Button>
          </>
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
              <Button size="sm" variant="secondary" onClick={() => refreshPreview('expired')} loading={busy}>
                {t('settings.media.refreshPreview')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => refreshPreview('all')} disabled={busy}>
                {t('settings.media.previewAll')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setPending('expired')} disabled={busy}>
                <Trash2 className="size-3.5" />
                {t('settings.media.cleanupExpired')}
              </Button>
              <Button size="sm" variant="destructive" onClick={() => setPending('all')} disabled={busy}>
                {t('settings.media.cleanupAll')}
              </Button>
            </div>

            {preview ? (
              <div className="ember-enter flex flex-wrap items-center gap-3 rounded-control bg-surface px-3 py-2.5">
                <HardDrive className="size-4 text-ink-mute" />
                <Badge tone={preview.scope === 'all' ? 'danger' : 'neutral'}>
                  {t(preview.scope === 'all' ? 'settings.media.scopeAll' : 'settings.media.scopeExpired')}
                </Badge>
                <span className="text-small text-ink">
                  {t('settings.media.deleted', { count: preview.data.count })} ·{' '}
                  {t('settings.media.freed', { size: formatBytes(preview.data.bytes) })}
                </span>
                <Button size="sm" variant="primary" onClick={() => setPending(preview.scope)} disabled={busy}>
                  {t('settings.media.runPreviewed')}
                </Button>
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

      <Dialog
        open={pending !== null}
        onClose={() => setPending(null)}
        size="sm"
        title={t('settings.media.confirmTitle')}
        description={
          pending === null
            ? undefined
            : preview && preview.scope === pending
              ? t('settings.media.confirmBody', { count: preview.data.count })
              : t('settings.media.confirmNoPreview')
        }
        footer={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setPending(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => pending && void clean(pending)}
            >
              {t('common.confirm')}
            </Button>
          </div>
        }
      >
        <p className="text-small text-ink-soft">
          {t(pending === 'all' ? 'settings.media.cleanupAllHint' : 'settings.media.cleanupExpiredHint')}
        </p>
      </Dialog>
    </div>
  )
}
