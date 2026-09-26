import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { generateNotes } from '@/services/note'
import type {
  BatchGeneratePayload,
  BatchGenerateResult,
  ExpandResult,
} from '@/services/note'
import { parseRangeSelection } from '@/utils/range'

export interface BatchDefaults {
  quality: string
  model_name: string
  provider_id: string
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
}

interface BatchImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaults: BatchDefaults
  /** 主表单里「展开预览」已经请求好的结果；对话框只负责展示 / 勾选。 */
  result: ExpandResult | null
  /** 主表单里的原始链接，用于从 ?p= 预选某一 P。 */
  sourceUrl?: string
  onSubmitted: (results: BatchGenerateResult[]) => void
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
  }, [result, sourceUrl])

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
    const items = flatParts
      .filter(item => selected[item.key] && selectable(item))
      .map(item => ({
        bvid: item.bvid,
        p: item.part.p,
        video_id: item.part.video_id,
        url: item.part.url,
      }))

    if (items.length === 0) {
      toast.error('请至少勾选一个分P')
      return
    }

    const payload: BatchGeneratePayload = {
      platform: 'bilibili',
      items,
      quality: defaults.quality,
      model_name: defaults.model_name,
      provider_id: defaults.provider_id,
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
    }

    setSubmitting(true)
    try {
      const { results } = await generateNotes(payload)
      const queued = results.filter(r => r.status === 'queued').length
      const skipped = results.filter(r => r.status === 'skipped').length
      if (queued > 0) {
        toast.success(`已提交 ${queued} 个任务${skipped ? `，跳过 ${skipped} 个已生成` : ''}`)
      } else if (skipped > 0) {
        toast.success(`${skipped} 个任务已生成过，已跳过`)
      }
      onSubmitted(results)
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
        </DialogHeader>

        {!result ? (
          <div className="py-10 text-center text-sm text-muted-foreground">
            正在获取视频列表…
          </div>
        ) : (
          <>
            <div className="text-sm text-muted-foreground">
              {result.type === 'collection' ? '合集' : '视频'}：{result.title || '-'}
              {result.owner?.name ? ` · ${result.owner.name}` : ''}
              <span className="ml-2">共 {flatParts.length} 个分P</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
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
              <span className="text-sm text-muted-foreground">已选 {selectedCount}</span>
            </div>

            <ScrollArea className="h-[420px] rounded-md border p-2">
              {result.videos.map(video => (
                <div key={video.bvid} className="mb-3">
                  <div className="mb-1 text-sm font-medium">
                    {video.title || video.bvid}
                    <span className="ml-2 text-xs text-muted-foreground">{video.bvid}</span>
                  </div>
                  {video.error && (
                    <div className="pl-6 text-xs text-red-500">{video.error}</div>
                  )}
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
                        <span className="text-xs text-muted-foreground">
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
            disabled={submitting || selectedCount === 0}
          >
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            确定生成（{selectedCount}）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
