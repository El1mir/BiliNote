import { useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { AudioLines, AlertTriangle, CheckCircle2, Download, Loader2, Save, XCircle, Plus, Trash2, Boxes, Pencil } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Label } from '@/components/ui/label'
import {
  getTranscriberConfig,
  updateTranscriberConfig,
  getModelsStatus,
  downloadModel,
  addWhisperModel,
  deleteWhisperModel,
  addOpenaiAsr,
  updateOpenaiAsr,
  deleteOpenaiAsr,
  testOpenaiAsr,
  TranscriberConfig,
  ModelStatus,
  OpenAIASREndpoint,
  OpenAIASRStyle,
} from '@/services/transcriber'

const isWhisperType = (type: string) =>
  type === 'fast-whisper' || type === 'mlx-whisper'

interface AsrFormState {
  id: string
  name: string
  base_url: string
  api_key: string
  model: string
  timeout: string
  chunk_size_mb: string
  api_style: OpenAIASRStyle
  max_speech_chunks: string
  silence_noise_db: string
  min_silence_seconds: string
  max_rpm: string
  chunk_concurrency: string
}

const emptyAsrForm: AsrFormState = {
  id: '',
  name: '',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'whisper-1',
  timeout: '600',
  chunk_size_mb: '18',
  api_style: 'transcriptions',
  max_speech_chunks: '120',
  silence_noise_db: '-30',
  min_silence_seconds: '0.5',
  max_rpm: '30',
  chunk_concurrency: '4',
}

/** 表单字段：上方 label + 下方输入框（+ 可选说明），避免只靠 placeholder 看不出含义。 */
const Field = ({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) => (
  <div className="space-y-1.5">
    <Label className="text-xs text-neutral-600">{label}</Label>
    {children}
    {hint && <p className="text-xs text-neutral-400">{hint}</p>}
  </div>
)

export default function Transcriber() {
  const [config, setConfig] = useState<TranscriberConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [selectedType, setSelectedType] = useState('')
  const [selectedModelSize, setSelectedModelSize] = useState('')
  const [modelStatuses, setModelStatuses] = useState<ModelStatus[]>([])
  const [mlxModelStatuses, setMlxModelStatuses] = useState<ModelStatus[]>([])
  const [mlxAvailable, setMlxAvailable] = useState(false)
  // OpenAI 兼容 ASR（spec 003）
  const [asrActiveId, setAsrActiveId] = useState('')
  const [asrForm, setAsrForm] = useState<AsrFormState>(emptyAsrForm)
  const [asrSaving, setAsrSaving] = useState(false)
  const [asrTestingId, setAsrTestingId] = useState('')
  // 自定义模型表单
  const [newModelName, setNewModelName] = useState('')
  const [newModelTarget, setNewModelTarget] = useState('')
  const [addingModel, setAddingModel] = useState(false)
  // 已提示过的下载失败 key（whisper 用 model_size，mlx 用 mlx-{size}）。
  // null 表示尚未首次加载——首次加载只建立基线、不对历史失败弹窗。
  const prevFailedRef = useRef<Set<string> | null>(null)

  // 重新拉取配置（不重置用户当前的选择），用于增删自定义模型后刷新下拉与列表
  const reloadConfig = useCallback(async () => {
    try {
      const data = await getTranscriberConfig()
      setConfig(data)
      setAsrActiveId(data.openai_asr_id || '')
    } catch {
      // 静默
    }
  }, [])

  const fetchModelsStatus = useCallback(async () => {
    try {
      const data = await getModelsStatus()
      setModelStatuses(data.whisper)
      setMlxModelStatuses(data.mlx_whisper)
      setMlxAvailable(data.mlx_available)

      // 下载失败主动提示：只对「本次新出现的失败」弹一次，避免轮询期间反复弹窗
      const failedNow = new Map<string, ModelStatus>()
      data.whisper.forEach(m => m.failed && failedNow.set(m.model_size, m))
      data.mlx_whisper.forEach(m => m.failed && failedNow.set(`mlx-${m.model_size}`, m))
      if (prevFailedRef.current === null) {
        // 首次加载：建立基线，不对进入页面前就已失败的项弹窗（仍会在列表里红字展示）
        prevFailedRef.current = new Set(failedNow.keys())
      } else {
        failedNow.forEach((m, key) => {
          if (!prevFailedRef.current!.has(key)) {
            const detail = m.error ? `：${m.error.slice(0, 120)}` : ''
            toast.error(`模型 ${m.model_size} 下载失败${detail}`, { duration: 6000 })
          }
        })
        prevFailedRef.current = new Set(failedNow.keys())
      }
    } catch {
      // 静默失败，不阻塞主流程
    }
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getTranscriberConfig()
        setConfig(data)
        setSelectedType(data.transcriber_type)
        setSelectedModelSize(data.whisper_model_size)
        setAsrActiveId(data.openai_asr_id || '')
      } catch {
        toast.error('获取转写器配置失败')
      } finally {
        setLoading(false)
      }
    }
    load()
    fetchModelsStatus()
  }, [fetchModelsStatus])

  // 有下载中的模型时自动轮询状态
  useEffect(() => {
    const hasDownloading =
      modelStatuses.some(m => m.downloading) || mlxModelStatuses.some(m => m.downloading)
    if (!hasDownloading) return

    const timer = setInterval(fetchModelsStatus, 3000)
    return () => clearInterval(timer)
  }, [modelStatuses, mlxModelStatuses, fetchModelsStatus])

  const handleSave = async () => {
    // 切到本地 whisper 引擎且选了未下载的模型时，提前 confirm，避免用户保存后到首次任务才发现要下 GB 级模型
    if (isWhisperType(selectedType)) {
      const pool = selectedType === 'mlx-whisper' ? mlxModelStatuses : modelStatuses
      const target = pool.find(m => m.model_size === selectedModelSize)
      if (target && !target.downloaded && !target.downloading) {
        const sizeHint: Record<string, string> = {
          'tiny': '~75MB',
          'base': '~150MB',
          'small': '~500MB',
          'medium': '~1.5GB',
          'large-v3': '~3GB',
          'large-v3-turbo': '~1.6GB',
        }
        const ok = window.confirm(
          `选择 ${selectedType} / ${selectedModelSize} 后，首次转写时会下载该模型（${sizeHint[selectedModelSize] || '体积未知'}）。\n` +
          `网络较差时容易中断；推荐改用 Groq / 必剪 / 快手 等在线引擎。\n\n` +
          '继续保存吗？',
        )
        if (!ok) return
      }
    }

    if (selectedType === 'openai-asr' && !asrActiveId) {
      toast.error('请先添加并选择一条要使用的 OpenAI 兼容 ASR 端点')
      return
    }

    setSaving(true)
    try {
      const payload: {
        transcriber_type: string
        whisper_model_size?: string
        openai_asr_id?: string
      } = {
        transcriber_type: selectedType,
      }
      if (isWhisperType(selectedType)) {
        payload.whisper_model_size = selectedModelSize
      }
      if (selectedType === 'openai-asr') {
        payload.openai_asr_id = asrActiveId
      }
      await updateTranscriberConfig(payload)
      toast.success('转写器配置已保存')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDownload = async (modelSize: string, transcriberType: string) => {
    try {
      await downloadModel({ model_size: modelSize, transcriber_type: transcriberType })
      toast.success(`模型 ${modelSize} 开始下载`)
      // 立即刷新状态
      setTimeout(fetchModelsStatus, 1000)
    } catch {
      toast.error('下载请求失败')
    }
  }

  const handleAddCustomModel = async () => {
    const name = newModelName.trim()
    const target = newModelTarget.trim()
    if (!name || !target) {
      toast.error('请填写模型名称和 HF repo_id / 本地路径')
      return
    }
    setAddingModel(true)
    try {
      await addWhisperModel({ name, target })
      toast.success(`已添加自定义模型 ${name}`)
      setNewModelName('')
      setNewModelTarget('')
      await reloadConfig()
      await fetchModelsStatus()
    } catch {
      // 后端的具体错误（如重名）已由请求拦截器 toast，这里不重复提示
    } finally {
      setAddingModel(false)
    }
  }

  const handleDeleteCustomModel = async (name: string) => {
    try {
      await deleteWhisperModel(name)
      toast.success(`已删除自定义模型 ${name}`)
      // 删的正好是当前选中的，回退到 tiny，避免选中一个不存在的名称
      if (selectedModelSize === name) setSelectedModelSize('tiny')
      await reloadConfig()
      await fetchModelsStatus()
    } catch {
      // 拦截器已提示
    }
  }

  // ---------------- OpenAI 兼容 ASR 端点管理（spec 003） ----------------

  const resetAsrForm = () => setAsrForm(emptyAsrForm)

  const handleEditAsr = (endpoint: OpenAIASREndpoint) => {
    setAsrForm({
      id: endpoint.id,
      name: endpoint.name,
      base_url: endpoint.base_url,
      api_key: endpoint.api_key,
      model: endpoint.model,
      timeout: String(endpoint.timeout ?? 600),
      chunk_size_mb: String(endpoint.chunk_size_mb ?? 18),
      api_style: endpoint.api_style || 'transcriptions',
      max_speech_chunks: String(endpoint.max_speech_chunks ?? 120),
      silence_noise_db: String(endpoint.silence_noise_db ?? -30),
      min_silence_seconds: String(endpoint.min_silence_seconds ?? 0.5),
      max_rpm: String(endpoint.max_rpm ?? 30),
      chunk_concurrency: String(endpoint.chunk_concurrency ?? 4),
    })
  }

  const handleSaveAsr = async () => {
    const name = asrForm.name.trim()
    const baseUrl = asrForm.base_url.trim()
    const model = asrForm.model.trim()
    const apiKey = asrForm.api_key.trim()
    if (!name || !baseUrl || !model) {
      toast.error('名称 / 服务地址 / 模型名不能为空')
      return
    }
    // 新增必须填 key；编辑时回显的是打码值，带 * 后端会跳过不覆盖
    if (!asrForm.id && !apiKey) {
      toast.error('请填写 API Key')
      return
    }

    setAsrSaving(true)
    try {
      const payload = {
        name,
        base_url: baseUrl,
        api_key: apiKey,
        model,
        timeout: Number(asrForm.timeout) || 600,
        chunk_size_mb: Number(asrForm.chunk_size_mb) || 18,
        api_style: asrForm.api_style,
        max_speech_chunks: Number(asrForm.max_speech_chunks) || 120,
        silence_noise_db: Number(asrForm.silence_noise_db) || -30,
        min_silence_seconds: Number(asrForm.min_silence_seconds) || 0.5,
        max_rpm: Number(asrForm.max_rpm) || 30,
        chunk_concurrency: Number(asrForm.chunk_concurrency) || 4,
      }
      if (asrForm.id) {
        await updateOpenaiAsr(asrForm.id, payload)
        toast.success('已保存')
        resetAsrForm()
        await reloadConfig()
      } else {
        const { id } = await addOpenaiAsr(payload)
        toast.success('已添加')
        resetAsrForm()
        await reloadConfig()
        // 新添加的先在界面上选中，点「保存配置」后才真正生效
        setAsrActiveId(id)
      }
    } catch {
      // 具体错误已由请求拦截器 toast
    } finally {
      setAsrSaving(false)
    }
  }

  const handleDeleteAsr = async (endpoint: OpenAIASREndpoint) => {
    if (!window.confirm(`删除端点「${endpoint.name}」？`)) return
    const wasActive = asrActiveId === endpoint.id
    try {
      await deleteOpenaiAsr(endpoint.id)
      toast.success('已删除')
      if (asrForm.id === endpoint.id) resetAsrForm()
      await reloadConfig()
      if (wasActive) setAsrActiveId('')
    } catch {
      // 拦截器已提示
    }
  }

  const handleTestAsr = async (endpoint: OpenAIASREndpoint) => {
    setAsrTestingId(endpoint.id)
    try {
      const res: any = await testOpenaiAsr(endpoint.id)
      toast.success(res?.message || '连接成功')
    } catch (e: any) {
      toast.error(e?.msg || '连接失败')
    } finally {
      setAsrTestingId('')
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-neutral-400" />
      </div>
    )
  }

  if (!config) {
    return <div className="p-6 text-center text-neutral-500">无法加载配置</div>
  }

  const currentModels = selectedType === 'mlx-whisper' ? mlxModelStatuses : modelStatuses
  const asrEndpoints = config.openai_asr_endpoints || []

  return (
    // SettingLayout 的 <main> 是 overflow-hidden，页面自己必须有滚动容器，
    // 否则「OpenAI 兼容 ASR」端点列表一多，底部内容就够不到、也无法滚动。
    <div className="h-full space-y-6 overflow-y-auto bg-white p-6">
      <div>
        <h2 className="text-2xl font-semibold">音频转写配置</h2>
        <p className="mt-1 text-sm text-neutral-500">
          选择视频音频转写为文字所使用的引擎，保存后对新任务立即生效
        </p>
      </div>

      {/* 转写引擎选择 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <AudioLines className="h-5 w-5" />
            转写引擎
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">转写器类型</label>
            <Select value={selectedType} onValueChange={setSelectedType}>
              <SelectTrigger className="w-full max-w-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {config.available_types.map(t => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isWhisperType(selectedType) && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Whisper 模型大小</label>
              <Select value={selectedModelSize} onValueChange={setSelectedModelSize}>
                <SelectTrigger className="w-full max-w-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {config.whisper_model_sizes.map(size => {
                    const status = currentModels.find(m => m.model_size === size)
                    return (
                      <SelectItem key={size} value={size}>
                        <span className="flex items-center gap-2">
                          {size}
                          {status?.downloaded && (
                            <CheckCircle2 className="h-3 w-3 text-green-500" />
                          )}
                        </span>
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
              <p className="text-xs text-neutral-400">
                模型越大精度越高，但速度更慢、占用更多显存
              </p>
            </div>
          )}

          {selectedType === 'mlx-whisper' && !config.mlx_whisper_available && (
            <Alert variant="warning" className="text-sm">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                MLX Whisper 当前不可用。需要 macOS 平台并安装{' '}
                <code className="rounded bg-neutral-100 px-1">pip install mlx_whisper</code>，
                安装后重启后端生效。
              </AlertDescription>
            </Alert>
          )}

          <Button onClick={handleSave} disabled={saving || (selectedType === 'mlx-whisper' && !config.mlx_whisper_available)} className="mt-2">
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存配置
          </Button>
        </CardContent>
      </Card>

      {/* Whisper 模型管理 */}
      {isWhisperType(selectedType) && currentModels.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Download className="h-5 w-5" />
              模型管理
              <span className="text-sm font-normal text-neutral-400">
                {selectedType === 'mlx-whisper' ? 'MLX Whisper' : 'Faster Whisper'}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {currentModels.map(model => (
                <div
                  key={model.model_size}
                  className="rounded-md border px-4 py-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-medium">{model.model_size}</span>
                      {model.downloaded ? (
                        <Badge variant="default" className="bg-green-500 hover:bg-green-600">
                          已下载
                        </Badge>
                      ) : model.downloading ? (
                        <Badge variant="secondary" className="flex items-center gap-1">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          下载中
                        </Badge>
                      ) : model.failed ? (
                        <Badge variant="destructive" className="flex items-center gap-1" title={model.error}>
                          <XCircle className="h-3 w-3" />
                          下载失败
                        </Badge>
                      ) : (
                        <Badge variant="outline">未下载</Badge>
                      )}
                    </div>
                    {!model.downloaded && !model.downloading && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDownload(model.model_size, selectedType)}
                      >
                        <Download className="mr-1 h-4 w-4" />
                        {model.failed ? '重试' : '下载'}
                      </Button>
                    )}
                  </div>
                  {model.failed && model.error && (
                    <p className="mt-2 break-all text-xs text-red-500" title={model.error}>
                      {model.error}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* OpenAI 兼容 ASR 端点管理（spec 003） */}
      {selectedType === 'openai-asr' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <AudioLines className="h-5 w-5" />
              OpenAI 兼容 ASR
              <span className="text-sm font-normal text-neutral-400">
                任意实现 /v1/audio/transcriptions 的服务
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert className="text-sm">
              <AlertDescription>
                <div>
                  填 <strong>Base URL</strong>（到 <code className="rounded bg-neutral-100 px-1">/v1</code>{' '}
                  为止）+ API Key + <strong>模型名</strong>；点「测试」会真发一段静音校验，
                  「使用」并保存后对新任务生效。
                </div>
                <ul className="mt-2 list-disc space-y-1 pl-4">
                  <li>
                    <strong>audio/transcriptions（Whisper 风格）</strong>：如 OpenAI 官方{' '}
                    <code className="rounded bg-neutral-100 px-1">https://api.openai.com/v1</code> +{' '}
                    <code className="rounded bg-neutral-100 px-1">whisper-1</code>，硅基流动{' '}
                    <code className="rounded bg-neutral-100 px-1">FunAudioLLM/SenseVoiceSmall</code>
                  </li>
                  <li>
                    <strong>chat/completions + input_audio</strong>：如小米 MiMo，Base URL{' '}
                    <code className="rounded bg-neutral-100 px-1">https://api.xiaomimimo.com/v1</code>{' '}
                    + 模型 <code className="rounded bg-neutral-100 px-1">mimo-v2.5-asr</code>
                    （音频经 base64 传入；这种接口不返回时间轴，会<b>按说话（静音边界）自动切片</b>，
                    每片单独转写并用真实语音边界当时间轴，可用「静音切片」三项参数微调）
                  </li>
                </ul>
              </AlertDescription>
            </Alert>

            {asrEndpoints.length === 0 ? (
              <p className="text-sm text-neutral-400">还没有端点，先在下方添加一条</p>
            ) : (
              <div className="space-y-2">
                {asrEndpoints.map(endpoint => {
                  const active = asrActiveId === endpoint.id
                  return (
                    <div
                      key={endpoint.id}
                      className={`rounded-md border px-4 py-3 ${active ? 'border-primary' : ''}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 font-medium">
                            {endpoint.name}
                            {active && (
                              <Badge variant="default" className="bg-green-500 hover:bg-green-600">
                                使用中
                              </Badge>
                            )}
                          </div>
                          <div className="truncate text-xs text-neutral-400" title={endpoint.base_url}>
                            {endpoint.base_url}
                          </div>
                          <div className="truncate text-xs text-neutral-400">
                            模型：{endpoint.model} · 超时 {endpoint.timeout}s · 切割阈值{' '}
                            {endpoint.chunk_size_mb}MB
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          {!active && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setAsrActiveId(endpoint.id)}
                            >
                              使用
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={asrTestingId === endpoint.id}
                            onClick={() => handleTestAsr(endpoint)}
                          >
                            {asrTestingId === endpoint.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              '测试'
                            )}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => handleEditAsr(endpoint)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-500 hover:text-red-600"
                            onClick={() => handleDeleteAsr(endpoint)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            <div className="space-y-2 rounded-md border p-4">
              <div className="text-sm font-medium">
                {asrForm.id ? '编辑端点' : '添加端点'}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="接口类型">
                  <Select
                    value={asrForm.api_style}
                    onValueChange={v => setAsrForm({ ...asrForm, api_style: v as OpenAIASRStyle })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="transcriptions">
                        audio/transcriptions（Whisper 风格）
                      </SelectItem>
                      <SelectItem value="chat">
                        chat/completions + input_audio（MiMo 等）
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </Field>

                <Field label="名称">
                  <Input
                    placeholder="如 硅基流动"
                    value={asrForm.name}
                    onChange={e => setAsrForm({ ...asrForm, name: e.target.value })}
                  />
                </Field>

                <Field label="服务地址（Base URL）" hint="填到 /v1 为止">
                  <Input
                    placeholder="https://api.openai.com/v1"
                    value={asrForm.base_url}
                    onChange={e => setAsrForm({ ...asrForm, base_url: e.target.value })}
                  />
                </Field>

                <Field label="API Key" hint="编辑时留空或保持打码值即不修改">
                  <Input
                    placeholder="sk-..."
                    value={asrForm.api_key}
                    onChange={e => setAsrForm({ ...asrForm, api_key: e.target.value })}
                  />
                </Field>

                <Field label="模型名">
                  <Input
                    placeholder="whisper-1 / mimo-v2.5-asr"
                    value={asrForm.model}
                    onChange={e => setAsrForm({ ...asrForm, model: e.target.value })}
                  />
                </Field>

                <Field label="超时（秒）" hint="默认 600">
                  <Input
                    type="number"
                    placeholder="600"
                    value={asrForm.timeout}
                    onChange={e => setAsrForm({ ...asrForm, timeout: e.target.value })}
                  />
                </Field>

                <Field label="切割阈值（MB）" hint="超过就切成多段分别转写，默认 18">
                  <Input
                    type="number"
                    placeholder="18"
                    value={asrForm.chunk_size_mb}
                    onChange={e => setAsrForm({ ...asrForm, chunk_size_mb: e.target.value })}
                  />
                </Field>

                <Field
                  label="每分钟请求上限"
                  hint="防止服务端 429，默认 30 次/分钟"
                >
                  <Input
                    type="number"
                    placeholder="30"
                    value={asrForm.max_rpm}
                    onChange={e => setAsrForm({ ...asrForm, max_rpm: e.target.value })}
                  />
                </Field>

                <Field
                  label="并发请求数"
                  hint="切片转写同时发起的请求数（1-32，默认 4）；设 1 即串行，只在「每分钟请求上限」允许的范围内并发"
                >
                  <Input
                    type="number"
                    min={1}
                    max={32}
                    placeholder="4"
                    value={asrForm.chunk_concurrency}
                    onChange={e =>
                      setAsrForm({ ...asrForm, chunk_concurrency: e.target.value })
                    }
                  />
                </Field>

                {asrForm.api_style === 'chat' && (
                  <>
                    <Field
                      label="最多切片数"
                      hint="按说话切片时最多切多少段，默认 120"
                    >
                      <Input
                        type="number"
                        placeholder="120"
                        value={asrForm.max_speech_chunks}
                        onChange={e =>
                          setAsrForm({ ...asrForm, max_speech_chunks: e.target.value })
                        }
                      />
                    </Field>

                    <Field
                      label="静音门限（dB）"
                      hint="越低越不敏感；环境吵可调到 -25"
                    >
                      <Input
                        type="number"
                        placeholder="-30"
                        value={asrForm.silence_noise_db}
                        onChange={e =>
                          setAsrForm({ ...asrForm, silence_noise_db: e.target.value })
                        }
                      />
                    </Field>

                    <Field
                      label="最短静音（秒）"
                      hint="多长的停顿算「说完了」，默认 0.5"
                    >
                      <Input
                        type="number"
                        step="0.1"
                        placeholder="0.5"
                        value={asrForm.min_silence_seconds}
                        onChange={e =>
                          setAsrForm({ ...asrForm, min_silence_seconds: e.target.value })
                        }
                      />
                    </Field>
                  </>
                )}
              </div>
              <div className="flex gap-2">
                <Button onClick={handleSaveAsr} disabled={asrSaving}>
                  {asrSaving ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="mr-1 h-4 w-4" />
                  )}
                  {asrForm.id ? '保存' : '添加'}
                </Button>
                {asrForm.id && (
                  <Button variant="outline" onClick={resetAsrForm}>
                    取消编辑
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 自定义 Whisper 模型（仅 fast-whisper：名称不符合内置 Systran 约定的模型在此登记映射） */}
      {selectedType === 'fast-whisper' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Boxes className="h-5 w-5" />
              自定义模型
              <span className="text-sm font-normal text-neutral-400">
                登记名称不符合内置约定的模型
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert className="text-sm">
              <AlertDescription>
                填 <strong>HF repo_id</strong>（如{' '}
                <code className="rounded bg-neutral-100 px-1">Systran/faster-whisper-large-v3</code>
                ，会自动下载）或<strong>本地模型目录</strong>（如{' '}
                <code className="rounded bg-neutral-100 px-1">/app/backend/models/my-whisper</code>
                ，目录内需含 <code className="rounded bg-neutral-100 px-1">model.bin</code>，下载会跳过）。
                添加后即可在上方「模型大小」下拉中选用。Docker 部署请把模型目录挂载进容器（见 README 的{' '}
                <code className="rounded bg-neutral-100 px-1">models</code> 卷）。
              </AlertDescription>
            </Alert>

            {config.whisper_custom_models &&
            Object.keys(config.whisper_custom_models).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(config.whisper_custom_models).map(([name, target]) => {
                  const status = modelStatuses.find(m => m.model_size === name)
                  return (
                    <div
                      key={name}
                      className="flex items-center justify-between gap-3 rounded-md border px-4 py-2.5"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 font-medium">
                          {name}
                          {status?.downloaded && (
                            <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                          )}
                          {status?.downloading && (
                            <Loader2 className="h-3.5 w-3.5 animate-spin text-neutral-400" />
                          )}
                          {status?.failed && (
                            <XCircle className="h-3.5 w-3.5 text-red-500" />
                          )}
                        </div>
                        <div className="truncate text-xs text-neutral-400" title={target}>
                          {target}
                        </div>
                        {status?.failed && status?.error && (
                          <div className="truncate text-xs text-red-500" title={status.error}>
                            {status.error}
                          </div>
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-red-500 hover:text-red-600"
                        onClick={() => handleDeleteCustomModel(name)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-sm text-neutral-400">还没有自定义模型</p>
            )}

            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                placeholder="模型名称（自定义，如 my-large-v3）"
                value={newModelName}
                onChange={e => setNewModelName(e.target.value)}
                className="sm:max-w-[220px]"
              />
              <Input
                placeholder="HF repo_id 或本地路径"
                value={newModelTarget}
                onChange={e => setNewModelTarget(e.target.value)}
                className="flex-1"
              />
              <Button onClick={handleAddCustomModel} disabled={addingModel}>
                {addingModel ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-1 h-4 w-4" />
                )}
                添加
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
