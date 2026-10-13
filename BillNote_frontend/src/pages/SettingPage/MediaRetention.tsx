import { useCallback, useEffect, useState } from 'react'
import { toast } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  getRecentCleanupRuns,
  getRetentionSettings,
  previewMediaCleanup,
  runMediaCleanup,
  saveRetentionSettings,
  type CleanupPreview,
  type CleanupRun,
  type RetentionSettings,
} from '@/services/media'

const TYPES = ['screenshot', 'video', 'audio']
const LABELS: Record<string, string> = { screenshot: '截图', video: '视频', audio: '音频' }
const formatBytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

export default function MediaRetention() {
  const [settings, setSettings] = useState<RetentionSettings>({
    screenshot_retention_days: 7,
    media_retention_days: 3,
  })
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [runs, setRuns] = useState<CleanupRun[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    const [nextPreview, nextRuns] = await Promise.all([
      previewMediaCleanup(TYPES, true),
      getRecentCleanupRuns(),
    ])
    setPreview(nextPreview)
    setRuns(nextRuns)
  }, [])

  useEffect(() => {
    getRetentionSettings()
      .then(setSettings)
      .catch(() => toast.error('读取保留期设置失败'))
    refresh().catch(() => toast.error('读取媒体资源状态失败'))
  }, [refresh])

  const save = async () => {
    setLoading(true)
    try {
      setSettings(await saveRetentionSettings(settings))
      toast.success('保留期设置已保存')
    } catch (error) {
      toast.error((error as Error)?.message || '保存失败')
    } finally {
      setLoading(false)
    }
  }

  const clean = async (expiredOnly: boolean) => {
    try {
      const current = await previewMediaCleanup(TYPES, expiredOnly)
      setPreview(current)
      if (!current.count) {
        toast('没有符合条件的资源')
        return
      }
      const scope = TYPES.map(
        type => `${LABELS[type]} ${current.by_type[type]?.count || 0} 个`
      ).join('、')
      const suffix = expiredOnly ? '已到期' : '全部受管'
      if (
        !window.confirm(
          `将${suffix}清理 ${scope}，共 ${current.count} 个、${formatBytes(current.bytes)}。此操作不可恢复，继续吗？`
        )
      )
        return
      setLoading(true)
      const response = await runMediaCleanup(TYPES, expiredOnly)
      const { deleted, missing, failed, bytes } = response.result
      toast.success(
        `清理完成：删除 ${deleted} 个，缺失 ${missing} 个，失败 ${failed} 个，释放 ${formatBytes(bytes)}`
      )
      await refresh()
    } catch (error) {
      toast.error((error as Error)?.message || '清理失败')
    } finally {
      setLoading(false)
    }
  }

  const setDays = (key: keyof RetentionSettings, value: string) => {
    const parsed = Number(value)
    const days = Number.isFinite(parsed) ? Math.max(0, Math.min(36500, Math.floor(parsed))) : 0
    setSettings(current => ({ ...current, [key]: days }))
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">媒体资源管理</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            保留期只影响之后生成的文件；0 表示不自动到期。
          </p>
        </div>
        <section className="space-y-4 rounded-lg border p-5">
          <h2 className="text-lg font-medium">自动保留期</h2>
          <label className="block space-y-2 text-sm">
            截图保留天数
            <Input
              type="number"
              min="0"
              max="36500"
              step="1"
              value={settings.screenshot_retention_days}
              onChange={event => setDays('screenshot_retention_days', event.target.value)}
            />
          </label>
          <label className="block space-y-2 text-sm">
            视频和音频保留天数
            <Input
              type="number"
              min="0"
              max="36500"
              step="1"
              value={settings.media_retention_days}
              onChange={event => setDays('media_retention_days', event.target.value)}
            />
          </label>
          <Button disabled={loading} onClick={() => void save()}>
            保存设置
          </Button>
        </section>
        <section className="space-y-4 rounded-lg border p-5">
          <h2 className="text-lg font-medium">资源清理</h2>
          <Button
            variant="outline"
            disabled={loading}
            onClick={() => void refresh().catch(() => toast.error('刷新失败'))}
          >
            刷新到期预览
          </Button>
          {preview && (
            <p className="text-sm">
              符合条件 {preview.count} 个，共 {formatBytes(preview.bytes)}
              {preview.expires_earliest && preview.expires_latest
                ? `；到期范围 ${new Date(preview.expires_earliest).toLocaleString()} – ${new Date(preview.expires_latest).toLocaleString()}`
                : ''}
            </p>
          )}
          {preview && (
            <div className="grid grid-cols-3 gap-3 text-sm">
              {TYPES.map(type => (
                <div key={type} className="rounded border p-3">
                  {LABELS[type]}：{preview.by_type[type]?.count || 0} 个 /{' '}
                  {formatBytes(preview.by_type[type]?.bytes || 0)}
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={loading} onClick={() => void clean(true)}>
              清理已到期资源
            </Button>
            <Button variant="destructive" disabled={loading} onClick={() => void clean(false)}>
              强制清理全部受管资源
            </Button>
          </div>
          <div className="space-y-2">
            <h3 className="font-medium">最近清理结果</h3>
            {runs.length ? (
              runs.map((run, index) => (
                <p key={`${run.completed_at}-${index}`} className="text-muted-foreground text-sm">
                  {new Date(run.completed_at).toLocaleString()}：请求 {run.requested} 个，删除{' '}
                  {run.deleted} 个，缺失 {run.missing} 个，失败 {run.failed} 个，释放{' '}
                  {formatBytes(run.bytes_freed)}（
                  {run.resource_types.map(type => LABELS[type] || type).join('、')}）
                </p>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">暂无清理记录</p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
