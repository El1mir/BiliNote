import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'
import { AlertTriangle, HardDrive, Info, Layers, Loader2, Save, Settings2 } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { fetchEnableModels, getProviderList } from '@/services/model'
import { activateGlobalModel } from '@/services/general'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  getGeneralSettings,
  updateGeneralSettings,
  type GeneralSettings,
  type GeneralSettingsPatch,
} from '@/services/general'

/** 表单里数字字段以字符串保存，避免受控输入在清空时跳回默认值 */
type FormState = {
  max_parallel_notes: string
  cache_limit_gb: string
  min_free_disk_gb: string
  circuit_breaker_threshold: string
}

const EMPTY_FORM: FormState = {
  max_parallel_notes: '',
  cache_limit_gb: '',
  min_free_disk_gb: '',
  circuit_breaker_threshold: '',
}

const BYTES_PER_GB = 1024 ** 3

/**
 * 字节 → GB 输入框文本。
 * 后端用字节存，界面上按 GB 编辑；`0`（不限 / 不检查 / 关闭）原样显示成 `0`，
 * 不要渲染成 `0.00` 这种看着像「几乎为零」的样子。保留两位小数是为了让
 * 1.5 GB 这类值能往返而不被截断。
 */
const bytesToGbInput = (bytes: number | null | undefined): string => {
  if (bytes === undefined || bytes === null) return ''
  return String(Math.round((bytes / BYTES_PER_GB) * 100) / 100)
}

/** GB 输入 → 字节。取整是必须的：后端字段是 int，浮点字节会被 pydantic 拒掉。 */
const gbInputToBytes = (gb: number): number => Math.round(gb * BYTES_PER_GB)

const formFromSettings = (settings: GeneralSettings): FormState => ({
  max_parallel_notes:
    settings.max_parallel_notes === undefined || settings.max_parallel_notes === null
      ? ''
      : String(settings.max_parallel_notes),
  cache_limit_gb: bytesToGbInput(settings.cache_limit_bytes),
  min_free_disk_gb: bytesToGbInput(settings.min_free_disk_bytes),
  circuit_breaker_threshold:
    settings.circuit_breaker_threshold === undefined || settings.circuit_breaker_threshold === null
      ? ''
      : String(settings.circuit_breaker_threshold),
})

/** 非负数字解析：空串 / 非数字 / 负数一律返回 null，交给各字段自己判错误。 */
const parseNonNegative = (text: string): number | null => {
  const trimmed = text.trim()
  if (trimmed === '') return null
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value < 0) return null
  return value
}

const parsePositiveInt = (text: string): number | null => {
  const value = parseNonNegative(text)
  if (value === null || !Number.isInteger(value) || value < 1) return null
  return value
}

export default function GeneralSettingPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  /** 后端下发的完整设置：既是「原始值」基准（判断哪些字段被改过），也提供各字段上限。 */
  const [settings, setSettings] = useState<GeneralSettings | null>(null)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [models, setModels] = useState<
    { id: string | number; provider_id: string | number; model_name: string }[]
  >([])
  const [providers, setProviders] = useState<{ id: string | number; name: string }[]>([])
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [activating, setActivating] = useState(false)

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const data = await getGeneralSettings()
      setSettings(data)
      setForm(formFromSettings(data))
      setSelectedProvider(data.active_provider_id || '')
      setSelectedModel(data.active_model_name || '')
      const [modelData, providerData] = await Promise.all([fetchEnableModels(), getProviderList()])
      setModels(
        modelData.map(item => ({
          ...item,
          id: String(item.id),
          provider_id: String(item.provider_id),
        }))
      )
      setProviders(providerData.map(item => ({ ...item, id: String(item.id) })))
    } catch (error) {
      const message = (error as { msg?: string })?.msg || '读取通用设置失败'
      setLoadError(message)
      throw error
    }
  }, [])

  useEffect(() => {
    load()
      .catch(() => {
        /* 错误已写进 loadError，页面会展示 */
      })
      .finally(() => setLoading(false))
  }, [load])

  const limits = useMemo(
    () => ({
      parallel: settings?.max_parallel_notes_limit ?? null,
      cacheGb:
        settings?.cache_limit_bytes_limit === undefined ||
        settings?.cache_limit_bytes_limit === null
          ? null
          : settings.cache_limit_bytes_limit / BYTES_PER_GB,
      diskGb:
        settings?.min_free_disk_bytes_limit === undefined ||
        settings?.min_free_disk_bytes_limit === null
          ? null
          : settings.min_free_disk_bytes_limit / BYTES_PER_GB,
      breaker: settings?.circuit_breaker_threshold_limit ?? null,
    }),
    [settings]
  )

  const defaults = useMemo(
    () => ({
      cacheGb: bytesToGbInput(settings?.cache_limit_bytes_default),
      diskGb: bytesToGbInput(settings?.min_free_disk_bytes_default),
      breaker:
        settings?.circuit_breaker_threshold_default === undefined ||
        settings?.circuit_breaker_threshold_default === null
          ? ''
          : String(settings.circuit_breaker_threshold_default),
    }),
    [settings]
  )

  // ---------------- 校验 ----------------
  const parallelValue = parsePositiveInt(form.max_parallel_notes)
  const parallelError =
    parallelValue === null
      ? `请输入 1${limits.parallel === null ? '' : ` - ${limits.parallel}`} 之间的整数`
      : limits.parallel !== null && parallelValue > limits.parallel
        ? `不能超过上限 ${limits.parallel}`
        : ''

  const cacheGbValue = parseNonNegative(form.cache_limit_gb)
  const cacheError =
    cacheGbValue === null
      ? '请输入不小于 0 的数字（0 = 不限）'
      : limits.cacheGb !== null && cacheGbValue > limits.cacheGb
        ? `不能超过上限 ${Math.round(limits.cacheGb)} GB`
        : ''

  const diskGbValue = parseNonNegative(form.min_free_disk_gb)
  const diskError =
    diskGbValue === null
      ? '请输入不小于 0 的数字（0 = 不检查）'
      : limits.diskGb !== null && diskGbValue > limits.diskGb
        ? `不能超过上限 ${Math.round(limits.diskGb)} GB`
        : ''

  const breakerValue = parseNonNegative(form.circuit_breaker_threshold)
  const breakerError =
    breakerValue === null || !Number.isInteger(breakerValue)
      ? '请输入不小于 0 的整数（0 = 关闭）'
      : limits.breaker !== null && breakerValue > limits.breaker
        ? `不能超过上限 ${limits.breaker}`
        : ''

  // ---------------- 只提交改动过的字段 ----------------
  // 后端把「未传」解释为「保持原值」，所以必须精确算出脏字段：
  // 若把没改的字段也一起发出去，用户只调一项就会把另外几项按当前表单值重写。
  const parallelDirty =
    settings !== null && parallelValue !== null && parallelValue !== settings.max_parallel_notes
  const cacheDirty =
    settings !== null &&
    cacheGbValue !== null &&
    gbInputToBytes(cacheGbValue) !== settings.cache_limit_bytes
  const diskDirty =
    settings !== null &&
    diskGbValue !== null &&
    gbInputToBytes(diskGbValue) !== settings.min_free_disk_bytes
  const breakerDirty =
    settings !== null &&
    breakerValue !== null &&
    breakerValue !== settings.circuit_breaker_threshold

  const dirtyCount = [parallelDirty, cacheDirty, diskDirty, breakerDirty].filter(Boolean).length

  const canSave =
    !saving &&
    dirtyCount > 0 &&
    // 只有「改过且非法」的字段才拦保存：用户没碰的字段即使表单里显示异常也不该阻塞。
    (!parallelDirty || parallelError === '') &&
    (!cacheDirty || cacheError === '') &&
    (!diskDirty || diskError === '') &&
    (!breakerDirty || breakerError === '')

  const providerOptions = useMemo(
    () => providers.map(provider => ({ id: String(provider.id), name: provider.name })),
    [providers]
  )
  const modelsForProvider = useMemo(
    () => models.filter(model => model.provider_id === selectedProvider),
    [models, selectedProvider]
  )

  const handleActivateModel = async () => {
    if (!selectedProvider || !selectedModel) {
      toast.error('请选择提供商和模型')
      return
    }
    setActivating(true)
    try {
      await activateGlobalModel(selectedProvider, selectedModel)
      await load()
      toast.success('全局模型已切换，排队和后续任务立即生效')
    } catch (error) {
      toast.error((error as { msg?: string })?.msg || '切换模型失败')
    } finally {
      setActivating(false)
    }
  }

  const handleSave = async () => {
    if (dirtyCount === 0) {
      toast('没有需要保存的改动')
      return
    }
    if (!canSave) {
      toast.error(parallelError || cacheError || diskError || breakerError || '请检查输入')
      return
    }

    const patch: GeneralSettingsPatch = {}
    const changed: string[] = []
    if (parallelDirty && parallelValue !== null) {
      patch.max_parallel_notes = parallelValue
      changed.push(`同时最多生成 ${parallelValue} 个笔记`)
    }
    if (cacheDirty && cacheGbValue !== null) {
      patch.cache_limit_bytes = gbInputToBytes(cacheGbValue)
      changed.push(cacheGbValue === 0 ? '缓存上限不限' : `缓存上限 ${cacheGbValue} GB`)
    }
    if (diskDirty && diskGbValue !== null) {
      patch.min_free_disk_bytes = gbInputToBytes(diskGbValue)
      changed.push(diskGbValue === 0 ? '不检查磁盘剩余' : `磁盘剩余门禁 ${diskGbValue} GB`)
    }
    if (breakerDirty && breakerValue !== null) {
      patch.circuit_breaker_threshold = breakerValue
      changed.push(breakerValue === 0 ? '关闭连续失败熔断' : `连续失败熔断 ${breakerValue} 次`)
    }

    setSaving(true)
    try {
      // 只发改动过的字段：未传字段由后端保持原值（0 是合法取值，不会被当成「没传」）。
      const updated = await updateGeneralSettings(patch)
      setSettings(updated)
      setForm(formFromSettings(updated))
      toast.success(`已保存：${changed.join('，')}`)
    } catch (error) {
      toast.error((error as { msg?: string })?.msg || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-neutral-400" />
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="h-full overflow-y-auto bg-white p-6">
        <div className="mx-auto max-w-3xl space-y-4">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>无法读取通用设置</AlertTitle>
            <AlertDescription>{loadError}</AlertDescription>
          </Alert>
          <Button
            variant="outline"
            onClick={() => {
              setLoading(true)
              load()
                .catch(() => undefined)
                .finally(() => setLoading(false))
            }}
          >
            重试
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full space-y-6 overflow-y-auto bg-white p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-semibold">
            <Settings2 className="h-6 w-6" />
            通用设置
          </h2>
          <p className="mt-1 text-sm text-neutral-500">
            全局生效的基础配置，与具体模型、转写器无关。
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>全局 LLM 提供商和模型</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-neutral-500">
              切换后立即影响新任务、排队任务、失败重试、服务重启恢复及 429
              等待中的任务。任务记录不会保存提供商和模型标识。
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                value={selectedProvider}
                onValueChange={value => {
                  setSelectedProvider(value)
                  setSelectedModel('')
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择提供商" />
                </SelectTrigger>
                <SelectContent>
                  {providerOptions.map(provider => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {provider.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={selectedModel} onValueChange={setSelectedModel}>
                <SelectTrigger>
                  <SelectValue placeholder="选择模型" />
                </SelectTrigger>
                <SelectContent>
                  {modelsForProvider.map(model => (
                    <SelectItem key={model.id} value={model.model_name}>
                      {model.model_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleActivateModel}
              disabled={activating || !selectedProvider || !selectedModel}
            >
              {activating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              激活全局模型
            </Button>
          </CardContent>
        </Card>

        {/* ---------------- 并发 ---------------- */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Layers className="h-5 w-5" />
              笔记生成并发
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">最大并行生成数量</label>
              <Input
                type="number"
                min="1"
                max={limits.parallel === null ? undefined : String(limits.parallel)}
                step="1"
                value={form.max_parallel_notes}
                onChange={event =>
                  setForm(current => ({ ...current, max_parallel_notes: event.target.value }))
                }
                placeholder="1"
              />
              <p className="text-xs text-neutral-500">
                限制同一时间最多有几个笔记任务在生成（下载、转写、调用大模型）。数值越大越快，但会同时占用更多
                CPU / 内存与上游接口配额。允许范围：1
                {limits.parallel === null ? '' : ` - ${limits.parallel}`}
                。保存后立即生效，无需重启服务。
              </p>
              {parallelError && <p className="text-xs text-red-500">{parallelError}</p>}
            </div>

            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle>改动会立刻应用到新任务</AlertTitle>
              <AlertDescription className="text-sm">
                超出并发的任务会排队等待，不会失败；已经在生成的笔记不受影响。调小该值不会中断正在进行的任务。
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>

        {/* ---------------- 缓存边界（spec 009 / ticket 07） ---------------- */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <HardDrive className="h-5 w-5" />
              缓存边界
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-neutral-500">
              本地媒体资源（已完成任务的音视频、截图等）按<strong>容量</strong>自动回收，
              不必等到保留天数过期。长批量任务最容易挤爆磁盘，这里是最后一道闸门。
            </p>

            <div className="space-y-2">
              <label className="text-sm font-medium">缓存总量上限（GB）</label>
              <Input
                type="number"
                min="0"
                max={limits.cacheGb === null ? undefined : String(Math.round(limits.cacheGb))}
                step="0.5"
                value={form.cache_limit_gb}
                onChange={event =>
                  setForm(current => ({ ...current, cache_limit_gb: event.target.value }))
                }
                placeholder={defaults.cacheGb || '10'}
              />
              <p className="text-xs text-neutral-500">
                本地缓存总字节超过该值时，按最旧优先删除已完成任务的资源，直到降到阈值以下。
                <strong>填 0 表示不限</strong>（仍会按保留天数清理）。默认
                {defaults.cacheGb ? ` ${defaults.cacheGb} GB` : ' 10 GB'}。修改只影响之后的清理，
                不会重算已有资源的过期时间。
              </p>
              {cacheError && <p className="text-xs text-red-500">{cacheError}</p>}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">磁盘剩余空间门禁（GB）</label>
              <Input
                type="number"
                min="0"
                max={limits.diskGb === null ? undefined : String(Math.round(limits.diskGb))}
                step="0.5"
                value={form.min_free_disk_gb}
                onChange={event =>
                  setForm(current => ({ ...current, min_free_disk_gb: event.target.value }))
                }
                placeholder={defaults.diskGb || '5'}
              />
              <p className="text-xs text-neutral-500">
                磁盘剩余空间低于该值时不再启动新的生成任务，避免把磁盘写满导致转写或下载直接失败。
                <strong>填 0 表示不检查</strong>。默认
                {defaults.diskGb ? ` ${defaults.diskGb} GB` : ' 5 GB'}。
              </p>
              {diskError && <p className="text-xs text-red-500">{diskError}</p>}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">连续失败熔断阈值（次）</label>
              <Input
                type="number"
                min="0"
                max={limits.breaker === null ? undefined : String(limits.breaker)}
                step="1"
                value={form.circuit_breaker_threshold}
                onChange={event =>
                  setForm(current => ({
                    ...current,
                    circuit_breaker_threshold: event.target.value,
                  }))
                }
                placeholder={defaults.breaker || '5'}
              />
              <p className="text-xs text-neutral-500">
                连续这么多个任务失败后暂停派发新任务，避免上游供应商挂掉时整批任务挨个失败刷屏。
                <strong>填 0 表示关闭熔断</strong>。默认
                {defaults.breaker ? ` ${defaults.breaker} 次` : ' 5 次'}。
              </p>
              {breakerError && <p className="text-xs text-red-500">{breakerError}</p>}
            </div>

            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle>与「媒体资源」页的分工</AlertTitle>
              <AlertDescription className="text-sm">
                「媒体资源」管的是<strong>时间</strong>（保留天数 + 手动清理），这里管的是
                <strong>容量</strong>（总量上限 + 磁盘门禁）。两者都会清理已完成的资源，互不冲突；
                正在生成或重试中的任务资源不会被删除。
              </AlertDescription>
            </Alert>
            {/* 当前缓存占用暂不展示：后端还没有对应的统计接口，不编造。 */}
          </CardContent>
        </Card>

        {/* ---------------- 操作 ---------------- */}
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!canSave} onClick={() => void handleSave()}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存
          </Button>
          <span className="text-xs text-neutral-500">
            {dirtyCount === 0
              ? '还没有改动'
              : canSave
                ? `将保存 ${dirtyCount} 项改动（未改动的字段保持原值）`
                : '请先修正上面标红的字段'}
          </span>
        </div>
      </div>
    </div>
  )
}
