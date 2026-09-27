import request from '@/utils/request'
import toast from 'react-hot-toast'

const API_BASE = String(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export const downloadNoteArchive = async (taskId: string): Promise<Blob> => {
  const base = API_BASE.endsWith('/api') ? API_BASE : `${API_BASE}/api`
  const response = await fetch(`${base}/task_archive/${encodeURIComponent(taskId)}`)
  if (!response.ok) {
    let message = '笔记归档下载失败'
    try {
      const payload = await response.json()
      message = payload?.msg || message
    } catch {
      // Keep a readable fallback for non-JSON proxy errors.
    }
    throw new Error(message)
  }
  return response.blob()
}

export const downloadNoteArchives = async (taskIds: string[]): Promise<Blob> => {
  const base = API_BASE.endsWith('/api') ? API_BASE : `${API_BASE}/api`
  const response = await fetch(`${base}/task_archives`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_ids: taskIds }),
  })
  if (!response.ok) {
    let message = '批量归档下载失败'
    try {
      const payload = await response.json()
      message = payload?.msg || message
    } catch {
      // Keep a readable fallback for non-JSON proxy errors.
    }
    throw new Error(message)
  }
  return response.blob()
}
export const generateNote = async (data: {
  video_url: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  task_id?: string
  format: Array<string>
  style: string
  extras?: string
  video_understand?: boolean
  video_interval?: number
  grid_size: Array<number>
  sampling_mode?: string
  max_frames?: number
  frames_per_second?: number
  frame_limit_mode?: string
}) => {
  try {
    console.log('generateNote', data)
    const response = await request.post('/generate_note', data)

    if (!response) {
      if (response.data.msg) {
        toast.error(response.data.msg)
      }
      return null
    }
    toast.success('笔记生成任务已提交！')

    console.log('res', response)
    // 成功提示

    return response
  } catch (e: any) {
    console.error('❌ 请求出错', e)

    // 错误提示
    // toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

export const delete_task = async ({ video_id, platform }) => {
  try {
    const data = {
      video_id,
      platform,
    }
    const res = await request.post('/delete_task', data)


      toast.success('任务已成功删除')
      return res
  } catch (e) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string) => {
  try {
    // 轮询接口：失败交给 useTaskPolling 做「连续失败」判断，
    // 不在这里弹 toast（3 秒轮一次，弹一次就误导用户以为任务失败了）。
    return await request.get('/task_status/' + task_id, { suppressToast: true })
  } catch (e) {
    console.error('❌ 获取任务状态失败', e)
    throw e // 抛出错误以便调用方处理
  }
}

// ---------------- 批量导入（B 站合集 / 多P） ----------------

export interface ExpandPart {
  p: number
  title: string
  duration: number
  video_id: string
  url: string
  already_generated: boolean
}

export interface ExpandVideo {
  bvid: string
  title: string
  duration: number
  cover: string
  error?: string | null
  parts: ExpandPart[]
}

export interface ExpandResult {
  platform: string
  type: 'video' | 'collection'
  title: string
  cover: string
  owner?: { mid: string; name: string }
  videos: ExpandVideo[]
}

export interface BatchGenerateItem {
  bvid: string
  p: number
  video_id: string
  url: string
}

export interface BatchGenerateResult {
  video_id: string
  task_id?: string
  status: 'queued' | 'skipped' | 'failed'
  reason?: string
}

export interface BatchGeneratePayload {
  platform: string
  items: BatchGenerateItem[]
  quality: string
  model_name: string
  provider_id: string
  format?: Array<string>
  style?: string
  extras?: string
  screenshot?: boolean
  link?: boolean
  video_understanding?: boolean
  video_interval?: number
  grid_size?: Array<number>
  sampling_mode?: string
  /** smart 采样：单个视频最多抽多少帧（批量时每个视频各自的上限） */
  max_frames?: number
  /** smart 采样：每秒最多保留多少帧 */
  frames_per_second?: number
  /** smart 限制方式二选一：'total'=只用 max_frames；'per_second'=只用 frames_per_second */
  frame_limit_mode?: string
}

/** 展开合集 / 多P 链接，返回可勾选的视频+分P 列表。 */
export const expandUrl = async (url: string): Promise<ExpandResult> => {
  return await request.post('/expand', { url })
}

/** 提交勾选后的批量生成请求。 */
export const generateNotes = async (
  payload: BatchGeneratePayload,
): Promise<{ results: BatchGenerateResult[] }> => {
  return await request.post('/generate_notes', payload)
}
