/* NoteForm.tsx ---------------------------------------------------- */
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form.tsx'
import { useEffect, useState } from 'react'
import { useForm, useWatch, type FieldErrors } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { Info, Loader2 } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert.tsx'
import { expandUrl, generateNote } from '@/services/note.ts'
import type { BatchGenerateResult, ExpandResult } from '@/services/note.ts'
import BatchImportDialog from './BatchImportDialog'
import { uploadFile } from '@/services/upload.ts'
import { useTaskStore } from '@/store/taskStore'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import { Checkbox } from '@/components/ui/checkbox.tsx'
import { Button } from '@/components/ui/button.tsx'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select.tsx'
import { Input } from '@/components/ui/input.tsx'
import { Textarea } from '@/components/ui/textarea.tsx'
import { noteStyles, noteFormats, videoPlatforms } from '@/constant/note.ts'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

/* -------------------- 校验 Schema -------------------- */
/** 用户粘贴的链接常缺协议头（如 bilibili.com/...），无任何 scheme 时自动补 https:// */
const withScheme = (url: string) => (/^[a-z][a-z0-9+.-]*:\/\//i.test(url) ? url : `https://${url}`)

const formSchema = z
  .object({
    video_url: z.string().optional(),
    platform: z.string().nonempty('请选择平台'),
    quality: z.enum(['fast', 'medium', 'slow']),
    screenshot: z.boolean().optional(),
    link: z.boolean().optional(),
    format: z.array(z.string()).default([]),
    style: z.string().nonempty('请选择笔记生成风格'),
    extras: z.string().optional(),
    video_understanding: z.boolean().optional(),
    video_interval: z.coerce.number().min(1).max(30).default(6).optional(),
    sampling_mode: z.enum(['interval', 'smart', 'hybrid']).default('interval').optional(),
    // 不设上限：几个小时的课程需要更大的抽帧预算
    max_frames: z.coerce.number().min(5).default(60).optional(),
    frames_per_second: z.coerce.number().min(1).max(10).default(2).optional(),
    frame_limit_mode: z.enum(['total', 'per_second']).default('total').optional(),
    // spec 008 ticket 02：本次任务的 OCR 辅助覆盖。
    // null = 不覆盖，跟随设置页的全局开关（默认）。
    ocr_assist: z.boolean().nullable().optional(),
    batch_mode: z.boolean().optional(),
    grid_size: z
      .tuple([z.coerce.number().min(1).max(10), z.coerce.number().min(1).max(10)])
      .default([2, 2])
      .optional(),
  })
  .superRefine(({ video_url, platform }, ctx) => {
    if (platform === 'local') {
      if (!video_url) {
        ctx.addIssue({ code: 'custom', message: '本地视频路径不能为空', path: ['video_url'] })
      }
    } else {
      if (!video_url) {
        ctx.addIssue({ code: 'custom', message: '视频链接不能为空', path: ['video_url'] })
      } else {
        try {
          const url = new URL(withScheme(video_url))
          if (!['http:', 'https:'].includes(url.protocol)) throw new Error()
        } catch {
          ctx.addIssue({ code: 'custom', message: '请输入正确的视频链接', path: ['video_url'] })
        }
      }
    }
  })

type NoteFormInput = z.input<typeof formSchema>
export type NoteFormValues = z.output<typeof formSchema>

type NoteQuality = NoteFormValues['quality']
const normalizeQuality = (quality: string | undefined): NoteQuality =>
  quality === 'fast' || quality === 'slow' ? quality : 'medium'

/* -------------------- 可复用子组件 -------------------- */
const SectionHeader = ({ title, tip }: { title: string; tip?: string }) => (
  <div className="my-3 flex items-center justify-between">
    <h2 className="block">{title}</h2>
    {tip && (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="hover:text-primary h-4 w-4 cursor-pointer text-neutral-400" />
          </TooltipTrigger>
          <TooltipContent className="text-xs">{tip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )}
  </div>
)

const CheckboxGroup = ({
  value = [],
  onChange,
  disabledMap,
}: {
  value?: string[]
  onChange: (v: string[]) => void
  disabledMap: Record<string, boolean>
}) => (
  <div className="flex flex-wrap space-x-1.5">
    {noteFormats.map(({ label, value: v }) => (
      <label key={v} className="flex items-center space-x-2">
        <Checkbox
          checked={value.includes(v)}
          disabled={disabledMap[v]}
          onCheckedChange={checked =>
            onChange(checked ? [...value, v] : value.filter(x => x !== v))
          }
        />
        <span>{label}</span>
      </label>
    ))}
  </div>
)

/* -------------------- 主组件 -------------------- */
const NoteForm = () => {
  const navigate = useNavigate()
  const [isUploading, setIsUploading] = useState(false)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [expanding, setExpanding] = useState(false)
  const [expandResult, setExpandResult] = useState<ExpandResult | null>(null)
  /* ---- 全局状态 ---- */
  const { addPendingTask, currentTaskId, getCurrentTask } = useTaskStore()

  /* ---- 表单 ---- */
  const form = useForm<NoteFormInput, unknown, NoteFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      platform: 'bilibili',
      quality: 'medium',
      style: 'minimal',
      video_interval: 6,
      sampling_mode: 'interval',
      max_frames: 60,
      frames_per_second: 2,
      frame_limit_mode: 'total',
      ocr_assist: null,
      batch_mode: false,
      grid_size: [2, 2],
      format: [],
    },
  })
  const currentTask = getCurrentTask()

  /* ---- 派生状态（只 watch 一次，提高性能） ---- */
  const platform = useWatch({ control: form.control, name: 'platform' }) as string
  const videoUnderstandingEnabled = useWatch({ control: form.control, name: 'video_understanding' })
  const samplingMode = useWatch({ control: form.control, name: 'sampling_mode' })
  const frameLimitMode = useWatch({ control: form.control, name: 'frame_limit_mode' })
  const batchMode = useWatch({ control: form.control, name: 'batch_mode' })
  const ocrAssist = useWatch({ control: form.control, name: 'ocr_assist' })
  // 三态收敛成一个字符串给 Select 用：null 是合法的第三态（跟随设置），
  // 不能塞进 boolean，否则「跟随设置」和「本次关闭」会渲染成同一项。
  const ocrAssistMode = ocrAssist === true ? 'on' : ocrAssist === false ? 'off' : 'global'

  /* ---- 副作用 ---- */
  useEffect(() => {
    if (!currentTask) return
    const { formData } = currentTask

    console.log('currentTask.formData.platform:', formData.platform)

    form.reset({
      platform: formData.platform || 'bilibili',
      video_url: formData.video_url || '',
      style: formData.style || 'minimal',
      quality: normalizeQuality(formData.quality),
      extras: formData.extras || '',
      screenshot: formData.screenshot ?? false,
      link: formData.link ?? false,
      video_understanding: formData.video_understanding ?? false,
      video_interval: formData.video_interval ?? 6,
      sampling_mode: formData.sampling_mode ?? 'interval',
      max_frames: formData.max_frames ?? 60,
      frames_per_second: formData.frames_per_second ?? 2,
      frame_limit_mode: formData.frame_limit_mode ?? 'total',
      // 老任务的 formData 里没有这个字段，?? null 会把 undefined 收敛成「跟随设置」
      ocr_assist: formData.ocr_assist ?? null,
      batch_mode: formData.batch_mode ?? false,
      grid_size: formData.grid_size ?? [2, 2],
      format: formData.format ?? [],
    })
  }, [
    // 当下面任意一个变了，就重新 reset
    currentTaskId,
    // 还要加上 formData 的各字段，或者直接 currentTask
    currentTask?.formData,
  ])

  /* ---- 帮助函数 ---- */
  const isGenerating = () => !['SUCCESS', 'FAILED', undefined].includes(getCurrentTask()?.status)
  const generating = isGenerating()
  const handleFileUpload = async (file: File, cb: (url: string) => void) => {
    const formData = new FormData()
    formData.append('file', file)
    setIsUploading(true)
    setUploadSuccess(false)

    try {
      const data = await uploadFile(formData)
      cb(data.url)
      setUploadSuccess(true)
    } catch (err) {
      console.error('上传失败:', err)
      // message.error('上传失败，请重试')
    } finally {
      setIsUploading(false)
    }
  }

  const onSubmit = async (values: NoteFormValues) => {
    if (values.batch_mode || batchMode) {
      // 批量模式：提交动作 = 展开预览（在主表单里请求，成功后才弹对话框）
      await handleExpandPreview()
      return
    }
    console.log('Not even go here')
    // axios 拦截器 reject 出来的是普通对象 `{code,msg,data}`，不是 Error 实例；
    // 只读这两个字段，避免 any。
    const videoUrl =
      values.platform === 'local' ? values.video_url || '' : withScheme(values.video_url || '')
    const payload = {
      ...values,
      video_url: videoUrl,
    }
    const apiError = (err: unknown): { reason?: string; downloading?: boolean } | undefined =>
      (err as { data?: { reason?: string; downloading?: boolean } } | undefined)?.data

    try {
      const data = await generateNote(payload)
      if (!data) return
      addPendingTask(data.task_id, values.platform, payload)
    } catch (e) {
      // 就绪门禁：本地转写模型还没下载好。后端返回 reason='transcriber_model_not_ready'，
      // 引导用户去「设置 → 音频转写配置」下载，而不是留一个静默失败的任务。
      const data = apiError(e)
      if (data?.reason === 'transcriber_model_not_ready') {
        const downloading = data.downloading
        toast.error(
          downloading
            ? '转写模型正在下载中，请稍候再提交'
            : '转写模型尚未下载，请先去「音频转写配置」页下载'
        )
        if (!downloading) navigate('/settings/transcriber')
        return
      }
      // 其余错误：axios 拦截器已经弹过 toast，这里只兜底不让 promise 变成未处理 rejection
      console.error('提交任务失败：', e)
    }
  }
  const onInvalid = (errors: FieldErrors<NoteFormInput>) => {
    console.warn('表单校验失败：', errors)
    // message.error('请完善所有必填项后再提交')
  }
  // 批量模式主按钮：先在主表单里请求 /expand，成功后才打开对话框
  const handleExpandPreview = async () => {
    const raw = (form.getValues().video_url || '').trim()
    if (!raw) {
      toast.error('请输入合集或多P视频链接')
      return
    }
    setExpanding(true)
    try {
      const data = await expandUrl(withScheme(raw))
      setExpandResult(data)
      setBatchOpen(true)
    } catch (e) {
      console.error('展开失败', e)
    } finally {
      setExpanding(false)
    }
  }

  const FormButton = () => {
    const label = generating ? '正在生成…' : '生成笔记'

    return (
      <div className="flex gap-2">
        <Button
          type={batchMode ? 'button' : 'submit'}
          className="bg-primary flex-1"
          disabled={generating || expanding}
          onClick={batchMode ? handleExpandPreview : undefined}
        >
          {(generating || (batchMode && expanding)) && (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          )}
          {batchMode ? (expanding ? '展开中…' : '展开预览') : label}
        </Button>
      </div>
    )
  }

  const batchDefaults = () => {
    const values = form.getValues()
    return {
      quality: values.quality,
      format: values.format,
      style: values.style,
      extras: values.extras,
      screenshot: values.screenshot,
      link: values.link,
      video_understanding: values.video_understanding,
      video_interval: values.video_interval,
      grid_size: values.grid_size,
      sampling_mode: values.sampling_mode,
      max_frames: values.max_frames,
      frames_per_second: values.frames_per_second,
      frame_limit_mode: values.frame_limit_mode,
      ocr_assist: values.ocr_assist ?? null,
    }
  }

  const handleBatchSubmitted = (
    results: BatchGenerateResult[],
    groupName: string,
    groupId: string | null
  ) => {
    const values = form.getValues()
    // 展开/批量只支持 B 站（BatchImportDialog 里 platform 恒为 'bilibili'），
    // 但仍从表单取值，避免再把平台写死。
    const platform = (values.platform as string) || 'bilibili'
    results
      .filter(r => r.status === 'queued' && r.task_id)
      .forEach(r => {
        // 组名 + 组 id 要一起带进本地任务：NoteHistory 要求两者同时存在才归组，
        // 只带组名会让这次批量在分组视图里先显示成「未分组」，要等下一次
        // loadTasks 才跳回正确的组（spec 009 决策 4）。
        // groupId 为 null（整批被去重跳过、后端没建组）时由 store 保持 null。
        addPendingTask(r.task_id as string, platform, { ...values }, groupName, groupId)
      })
  }
  /* -------------------- 渲染 -------------------- */
  return (
    <div className="h-full w-full">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-4">
          {/* 顶部按钮 */}
          <FormButton></FormButton>

          {/* 视频链接 & 平台 */}
          <SectionHeader title="视频链接" tip="支持 B 站、YouTube 等平台" />
          <div className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={!!batchMode}
              onCheckedChange={v => {
                const on = !!v
                form.setValue('batch_mode', on)
                if (on) form.setValue('platform', 'bilibili')
              }}
            />
            <span>批量模式</span>
          </div>
          <div className="flex gap-2">
            {/* 平台选择 */}

            <FormField
              control={form.control}
              name="platform"
              render={({ field }) => (
                <FormItem>
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                    defaultValue={field.value}
                  >
                    <FormControl>
                      <SelectTrigger className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(batchMode
                        ? videoPlatforms?.filter(p => p.value === 'bilibili')
                        : videoPlatforms
                      )?.map(p => (
                        <SelectItem key={p.value} value={p.value}>
                          <div className="flex items-center justify-center gap-2">
                            <div className="h-4 w-4">{p.logo()}</div>
                            <span>{p.label}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage style={{ display: 'none' }} />
                </FormItem>
              )}
            />
            {/* 链接输入 / 上传框 */}
            <FormField
              control={form.control}
              name="video_url"
              render={({ field }) => (
                <FormItem className="flex-1">
                  {platform === 'local' ? (
                    <>
                      <Input placeholder="请输入本地视频路径" {...field} />
                    </>
                  ) : (
                    <Input placeholder="请输入视频网站链接" {...field} />
                  )}
                  <FormMessage style={{ display: 'none' }} />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="video_url"
            render={({ field }) => (
              <FormItem className="flex-1">
                {platform === 'local' && (
                  <>
                    <div
                      className="hover:border-primary mt-2 flex h-40 cursor-pointer items-center justify-center rounded-md border-2 border-dashed border-gray-300 transition-colors"
                      onDragOver={e => {
                        e.preventDefault()
                        e.stopPropagation()
                      }}
                      onDrop={e => {
                        e.preventDefault()
                        const file = e.dataTransfer.files?.[0]
                        if (file) handleFileUpload(file, field.onChange)
                      }}
                      onClick={() => {
                        const input = document.createElement('input')
                        input.type = 'file'
                        input.accept = 'video/*'
                        input.onchange = e => {
                          const file = (e.target as HTMLInputElement).files?.[0]
                          if (file) handleFileUpload(file, field.onChange)
                        }
                        input.click()
                      }}
                    >
                      {isUploading ? (
                        <p className="text-center text-sm text-blue-500">上传中，请稍候…</p>
                      ) : uploadSuccess ? (
                        <p className="text-center text-sm text-green-500">上传成功！</p>
                      ) : (
                        <p className="text-center text-sm text-gray-500">
                          拖拽文件到这里上传 <br />
                          <span className="text-xs text-gray-400">或点击选择文件</span>
                        </p>
                      )}
                    </div>
                  </>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="grid grid-cols-2 gap-2">
            <FormItem>
              <SectionHeader title="当前模型" tip="模型在设置 → 通用设置中统一切换" />
              <Button type="button" variant="outline" onClick={() => navigate('/settings/general')}>
                前往通用设置
              </Button>
            </FormItem>

            {/* 笔记风格 */}
            <FormField
              control={form.control}
              name="style"
              render={({ field }) => (
                <FormItem>
                  <SectionHeader title="笔记风格" tip="选择生成笔记的呈现风格" />
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                    defaultValue={field.value}
                  >
                    <FormControl>
                      <SelectTrigger className="w-full min-w-0 truncate">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {noteStyles.map(({ label, value }) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
          {/* 视频理解 */}
          <SectionHeader title="视频理解" tip="将视频截图发给多模态模型辅助分析" />
          <div className="flex flex-col gap-2">
            <FormField
              control={form.control}
              name="video_understanding"
              render={() => (
                <FormItem>
                  <div className="flex items-center gap-2">
                    <FormLabel>启用</FormLabel>
                    <Checkbox
                      checked={videoUnderstandingEnabled === true}
                      onCheckedChange={v => form.setValue('video_understanding', v === true)}
                    />
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              {/* 采样方式 */}
              <FormField
                control={form.control}
                name="sampling_mode"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>采样方式</FormLabel>
                    <Select
                      disabled={!videoUnderstandingEnabled}
                      value={field.value || 'interval'}
                      onValueChange={field.onChange}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="interval">间隔采样</SelectItem>
                        <SelectItem value="smart">高价值帧采样</SelectItem>
                        <SelectItem value="hybrid">综合采样</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {/* 间隔采样：采样间隔；高价值：限制方式二选一（每秒上限 / 全片上限） */}
              {samplingMode === 'smart' ? (
                <>
                  {/* 限制方式二选一：每秒上限 / 全片上限，只生效一个 */}
                  <FormField
                    control={form.control}
                    name="frame_limit_mode"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>限制方式</FormLabel>
                        <Select
                          disabled={!videoUnderstandingEnabled}
                          value={field.value || 'total'}
                          onValueChange={field.onChange}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="total">全片最大帧数</SelectItem>
                            <SelectItem value="per_second">每秒最大帧数</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  {frameLimitMode === 'per_second' ? (
                    <FormField
                      control={form.control}
                      name="frames_per_second"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>每秒最多帧数</FormLabel>
                          <Input
                            disabled={!videoUnderstandingEnabled}
                            type="number"
                            min={1}
                            max={10}
                            {...field}
                          />
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ) : (
                    <FormField
                      control={form.control}
                      name="max_frames"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>单个视频最大帧数</FormLabel>
                          <Input
                            disabled={!videoUnderstandingEnabled}
                            type="number"
                            min={5}
                            {...field}
                          />
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}
                </>
              ) : samplingMode === 'hybrid' ? (
                <FormField
                  control={form.control}
                  name="max_frames"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>最大帧数</FormLabel>
                      <Input
                        disabled={!videoUnderstandingEnabled}
                        type="number"
                        min={5}
                        {...field}
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ) : (
                <FormField
                  control={form.control}
                  name="video_interval"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>采样间隔（秒）</FormLabel>
                      <Input disabled={!videoUnderstandingEnabled} type="number" {...field} />
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              {/* 拼图大小 */}
              <FormField
                control={form.control}
                name="grid_size"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>拼图尺寸（列 × 行）</FormLabel>
                    <div className="flex items-center space-x-2">
                      <Input
                        disabled={!videoUnderstandingEnabled}
                        type="number"
                        value={field.value?.[0] || 3}
                        onChange={e => field.onChange([+e.target.value, field.value?.[1] || 3])}
                        className="w-16"
                      />
                      <span>x</span>
                      <Input
                        disabled={!videoUnderstandingEnabled}
                        type="number"
                        value={field.value?.[1] || 3}
                        onChange={e => field.onChange([field.value?.[0] || 3, +e.target.value])}
                        className="w-16"
                      />
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            {/* OCR 辅助：设置页管「配没配好」，这里管「这一次用不用」 */}
            <FormField
              control={form.control}
              name="ocr_assist"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>OCR 辅助</FormLabel>
                  <Select
                    disabled={!videoUnderstandingEnabled}
                    value={ocrAssistMode}
                    onValueChange={v => field.onChange(v === 'global' ? null : v === 'on')}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="global">跟随设置</SelectItem>
                      <SelectItem value="on">本次启用</SelectItem>
                      <SelectItem value="off">本次关闭</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-muted-foreground text-xs">
                    关闭只跳过「把图上文字搬进笔记」这一步；画面值不值得编入笔记的判定
                    仍然会跑，插图集合不变。
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Alert variant="warning" className="text-sm">
              <AlertDescription>
                <strong>提示：</strong>视频理解功能必须使用多模态模型。
              </AlertDescription>
            </Alert>
          </div>

          {/* 笔记格式 */}
          <FormField
            control={form.control}
            name="format"
            render={({ field }) => (
              <FormItem>
                <SectionHeader title="笔记格式" tip="选择要包含的笔记元素" />
                <CheckboxGroup
                  value={field.value}
                  onChange={field.onChange}
                  disabledMap={{
                    link: platform === 'local',
                    screenshot: !videoUnderstandingEnabled,
                  }}
                />
                <FormMessage />
              </FormItem>
            )}
          />

          {/* 备注 */}
          <FormField
            control={form.control}
            name="extras"
            render={({ field }) => (
              <FormItem>
                <SectionHeader title="备注" tip="可在 Prompt 结尾附加自定义说明" />
                <Textarea placeholder="笔记需要罗列出 xxx 关键点…" {...field} />
                <FormMessage />
              </FormItem>
            )}
          />
        </form>
      </Form>

      <BatchImportDialog
        open={batchOpen}
        onOpenChange={setBatchOpen}
        defaults={batchDefaults()}
        result={expandResult}
        sourceUrl={(form.getValues().video_url as string) || ''}
        onSubmitted={handleBatchSubmitted}
      />
    </div>
  )
}

export default NoteForm
