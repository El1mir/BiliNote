import { useEffect, useState } from 'react'
import { Check, CircleAlert, Loader2, Sparkles } from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { asText } from '@/utils/text'
import { toPercent } from '@/utils/progress'

/** 超过该时长没有状态更新 → 显示「后端仍在处理」的弱提示（spec 005 ticket 16）。 */
const STALE_AFTER_MS = 60_000

/** 毫秒 → 「X 小时 Y 分」/「Y 分 Z 秒」/「Z 秒」 */
const formatDuration = (ms: number): string => {
  if (!Number.isFinite(ms) || ms < 0) return ''
  const total = Math.floor(ms / 1000)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  if (hours > 0) return `${hours} 小时 ${minutes} 分`
  if (minutes > 0) return `${minutes} 分 ${seconds} 秒`
  return `${seconds} 秒`
}

/** 毫秒差 → 「刚刚 / X 秒前 / X 分钟前 / X 小时前 / X 天前」 */
const formatRelative = (ms: number): string => {
  if (!Number.isFinite(ms)) return ''
  const total = Math.max(0, Math.floor(ms / 1000))
  if (total < 5) return '刚刚'
  if (total < 60) return `${total} 秒前`
  const minutes = Math.floor(total / 60)
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

/** 每秒推进一次「现在」；终态或页面不可见时不刷新，避免无意义重渲染。 */
const useNow = (active: boolean): number => {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return
      setNow(Date.now())
    }, 1000)
    return () => clearInterval(timer)
  }, [active])
  return now
}

const stages = [
  { key: 'queued', label: '排队中' },
  { key: 'parsing', label: '解析链接' },
  { key: 'fetching_subtitles', label: '获取字幕' },
  { key: 'downloading_video', label: '下载视频' },
  { key: 'downloading_audio', label: '准备音频' },
  { key: 'transcribing', label: '转写内容' },
  { key: 'planning_frames', label: '规划画面' },
  { key: 'extracting_frames', label: '抽取画面' },
  { key: 'building_grids', label: '拼接画面' },
  { key: 'summarizing', label: '生成总结' },
  { key: 'post_processing', label: '整理结果' },
  { key: 'saving', label: '保存笔记' },
]

interface Props { task: Task }

export default function ProgressTimeline({ task }: Props) {
  const current = asText(task.stage) || (task.status === 'SUCCESS' ? 'success' : task.status === 'FAILED' ? 'failed' : 'queued')
  const index = stages.findIndex(stage => stage.key === current)
  const terminal = current === 'success' || current === 'failed' || task.status === 'SUCCESS' || task.status === 'FAILED'
  const percent = toPercent(task.progress)
  const stagePercent = toPercent(task.stageProgress)

  const now = useNow(!terminal)
  const createdMs = task.createdAt ? new Date(task.createdAt).getTime() : NaN
  const updatedMs = task.updatedAt ? new Date(task.updatedAt).getTime() : NaN
  // 终态后计时器停下，用最后一次状态更新的时刻当结束点，避免「总耗时」一直涨
  const endMs = terminal && Number.isFinite(updatedMs) ? updatedMs : now
  const elapsed = Number.isFinite(createdMs) ? formatDuration(endMs - createdMs) : ''
  const sinceUpdate = Number.isFinite(updatedMs) ? now - updatedMs : null
  const stale = !terminal && sinceUpdate !== null && sinceUpdate >= STALE_AFTER_MS

  return (
    <section className="progress-panel animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="progress-panel__header">
        <div>
          <div className="eyebrow"><Sparkles className="h-3.5 w-3.5" />任务进度</div>
          <h2>{asText(task.stageLabel) || (task.status === 'SUCCESS' ? '笔记已完成' : task.status === 'FAILED' ? '生成失败' : '正在生成笔记')}</h2>
          <p>{asText(task.message) || asText(task.detail) || '正在处理，请稍候'}</p>
        </div>
        {percent !== null && <strong className="progress-percent">{percent}%</strong>}
      </div>
      <div className="progress-track"><span style={{ width: `${percent ?? 38}%` }} className={percent === null ? 'is-indeterminate' : ''} /></div>
      <div className="progress-meta">
        <span>{stagePercent !== null ? `当前阶段进度 ${stagePercent}%` : '后端将按实际处理阶段更新状态'}</span>
        <span>
          {elapsed && `${terminal ? '总耗时' : '已用时'} ${elapsed}`}
          {elapsed && sinceUpdate !== null && ' · '}
          {sinceUpdate !== null && `最后更新 ${formatRelative(sinceUpdate)}`}
        </span>
      </div>
      {stale && (
        <div className="progress-stale">
          <CircleAlert className="h-3.5 w-3.5" />
          后端仍在处理，已超过 {Math.round(STALE_AFTER_MS / 1000)} 秒没有状态更新；长音频 / 长视频属正常，可先观察，不必重复提交
        </div>
      )}
      <div className="timeline" aria-label="任务处理阶段">
        {stages.map((stage, stageIndex) => {
          const complete = index >= 0 && stageIndex < index
          const active = stage.key === current
          return <div key={stage.key} className={`timeline-item ${complete ? 'is-complete' : ''} ${active ? 'is-active' : ''}`}>
            <div className="timeline-dot">{complete ? <Check className="h-3.5 w-3.5" /> : active && !terminal ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span />}</div>
            <span>{stage.label}</span>
          </div>
        })}
        {(current === 'failed' || task.status === 'FAILED') && <div className="timeline-item is-error"><div className="timeline-dot"><CircleAlert className="h-3.5 w-3.5" /></div><span>任务失败</span></div>}
      </div>
    </section>
  )
}
