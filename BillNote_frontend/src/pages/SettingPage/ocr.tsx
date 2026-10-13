import { useCallback, useEffect, useState } from 'react'
import { toast } from 'react-hot-toast'
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  Plug,
  Save,
  ScanText,
  Settings2,
} from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import {
  getOcrConfig,
  testOcrConfig,
  updateOcrConfig,
  type OcrConfig,
  type OcrConfigInput,
  type OcrDefaults,
  type OcrTestFailure,
  type OcrTestSuccess,
} from '@/services/ocr'

/** 表单里所有可编辑字段（不含只读的 _defaults） */
type FormState = {
  enabled: boolean
  base_url: string
  api_key: string
  model_name: string
  timeout: string
  max_file_mb: string
  max_pages: string
}

const EMPTY_FORM: FormState = {
  enabled: false,
  base_url: '',
  api_key: '',
  model_name: '',
  timeout: '',
  max_file_mb: '',
  max_pages: '',
}

const formFromConfig = (config: OcrConfig): FormState => ({
  enabled: Boolean(config.enabled),
  base_url: config.base_url ?? '',
  api_key: config.api_key ?? '',
  model_name: config.model_name ?? '',
  timeout: config.timeout === undefined || config.timeout === null ? '' : String(config.timeout),
  max_file_mb:
    config.max_file_mb === undefined || config.max_file_mb === null
      ? ''
      : String(config.max_file_mb),
  max_pages:
    config.max_pages === undefined || config.max_pages === null ? '' : String(config.max_pages),
})

/** 数字输入：留空则不下发该字段（沿用后端默认），否则必须能解析成数字 */
const numberOrUndefined = (raw: string): number | undefined => {
  const trimmed = raw.trim()
  if (!trimmed) return undefined
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

/** 把上游原始错误正文转成可展示字符串——绝不吞掉它 */
const formatDetail = (detail: unknown): string => {
  if (detail === undefined || detail === null) return ''
  if (typeof detail === 'string') return detail
  try {
    return JSON.stringify(detail, null, 2)
  } catch {
    return String(detail)
  }
}

export default function OcrSettingPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [defaults, setDefaults] = useState<OcrDefaults | null>(null)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const [testSuccess, setTestSuccess] = useState<OcrTestSuccess | null>(null)
  const [testFailure, setTestFailure] = useState<OcrTestFailure | null>(null)

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const config = await getOcrConfig()
      setForm(formFromConfig(config))
      setDefaults(config._defaults ?? null)
    } catch (error) {
      const message = (error as { msg?: string })?.msg || '读取 OCR 配置失败'
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

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(current => ({ ...current, [key]: value }))
  }

  /**
   * 构造请求体。
   *
   * 端点路径、鉴权头形态、文件字段名、响应取值路径都已经是后端常量，
   * 不再是可提交字段；这里只发真正需要用户填的项。
   */
  const buildPayload = (): OcrConfigInput | null => {
    const payload: OcrConfigInput = {
      enabled: form.enabled,
      base_url: form.base_url,
      api_key: form.api_key,
      model_name: form.model_name,
    }

    const timeout = numberOrUndefined(form.timeout)
    if (timeout !== undefined) payload.timeout = timeout

    const maxFileMb = numberOrUndefined(form.max_file_mb)
    if (maxFileMb !== undefined) payload.max_file_mb = maxFileMb

    const maxPages = numberOrUndefined(form.max_pages)
    if (maxPages !== undefined) payload.max_pages = maxPages

    return payload
  }

  const handleSave = async () => {
    const payload = buildPayload()
    if (!payload) return

    setSaving(true)
    try {
      await updateOcrConfig(payload)
      toast.success('OCR 配置已保存')
      // 重新拉取，刷新打码后的 api_key
      await load()
    } catch (error) {
      toast.error((error as { msg?: string })?.msg || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    const payload = buildPayload()
    if (!payload) return

    setTesting(true)
    setTestSuccess(null)
    setTestFailure(null)
    try {
      const result = await testOcrConfig(payload)
      if (result?.ok) {
        setTestSuccess(result)
        toast.success(result.message || '连接成功')
      } else {
        // code === 0 但 ok=false 的兜底分支
        setTestFailure({
          ok: false,
          message: result?.message || '连接失败',
          detail: formatDetail((result as { detail?: unknown })?.detail),
          code: (result as { code?: string | null })?.code ?? null,
          status_code: (result as { status_code?: number | null })?.status_code ?? null,
        })
        toast.error(result?.message || '连接失败')
      }
    } catch (error) {
      // 拦截器把整个 envelope 作为 rejection 抛出来（code !== 0）
      const envelope = (error ?? {}) as {
        msg?: string
        data?: Partial<OcrTestFailure> | null
      }
      const data = envelope.data ?? null
      setTestFailure({
        ok: false,
        message: data?.message || envelope.msg || '连接失败',
        detail: formatDetail(data?.detail),
        code: data?.code ?? null,
        status_code: data?.status_code ?? null,
      })
      toast.error(envelope.msg || '连接失败')
    } finally {
      setTesting(false)
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
            <AlertTitle>无法读取 OCR 配置</AlertTitle>
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
            <ScanText className="h-6 w-6" />
            OCR 辅助
          </h2>
          <p className="mt-1 text-sm text-neutral-500">
            对视频画面做文字识别，把识别到的文字一并交给模型，用于补充字幕缺失的信息。
          </p>
        </div>

        {!form.enabled && (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>当前未启用</AlertTitle>
            <AlertDescription>
              笔记将只依据转写文本生成，不做画面文字识别。下方配置仍可正常编辑与保存，填写完成后打开开关即可生效。
            </AlertDescription>
          </Alert>
        )}

        {/* ---------------- 基础 ---------------- */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Settings2 className="h-5 w-5" />
              基础
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
              <div className="space-y-0.5">
                <div className="text-sm font-medium">启用 OCR 辅助</div>
                <div className="text-xs text-neutral-500">
                  关闭时不做任何 OCR 调用；开启前请确保服务地址、API Key、模型名已填写。
                </div>
              </div>
              <Switch
                checked={form.enabled}
                onCheckedChange={checked => setField('enabled', checked)}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">服务地址（base_url）</label>
              <Input
                value={form.base_url}
                onChange={event => setField('base_url', event.target.value)}
                placeholder={defaults?.base_url ?? 'https://open.bigmodel.cn'}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">API Key</label>
              <Input
                type="password"
                value={form.api_key}
                onChange={event => setField('api_key', event.target.value)}
                placeholder="留空或保持打码值即不修改已保存的密钥"
                autoComplete="off"
              />
              <p className="text-xs text-neutral-500">
                已保存的密钥以打码形式展示（形如 3fcb************OyK）。保持原样提交即表示不修改。
              </p>
              <p className="text-xs text-neutral-500">
                注意：智谱的 Key 形如 <code>{'{id}.{secret}'}</code>，<strong>中间那个点</strong>
                以及点之后的部分都不能少。只粘贴点之前那一段会一直报
                <code>401 令牌已过期或验证不正确</code>——请到 API Keys 页面完整复制。
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">模型名（model_name）</label>
              <Input
                value={form.model_name}
                onChange={event => setField('model_name', event.target.value)}
                placeholder={defaults?.model_name ?? 'glm-ocr'}
              />
            </div>
          </CardContent>
        </Card>

        {/* ---------------- 限制 ---------------- */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Settings2 className="h-5 w-5" />
              请求限制
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert>
              <AlertDescription className="text-sm">
                以下三项通常不需要修改，留空即使用灰色提示里的默认值。它们是与上游限制相关的护栏
                （单张图片上限、超时、页数），不是部署差异——端点、鉴权方式与响应解析方式都已经是
                内置的智谱专用实现，无需配置。
              </AlertDescription>
            </Alert>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm font-medium">timeout（秒）</label>
                <Input
                  type="number"
                  min="1"
                  value={form.timeout}
                  onChange={event => setField('timeout', event.target.value)}
                  placeholder={defaults ? String(defaults.timeout) : '300'}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">max_file_mb</label>
                <Input
                  type="number"
                  min="1"
                  value={form.max_file_mb}
                  onChange={event => setField('max_file_mb', event.target.value)}
                  placeholder={defaults ? String(defaults.max_file_mb) : '10'}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">max_pages</label>
                <Input
                  type="number"
                  min="1"
                  value={form.max_pages}
                  onChange={event => setField('max_pages', event.target.value)}
                  placeholder={defaults ? String(defaults.max_pages) : '30'}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ---------------- 操作 ---------------- */}
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={saving || testing} onClick={() => void handleSave()}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存
          </Button>
          <Button variant="outline" disabled={saving || testing} onClick={() => void handleTest()}>
            {testing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Plug className="mr-2 h-4 w-4" />
            )}
            连接测试
          </Button>
          <span className="text-xs text-neutral-500">
            连接测试使用当前表单内容作为草稿，不会保存配置。
          </span>
        </div>

        {/* ---------------- 测试结果 ---------------- */}
        {testSuccess && (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>连接成功</AlertTitle>
            <AlertDescription className="space-y-3">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                <span>
                  协议：<span className="font-mono">{testSuccess.protocol}</span>
                </span>
                <span>
                  模型：<span className="font-mono">{testSuccess.model_name}</span>
                </span>
                <span>
                  识别块数：<span className="font-mono">{testSuccess.blocks}</span>
                </span>
              </div>
              {testSuccess.preview ? (
                <div className="space-y-1">
                  <div className="text-xs text-neutral-500">
                    测试图识别结果（前 120 字，证明调用确实走通了）
                  </div>
                  <pre className="max-h-48 overflow-auto rounded border bg-neutral-50 p-3 font-mono text-xs whitespace-pre-wrap">
                    {testSuccess.preview}
                  </pre>
                </div>
              ) : (
                <div className="text-xs text-neutral-500">
                  上游调用成功，但测试图未返回可识别的文本内容。
                </div>
              )}
            </AlertDescription>
          </Alert>
        )}

        {testFailure && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>连接失败：{testFailure.message}</AlertTitle>
            <AlertDescription className="space-y-3">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                {testFailure.code ? (
                  <span>
                    上游错误码：<span className="font-mono">{testFailure.code}</span>
                  </span>
                ) : null}
                {testFailure.status_code ? (
                  <span>
                    HTTP 状态码：<span className="font-mono">{testFailure.status_code}</span>
                  </span>
                ) : null}
              </div>
              {testFailure.detail ? (
                <div className="space-y-1">
                  <div className="text-xs">上游原始响应（原样展示，便于对照上游文档排查）</div>
                  <pre className="max-h-80 overflow-auto rounded border bg-neutral-50 p-3 font-mono text-xs whitespace-pre-wrap text-neutral-900">
                    {testFailure.detail}
                  </pre>
                </div>
              ) : (
                <div className="text-xs">
                  上游未返回响应正文（可能是网络不通或请求被本地拦截）。请检查服务地址与网络。
                </div>
              )}
            </AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  )
}
