import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  getGeneralSettings,
  updateGeneralSettings,
  type GeneralSettingsPatch,
} from '@/services/general'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Input } from '@/ember/ui/Input'
import { Skeleton } from '@/ember/ui/Skeleton'
import { Switch } from '@/ember/ui/Switch'
import { SettingRow, SettingsLoadError, SettingsSection } from '@/ember/pages/settings/Section'
import { useSectionDraft } from '@/ember/pages/settings/useSectionDraft'

/** 草稿在设置页内跨分区保留时用的 key。 */
const DRAFT_KEY = 'general'

/** Byte counts are shown as-is with a hint: a GB-precision field would silently lose exactness. */
const MiB = 1024 * 1024

/** Bytes -> MiB for display, keeping one decimal so 9.5 MiB survives a round trip. */
function toMiB(bytes: number): number {
  return Math.round((bytes / MiB) * 10) / 10
}

type NumericField =
  | 'max_parallel_notes'
  | 'cache_limit_bytes'
  | 'min_free_disk_bytes'
  | 'circuit_breaker_threshold'
  | 'asr_max_file_mb'
  | 'asr_max_duration_minutes'
  | 'asr_silence_noise_db'
  | 'asr_min_silence_seconds'
  | 'llm_max_request_bytes'
  | 'llm_judge_image_budget_bytes'
  | 'llm_retry_attempts'
  | 'llm_retry_backoff_seconds'
  | 'ocr_stage_concurrency'
  | 'note_max_images'
  | 'note_max_retries'
  | 'note_retry_backoff_seconds'
  | 'llm_rate_limit_cooldown_seconds'
  | 'llm_rate_limit_max_wait_seconds'
  | 'llm_rate_limit_resume_interval_seconds'
  | 'download_retries'
  | 'download_socket_timeout_seconds'
  | 'screenshot_max_width'
  | 'screenshot_quality'
  | 'ffmpeg_timeout_seconds'
  | 'ocr_max_judge_candidates'
/**
 * General settings.
 *
 * Grouped by *what the limit protects*, not by which module reads it: a user who
 * hits "音频太大" or "请求被网关 413" lands on the same screen and needs to see the
 * related knobs together. Every group renders from the same draft object, so one
 * Save commits whatever was touched.
 */
export function GeneralSection() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useAsync(getGeneralSettings)
  const [saving, setSaving] = useState(false)
  // 草稿存在跨卸载的仓库里：切到别的分区看一眼再回来，改过的数值还在。
  const [draft, setDraft] = useSectionDraft<GeneralSettingsPatch>(DRAFT_KEY)

  const patch = draft ?? {}
  const num = (key: NumericField) => (patch[key] as number | undefined) ?? data?.[key] ?? 0
  const setNum = (key: NumericField, raw: string) =>
    setDraft(next => ({ ...(next ?? {}), [key]: Number(raw) }))
  const mib = (key: 'llm_max_request_bytes' | 'llm_judge_image_budget_bytes') => toMiB(num(key))
  const setMiB = (key: 'llm_max_request_bytes' | 'llm_judge_image_budget_bytes', raw: string) =>
    setDraft(next => ({ ...(next ?? {}), [key]: Math.round(Number(raw) * MiB) }))
  const flag = (key: 'asr_silence_split') => patch[key] ?? data?.[key] ?? false

  const save = async () => {
    // 读失败时每个 num() 都会回落成 0，保存会把 26 个数值字段写成 0。
    if (error) return
    setSaving(true)
    try {
      await updateGeneralSettings(patch)
      toast.success(t('settings.saved'))
      setDraft(undefined)
      reload()
    } catch {
      toast.error(t('settings.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  if (loading && !data) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <SettingsSection title={t('settings.general')} description={t('settings.general.description')}>
        <SettingsLoadError onRetry={reload} />
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title={t('settings.general')}
      description={t('settings.general.description')}
      actions={
        <Button
          variant="primary"
          onClick={save}
          loading={saving}
          disabled={!Object.keys(patch).length || Boolean(error)}
        >
          {t('common.save')}
        </Button>
      }
    >
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h3 className="ember-overline text-ink-mute">{t('settings.general.group.runtime')}</h3>
          <Card className="bg-canvas px-4 sm:px-5">
            <SettingRow
              label={t('settings.general.maxParallel')}
              hint={t('settings.general.maxParallelHint')}
              control={
                <Input
                  type="number"
                  min={1}
                  max={data?.max_parallel_notes_limit ?? 16}
                  value={num('max_parallel_notes')}
                  onChange={event => setNum('max_parallel_notes', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.cacheLimit')}
              hint={t('settings.general.cacheLimitHint') + ' · ' + t('settings.general.bytesHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  value={num('cache_limit_bytes')}
                  onChange={event => setNum('cache_limit_bytes', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.minFreeDisk')}
              hint={t('settings.general.minFreeDiskHint') + ' · ' + t('settings.general.bytesHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  value={num('min_free_disk_bytes')}
                  onChange={event => setNum('min_free_disk_bytes', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.circuitBreaker')}
              hint={t('settings.general.circuitBreakerHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  value={num('circuit_breaker_threshold')}
                  onChange={event => setNum('circuit_breaker_threshold', event.target.value)}
                />
              }
            />
          </Card>
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="ember-overline text-ink-mute">{t('settings.general.group.asr')}</h3>
          <Card className="bg-canvas px-4 sm:px-5">
            <SettingRow
              label={t('settings.general.asrMaxFile')}
              hint={t('settings.general.asrMaxFileHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.asr_max_file_mb_limit ?? undefined}
                  value={num('asr_max_file_mb')}
                  onChange={event => setNum('asr_max_file_mb', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.asrMaxDuration')}
              hint={t('settings.general.asrMaxDurationHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.asr_max_duration_minutes_limit ?? undefined}
                  value={num('asr_max_duration_minutes')}
                  onChange={event => setNum('asr_max_duration_minutes', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.silenceSplit')}
              hint={t('settings.general.silenceSplitHint')}
              control={
                <Switch
                  checked={flag('asr_silence_split')}
                  onChange={checked =>
                    setDraft(next => ({ ...(next ?? {}), asr_silence_split: checked }))
                  }
                  label={t('settings.general.silenceSplit')}
                />
              }
            />
            <SettingRow
              label={t('settings.general.silenceNoise')}
              hint={t('settings.general.silenceNoiseHint')}
              control={
                <Input
                  type="number"
                  step={0.5}
                  min={data?.asr_silence_noise_db_min ?? undefined}
                  max={data?.asr_silence_noise_db_max ?? undefined}
                  value={num('asr_silence_noise_db')}
                  onChange={event => setNum('asr_silence_noise_db', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.minSilence')}
              hint={t('settings.general.minSilenceHint')}
              control={
                <Input
                  type="number"
                  step={0.05}
                  min={data?.asr_min_silence_seconds_min ?? undefined}
                  max={data?.asr_min_silence_seconds_max ?? undefined}
                  value={num('asr_min_silence_seconds')}
                  onChange={event => setNum('asr_min_silence_seconds', event.target.value)}
                />
              }
            />
          </Card>
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="ember-overline text-ink-mute">{t('settings.general.group.llm')}</h3>
          <Card className="bg-canvas px-4 sm:px-5">
            <SettingRow
              label={t('settings.general.llmRequest')}
              hint={t('settings.general.llmRequestHint') + ' · ' + t('settings.general.mibUnit')}
              control={
                <Input
                  type="number"
                  step={0.5}
                  min={1}
                  max={toMiB(data?.llm_max_request_bytes_max ?? MiB)}
                  value={mib('llm_max_request_bytes')}
                  onChange={event => setMiB('llm_max_request_bytes', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.judgeImage')}
              hint={t('settings.general.judgeImageHint') + ' · ' + t('settings.general.mibUnit')}
              control={
                <Input
                  type="number"
                  step={0.5}
                  min={0.5}
                  value={mib('llm_judge_image_budget_bytes')}
                  onChange={event => setMiB('llm_judge_image_budget_bytes', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.retryAttempts')}
              hint={t('settings.general.retryAttemptsHint')}
              control={
                <Input
                  type="number"
                  min={1}
                  max={data?.llm_retry_attempts_limit ?? 10}
                  value={num('llm_retry_attempts')}
                  onChange={event => setNum('llm_retry_attempts', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.retryBackoff')}
              hint={t('settings.general.retryBackoffHint')}
              control={
                <Input
                  type="number"
                  step={0.1}
                  min={0}
                  max={data?.llm_retry_backoff_seconds_limit ?? 60}
                  value={num('llm_retry_backoff_seconds')}
                  onChange={event => setNum('llm_retry_backoff_seconds', event.target.value)}
                />
              }
            />
          </Card>
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="ember-overline text-ink-mute">{t('settings.general.group.ocr')}</h3>
          <Card className="bg-canvas px-4 sm:px-5">
            <SettingRow
              label={t('settings.general.ocrConcurrency')}
              hint={t('settings.general.ocrConcurrencyHint')}
              control={
                <Input
                  type="number"
                  min={1}
                  max={data?.ocr_stage_concurrency_limit ?? 32}
                  value={num('ocr_stage_concurrency')}
                  onChange={event => setNum('ocr_stage_concurrency', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.noteMaxImages')}
              hint={t('settings.general.noteMaxImagesHint')}
              control={
                <Input
                  type="number"
                  min={1}
                  max={data?.note_max_images_limit ?? 500}
                  value={num('note_max_images')}
                  onChange={event => setNum('note_max_images', event.target.value)}
                />
              }
            />
          </Card>
        </div>

        <div className="flex flex-col gap-2.5">
          <h3 className="ember-overline text-ink-mute">{t('settings.general.group.shot')}</h3>
          <Card className="bg-canvas px-4 sm:px-5">
            <SettingRow
              label={t('settings.general.shotMaxWidth')}
              hint={t('settings.general.shotMaxWidthHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.screenshot_max_width_limit ?? 7680}
                  value={num('screenshot_max_width')}
                  onChange={event => setNum('screenshot_max_width', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.shotQuality')}
              hint={t('settings.general.shotQualityHint')}
              control={
                <Input
                  type="number"
                  min={data?.screenshot_quality_min ?? 1}
                  max={data?.screenshot_quality_max ?? 31}
                  value={num('screenshot_quality')}
                  onChange={event => setNum('screenshot_quality', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.ffmpegTimeout')}
              hint={t('settings.general.ffmpegTimeoutHint')}
              control={
                <Input
                  type="number"
                  min={data?.ffmpeg_timeout_seconds_min ?? 10}
                  max={data?.ffmpeg_timeout_seconds_max ?? 600}
                  value={num('ffmpeg_timeout_seconds')}
                  onChange={event => setNum('ffmpeg_timeout_seconds', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.judgeCandidates')}
              hint={t('settings.general.judgeCandidatesHint')}
              control={
                <Input
                  type="number"
                  min={1}
                  max={data?.ocr_max_judge_candidates_limit ?? 1000}
                  value={num('ocr_max_judge_candidates')}
                  onChange={event => setNum('ocr_max_judge_candidates', event.target.value)}
                />
              }
            />
          </Card>
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="ember-overline text-ink-mute">{t('settings.general.group.retry')}</h3>
          <Card className="bg-canvas px-4 sm:px-5">
            <SettingRow
              label={t('settings.general.noteMaxRetries')}
              hint={t('settings.general.noteMaxRetriesHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.note_max_retries_limit ?? 10}
                  value={num('note_max_retries')}
                  onChange={event => setNum('note_max_retries', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.noteRetryBackoff')}
              hint={t('settings.general.noteRetryBackoffHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  step={0.5}
                  max={data?.note_retry_backoff_seconds_limit ?? undefined}
                  value={num('note_retry_backoff_seconds')}
                  onChange={event => setNum('note_retry_backoff_seconds', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.rateLimitCooldown')}
              hint={t('settings.general.rateLimitCooldownHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.llm_rate_limit_cooldown_seconds_limit ?? undefined}
                  value={num('llm_rate_limit_cooldown_seconds')}
                  onChange={event => setNum('llm_rate_limit_cooldown_seconds', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.rateLimitMaxWait')}
              hint={t('settings.general.rateLimitMaxWaitHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.llm_rate_limit_max_wait_seconds_limit ?? undefined}
                  value={num('llm_rate_limit_max_wait_seconds')}
                  onChange={event => setNum('llm_rate_limit_max_wait_seconds', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.rateLimitResume')}
              hint={t('settings.general.rateLimitResumeHint')}
              control={
                <Input
                  type="number"
                  min={data?.llm_rate_limit_resume_interval_seconds_min ?? 10}
                  max={data?.llm_rate_limit_resume_interval_seconds_max ?? undefined}
                  value={num('llm_rate_limit_resume_interval_seconds')}
                  onChange={event =>
                    setNum('llm_rate_limit_resume_interval_seconds', event.target.value)
                  }
                />
              }
            />
            <SettingRow
              label={t('settings.general.downloadRetries')}
              hint={t('settings.general.downloadRetriesHint')}
              control={
                <Input
                  type="number"
                  min={0}
                  max={data?.download_retries_limit ?? 10}
                  value={num('download_retries')}
                  onChange={event => setNum('download_retries', event.target.value)}
                />
              }
            />
            <SettingRow
              label={t('settings.general.downloadSocketTimeout')}
              hint={t('settings.general.downloadSocketTimeoutHint')}
              control={
                <Input
                  type="number"
                  min={data?.download_socket_timeout_seconds_min ?? 5}
                  max={data?.download_socket_timeout_seconds_max ?? undefined}
                  value={num('download_socket_timeout_seconds')}
                  onChange={event => setNum('download_socket_timeout_seconds', event.target.value)}
                />
              }
            />
          </Card>
        </div>
      </div>
    </SettingsSection>
  )
}
