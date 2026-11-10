import { useState } from 'react'
import { Activity, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import { getDeployStatus, getSysHealth } from '@/services/system'
import { useAsync } from '@/ember/lib/useAsync'
import { useI18n } from '@/ember/i18n/context'
import { Badge } from '@/ember/ui/Badge'
import { Button } from '@/ember/ui/Button'
import { Card } from '@/ember/ui/Card'
import { Skeleton } from '@/ember/ui/Skeleton'
import { SettingsLoadError, SettingsSection } from '@/ember/pages/settings/Section'

const Row = ({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) => {
  const { t } = useI18n()
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/70 py-3 last:border-b-0">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-small font-semibold text-ink">{label}</span>
        {detail ? <span className="truncate text-caption text-ink-soft">{detail}</span> : null}
      </div>
      <Badge tone={ok ? 'success' : 'danger'}>
        {ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
        {ok ? t('monitor.normal') : t('monitor.abnormal')}
      </Badge>
    </div>
  )
}

/** Live deployment status. Both requests fire together; either one failing leaves the other usable. */
export function MonitorSection() {
  const { t } = useI18n()
  const [nonce, setNonce] = useState(0)
  const health = useAsync(getSysHealth, [nonce])
  const deploy = useAsync(getDeployStatus, [nonce])

  const refresh = () => {
    setNonce(value => value + 1)
    health.reload()
    deploy.reload()
  }

  const loading = (health.loading && !health.data) || (deploy.loading && !deploy.data)

  return (
    <SettingsSection
      title={t('monitor.title')}
      description={t('monitor.subtitle')}
      actions={
        <Button size="sm" variant="secondary" onClick={refresh} loading={loading} disabled={loading}>
          <RefreshCw className="size-3.5" />
          {t('common.refresh')}
        </Button>
      }
    >
      {loading ? (
        <Skeleton className="h-56 w-full" />
      ) : health.error ? (
        <SettingsLoadError detail={t('monitor.connectError')} onRetry={refresh} />
      ) : (
        <div className="flex flex-col gap-4">
          <Card className="bg-canvas px-4 sm:px-5">
            <Row label={t('monitor.backendTitle')} ok={health.data?.backend === 'ok'} detail={deploy.data ? `port ${deploy.data.backend.port}` : undefined} />
            <Row label="FFmpeg" ok={health.data?.ffmpeg === 'ok'} />
            <Row label="SQLite" ok={health.data?.db === 'ok'} />
            <Row
              label={health.data?.whisper_model.type ?? 'transcriber'}
              ok={Boolean(health.data?.whisper_model.downloaded)}
              detail={health.data?.whisper_model.size ?? undefined}
            />
          </Card>

          {deploy.error ? (
            <Card className="bg-canvas p-5">
              <div className="flex items-center gap-2 text-small text-danger">
                <Activity className="size-4" />
                {t('settings.loadFailed')}
              </div>
            </Card>
          ) : deploy.data ? (
            <Card className="bg-canvas px-4 sm:px-5">
              <Row
                label="CUDA"
                ok={deploy.data.cuda.available}
                detail={deploy.data.cuda.gpu_name ?? (deploy.data.cuda.torch_installed === false ? 'torch not installed' : undefined)}
              />
              <Row
                label={deploy.data.whisper.transcriber_type}
                ok={deploy.data.whisper.downloaded}
                detail={deploy.data.whisper.model_size}
              />
              <Row label="FFmpeg" ok={deploy.data.ffmpeg.available} />
            </Card>
          ) : null}
        </div>
      )}
    </SettingsSection>
  )
}
