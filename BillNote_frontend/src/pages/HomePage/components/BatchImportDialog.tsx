import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { generateNotes } from '@/services/note'
import type { BatchGeneratePayload, BatchGenerateResult, ExpandResult } from '@/services/note'
import { parseRangeSelection } from '@/utils/range'

/** 超过这个条数就弹二次确认（spec 009 决策 13：不设硬上限，只提醒）。 */
const BATCH_CONFIRM_THRESHOLD = 200

export interface BatchDefaults {
  quality: string
  format?: string[]
  style?: string
  extras?: string
  screenshot?: boolean
  link?: boolean
  video_understanding?: boolean
  video_interval?: number
  grid_size?: number[]
  sampling_mode?: string
  max_frames?: number
  frames_per_second?: number
  frame_limit_mode?: string
  ocr_assist?: boolean | null
}

interface BatchImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaults: BatchDefaults
  /** 主表单里「展开预览」已经请求好的结果；对话框只负责展示 / 勾选。 */
  result: ExpandResult | null
  /** 主表单里的原始链接，用于从 ?p= 预选某一 P。 */
  sourceUrl?: string
  /**
   * 提交成功的回调。`groupName` 是本次整批落进的组名（必填，spec 009 决策 1）；
   * `groupId` 是后端本次新建的组 id（`null` = 整批都被去重/在途跳过，后端没建组，
   * spec 009 决策 2）。前端本地那些任务必须同时带上两者，否则刚提交的任务在
   * 分组列表里会先落到「未分组」（m04884）。
   */
  onSubmitted: (results: BatchGenerateResult[], groupName: string, groupId: string | null) => void
}

interface FlatPart {
  key: string
  bvid: string
  videoTitle: string
  hasError: boolean
  part: ExpandResult['videos'][number]['parts'][number]
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '-'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSizeMb(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))} 分钟`
  const hours = minutes / 60
  return hours < 24 ? `${hours.toFixed(1)} 小时` : `${(hours / 24).toFixed(1)} 天`
}

/**
 * 粗估这一批的磁盘与耗时，只用于二次确认的提示文案（spec 009 决策 13：不设硬上限，只提醒）。
 * 口径来自 spec 009 §3 的实测：音视频产物约 1 MB / 分钟（开视频理解/截图可达数倍），
 * 单个 1–3 小时视频实际耗时 10–60 分钟，且后端 `background_tasks` 是逐条串行
 * （批量内并发度 = 1），所以整批耗时近似各任务耗时之和。
 * 拿不到时长（duration 为 0）时按每条 30 分钟兜底，宁可估高不估低。
 */
function estimateBatchCost(totalDurationSec: number, count: number) {
  const totalMinutes = totalDurationSec > 0 ? totalDurationSec / 60 : count * 30
  return {
    diskLowMb: totalMinutes,
    diskHighMb: totalMinutes * 4,
    minutesLow: totalMinutes * 0.5,
    minutesHigh: totalMinutes * 1.2,
  }
}

function extractPFromUrl(url: string): number | null {
  const m = url.match(/[?&]p=(\d+)/)
  return m ? parseInt(m[1], 10) : null
}

export default function BatchImportDialog({
  open,
  onOpenChange,
  defaults,
  result,
  sourceUrl = '',
  onSubmitted,
}: BatchImportDialogProps) {
  const [submitting, setSubmitting] = useState(false)
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [rangeInput, setRangeInput] = useState('')
  const [groupName, setGroupName] = useState('')
  // 用户手动改过分组名之后，就不再被展开结果覆盖。
  const [groupNameTouched, setGroupNameTouched] = useState(false)

  const flatParts = useMemo<FlatPart[]>(() => {
    if (!result) return []
    const list: FlatPart[] = []
    result.videos.forEach(video => {
      video.parts.forEach(part => {
        list.push({
          key: part.video_id,
          bvid: video.bvid,
          videoTitle: video.title,
          hasError: !!video.error,
          part,
        })
      })
    })
    return list
  }, [result])

  // 每次拿到新的展开结果就重置勾选：默认全选；若链接带 ?p= 则只选那一 P。
  useEffect(() => {
    if (!result) {
      setSelected({})
      setRangeInput('')
      return
    }
    const pFromUrl = extractPFromUrl(sourceUrl)
    const next: Record<string, boolean> = {}
    result.videos.forEach(video => {
      video.parts.forEach(part => {
        const ok = !video.error && !part.already_generated
        next[part.video_id] = ok && (!pFromUrl || part.p === pFromUrl)
      })
    })
    setSelected(next)
    setRangeInput('')
    // 默认用合集 / 视频标题当组名：批量新建时整批落在同一个组里（m04884）。
    // 用户手动改过就以用户为准，不再被展开结果覆盖。
    if (!groupNameTouched) setGroupName(result.title || '')
  }, [result, sourceUrl, groupNameTouched])

  const selectable = (item: FlatPart) => !item.hasError && !item.part.already_generated
  const selectedCount = flatParts.filter(i => selected[i.key] && selectable(i)).length

  const setAll = (value: boolean) => {
    const next: Record<string, boolean> = {}
    flatParts.forEach(item => {
      next[item.key] = value && selectable(item)
    })
    setSelected(next)
  }

  const applyRange = () => {
    const picked = parseRangeSelection(rangeInput, flatParts.length)
    if (picked.length === 0) {
      toast.error('范围格式无效，示例：3-7 或 1,3-5')
      return
    }
    const next: Record<string, boolean> = {}
    flatParts.forEach((item, idx) => {
      next[item.key] = picked.includes(idx + 1) && selectable(item)
    })
    setSelected(next)
  }

  const handleSubmit = async () => {
    const picked = flatParts.filter(item => selected[item.key] && selectable(item))
    const items = picked.map(item => ({
      bvid: item.bvid,
      p: item.part.p,
      video_id: item.part.video_id,
      url: item.part.url,
    }))

    if (items.length === 0) {
      toast.error('请至少勾选一个分P')
      return
    }

    // 分组名必填（spec 009 决策 1）：后端按组名整批建组，留空整批会落进「未分组」，
    // 正是用户抱怨的那个问题，所以这里硬拦一道，而不是静默放行。
    const trimmedGroupName = groupName.trim()
    if (!trimmedGroupName) {
      toast.error('请填写分组名称')
      return
    }

    // 条数超过阈值时二次确认（spec 009 决策 13：不设硬上限，只提示预估磁盘与时长）。
    if (items.length > BATCH_CONFIRM_THRESHOLD) {
      const totalDuration = picked.reduce((sum, item) => sum + (item.part.duration || 0), 0)
      const cost = estimateBatchCost(totalDuration, items.length)
      const ok = window.confirm(
        `本次将提交 ${items.length} 个任务，超过 ${BATCH_CONFIRM_THRESHOLD} 条。\n\n` +
          `预估磁盘占用：${formatSizeMb(cost.diskLowMb)} ~ ${formatSizeMb(cost.diskHighMb)}\n` +
          `预估耗时：${formatMinutes(cost.minutesLow)} ~ ${formatMinutes(cost.minutesHigh)}` +
          `（后端逐个串行执行）\n\n` +
          `确认继续提交吗？`
      )
      if (!ok) return
    }

    const payload: BatchGeneratePayload = {
      platform: 'bilibili',
      items,
      quality: defaults.quality,
      format: defaults.format,
      style: defaults.style,
      extras: defaults.extras,
      screenshot: defaults.screenshot,
      link: defaults.link,
      video_understanding: defaults.video_understanding,
      video_interval: defaults.video_interval,
      grid_size: defaults.grid_size,
      sampling_mode: defaults.sampling_mode,
      max_frames: defaults.max_frames,
      frames_per_second: defaults.frames_per_second,
      frame_limit_mode: defaults.frame_limit_mode,
      ocr_assist: defaults.ocr_assist,
      group_name: trimmedGroupName,
    }

    setSubmitting(true)
    try {
      const { results, group_id } = await generateNotes(payload)
      const queued = results.filter(r => r.status === 'queued').length
      const skipped = results.filter(r => r.status === 'skipped').length
      if (queued > 0) {
        toast.success(`已提交 ${queued} 个任务${skipped ? `，跳过 ${skipped} 个已生成` : ''}`)
      } else if (skipped > 0) {
        toast.success(`${skipped} 个任务已生成过，已跳过`)
      }
      // group_id 为 null = 整批被去重/在途跳过、后端没建组，交给 store 保持未分组。
      onSubmitted(results, trimmedGroupName, group_id ?? null)
      onOpenChange(false)
    } catch (e) {
      console.error('批量提交失败', e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>批量导入（B 站合集 / 多P）</DialogTitle>
          <DialogDescription className="sr-only">选择要批量生成笔记的视频分P</DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="text-muted-foreground py-10 text-center text-sm">正在获取视频列表…</div>
        ) : (
          <>
            <div className="text-muted-foreground text-sm">
              {result.type === 'collection' ? '合集' : '视频'}：{result.title || '-'}
              {result.owner?.name ? ` · ${result.owner.name}` : ''}
              <span className="ml-2">共 {flatParts.length} 个分P</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground text-sm">
                分组名 <span className="text-red-500">*</span>
              </span>
              <Input
                className="h-8 w-56"
                placeholder="请输入分组名称（必填）"
                value={groupName}
                aria-invalid={!groupName.trim()}
                onChange={e => {
                  setGroupNameTouched(true)
                  setGroupName(e.target.value)
                }}
              />
              {!groupName.trim() && <span className="text-xs text-red-500">请填写分组名称</span>}
              <Button type="button" size="sm" variant="outline" onClick={() => setAll(true)}>
                全选
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setAll(false)}>
                全不选
              </Button>
              <Input
                className="h-8 w-40"
                placeholder="范围，如 3-7"
                value={rangeInput}
                onChange={e => setRangeInput(e.target.value)}
              />
              <Button type="button" size="sm" variant="outline" onClick={applyRange}>
                应用范围
              </Button>
              <span className="text-muted-foreground text-sm">已选 {selectedCount}</span>
            </div>

            <ScrollArea className="h-[420px] rounded-md border p-2">
              {result.videos.map(video => (
                <div key={video.bvid} className="mb-3">
                  <div className="mb-1 text-sm font-medium">
                    {video.title || video.bvid}
                    <span className="text-muted-foreground ml-2 text-xs">{video.bvid}</span>
                  </div>
                  {video.error && <div className="pl-6 text-xs text-red-500">{video.error}</div>}
                  {video.parts.map(part => {
                    const item: FlatPart = {
                      key: part.video_id,
                      bvid: video.bvid,
                      videoTitle: video.title,
                      hasError: !!video.error,
                      part,
                    }
                    const ok = selectable(item)
                    return (
                      <label
                        key={part.video_id}
                        className="flex items-center gap-2 py-1 pl-6 text-sm"
                      >
                        <Checkbox
                          checked={!!selected[part.video_id]}
                          disabled={!ok}
                          onCheckedChange={() =>
                            setSelected(prev => ({
                              ...prev,
                              [part.video_id]: !prev[part.video_id],
                            }))
                          }
                        />
                        <span className={ok ? '' : 'text-muted-foreground line-through'}>
                          P{part.p} {part.title}
                        </span>
                        <span className="text-muted-foreground text-xs">
                          {formatDuration(part.duration)}
                        </span>
                        {part.already_generated && (
                          <span className="rounded bg-gray-200 px-1 text-xs text-gray-600">
                            已生成
                          </span>
                        )}
                      </label>
                    )
                  })}
                </div>
              ))}
            </ScrollArea>
          </>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            // 组名必填（spec 009 决策 1）：空组名时按钮直接禁用，避免提交出去再被后端拒绝。
            disabled={submitting || selectedCount === 0 || !groupName.trim()}
            title={!groupName.trim() ? '请先填写分组名称' : undefined}
          >
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            确定生成（{selectedCount}）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
