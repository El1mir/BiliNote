import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

const normalizeTaskStatus = (payload: any) => {
  const raw = payload?.data && payload?.status === undefined ? payload.data : payload
  const progress = raw?.progress ?? {}
  return {
    ...raw,
    result: raw?.result || payload?.result,
    stage: raw?.stage ?? progress?.stage ?? null,
    stageLabel: raw?.stage_label ?? raw?.stageLabel ?? progress?.stage_label ?? progress?.stageLabel ?? null,
    progress: raw?.progress_value ?? (typeof raw?.progress === 'number' ? raw.progress : progress?.progress ?? null),
    stageProgress: raw?.stage_progress ?? raw?.stageProgress ?? progress?.stage_progress ?? progress?.stageProgress ?? null,
    message: raw?.message ?? progress?.message ?? null,
    detail: raw?.detail ?? progress?.detail ?? null,
    updatedAt: raw?.updated_at ?? raw?.updatedAt ?? progress?.updated_at ?? progress?.updatedAt ?? null,
  }
}


const hasMarkdownContent = (task: any) =>
  Array.isArray(task?.markdown) ? task.markdown.length > 0 : Boolean(task?.markdown)

export const useTaskPolling = (interval = 3000) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const updateTaskStatus = useTaskStore(state => state.updateTaskStatus)
  const removeTask = useTaskStore(state => state.removeTask)

  const tasksRef = useRef(tasks)
  // 每个任务的连续轮询失败次数。偶发超时/网络抖动不应该把任务判死。
  const failuresRef = useRef<Record<string, number>>({})
  const MAX_POLL_FAILURES = 5

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    const timer = setInterval(async () => {
      const pendingTasks = tasksRef.current.filter(
        task =>
          (task.status != 'SUCCESS' && task.status != 'FAILED') ||
          // 兼容旧 bug：已经 SUCCESS 但没有 markdown 内容，补拉一次结果。
          (task.status === 'SUCCESS' && !hasMarkdownContent(task)),
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      for (const task of pendingTasks) {
        try {
          const res = normalizeTaskStatus(await get_task_status(task.id))
          const { status } = res
          failuresRef.current[task.id] = 0

          if (status || res.stage) {
              const progressData = {
                status: status || task.status,
                stage: res.stage,
                stageLabel: res.stageLabel,
                progress: res.progress,
                stageProgress: res.stageProgress,
                message: res.message,
                detail: res.detail,
                updatedAt: res.updatedAt,
              }
              if (status === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = res.result || {}
                if (task.status !== 'SUCCESS') toast.success('笔记生成成功')
              updateTaskContent(task.id, {
                ...progressData,
                markdown,
                transcript,
                audioMeta: audio_meta,
              })
            } else if (status === 'FAILED') {
              updateTaskContent(task.id, progressData)
              console.warn(`任务 ${task.id} 失败`)
            } else {
              updateTaskContent(task.id, progressData)
            }
          }
        } catch (e) {
          const failures = (failuresRef.current[task.id] || 0) + 1
          failuresRef.current[task.id] = failures
          console.warn(`任务 ${task.id} 轮询失败（第 ${failures}/${MAX_POLL_FAILURES} 次）`, e)
          // 只有连续多次都拿不到状态才判定失败：单次超时/抖动时任务其实还在跑，
          // 误判会让界面出现「重试」，点下去就会重复提交同一个任务。
          if (failures >= MAX_POLL_FAILURES) {
            updateTaskContent(task.id, { status: 'FAILED' })
            toast.error('多次获取任务状态失败，已标记为失败，可稍后重试')
          }
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval])
}
