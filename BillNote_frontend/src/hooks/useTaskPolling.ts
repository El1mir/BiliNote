import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

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
        task => task.status != 'SUCCESS' && task.status != 'FAILED'
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      for (const task of pendingTasks) {
        try {
          const res = await get_task_status(task.id)
          const { status } = res
          failuresRef.current[task.id] = 0

          if (status && status !== task.status) {
            if (status === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = res.result
              toast.success('笔记生成成功')
              updateTaskContent(task.id, {
                status,
                markdown,
                transcript,
                audioMeta: audio_meta,
              })
            } else if (status === 'FAILED') {
              updateTaskContent(task.id, { status })
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              updateTaskContent(task.id, { status })
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
