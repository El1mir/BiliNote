import { useEffect, useRef } from 'react'
import { useTaskStore, readLatestMarkdown, type Task } from '@/store/taskStore'
import { getTaskStatusBatch, readTaskStatusMap, type TaskStatusLite } from '@/services/note.ts'
import toast from 'react-hot-toast'

/**
 * `POST /api/task_status/batch` 返回的每条轻量状态（见 `TaskStatusLite`）。
 * 后端可能用下划线命名也可能用驼峰，这里统一收敛。
 * 注意：轻量端点**不含** markdown 与 transcript —— 任务成功那一刻才用
 * `rehydrateTask` 单条拉完整结果（spec 009 ticket 06 第 3 条）。
 */
const normalizeTaskStatus = (lite: TaskStatusLite) => ({
  status: lite.status,
  stage: lite.stage ?? null,
  stageLabel: lite.stage_label ?? lite.stageLabel ?? null,
  progress: lite.progress ?? null,
  stageProgress: lite.stage_progress ?? lite.stageProgress ?? null,
  message: lite.message ?? null,
  detail: lite.detail ?? null,
  updatedAt: lite.updated_at ?? lite.updatedAt ?? null,
})

const hasMarkdownContent = (task: Task | undefined) => Boolean(readLatestMarkdown(task?.markdown))

/**
 * 单次批量状态请求最多带多少个 task_id。
 * 后端上限是 1000（`backend/app/routers/note.py` 的 `BatchStatusRequest` 检查），
 * 这里取 500 留出余量：分片只在待办超过 500 个时才会发生，
 * 常规批量（几十到 200 个）仍然是每轮 1 个请求。
 */
const BATCH_STATUS_CHUNK = 500

export const useTaskPolling = (interval = 3000) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskStatus = useTaskStore(state => state.updateTaskStatus)
  const rehydrateTask = useTaskStore(state => state.rehydrateTask)

  const tasksRef = useRef(tasks)
  /**
   * 连续轮询失败次数。**按轮**计数而不是按任务：改成一次批量请求之后，
   * 一轮里所有任务的成败是同一件事，没必要各自记一遍。
   * 偶发超时/网络抖动不应该把任务判死（spec 009 ticket 06）。
   */
  const failuresRef = useRef(0)
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
          (task.status === 'SUCCESS' && !hasMarkdownContent(task))
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      // 每轮只发一个状态请求（spec 009 ticket 06 验收：200 个待办也是 1 个请求）。
      // 后端对单个请求有 1000 个 id 的上限（note.py 的 BatchStatusRequest 检查），
      // 超过 BATCH_STATUS_CHUNK 就分片 —— 只有待办特别多时才会多发请求，
      // 平时仍是 1 个；不能因为超限就让整轮轮询一直报错。
      const statuses: Record<string, TaskStatusLite | null> = {}
      try {
        for (let i = 0; i < pendingTasks.length; i += BATCH_STATUS_CHUNK) {
          const chunk = pendingTasks.slice(i, i + BATCH_STATUS_CHUNK)
          const payload = await getTaskStatusBatch(chunk.map(task => task.id))
          // 后端返回的键名可能是 states 或 statuses，readTaskStatusMap 两个都认。
          Object.assign(statuses, readTaskStatusMap(payload))
        }
        failuresRef.current = 0
      } catch (e) {
        failuresRef.current += 1
        console.warn(`批量轮询失败（第 ${failuresRef.current}/${MAX_POLL_FAILURES} 轮）`, e)
        // 单轮失败**绝不**改任务状态：任务其实还在跑，误标 FAILED 会让界面出现
        // 「重试」，点下去就重复提交同一个任务。只在连续失败到阈值时提示一次。
        if (failuresRef.current === MAX_POLL_FAILURES) {
          toast.error('连续多次获取任务状态失败，请检查后端服务；任务状态未改动，恢复后会自动继续')
        }
        return
      }

      // 本轮新成功的任务数，用于把 N 条成功提示合并成一条（否则 200 个任务弹 200 次）。
      let newlySucceeded = 0

      for (const task of pendingTasks) {
        const lite = statuses[task.id]
        // 未知 id / 后端没有这条记录：保持原状态，不猜。
        if (!lite) continue

        const res = normalizeTaskStatus(lite)
        const status = res.status as Task['status'] | undefined
        if (!status && !res.stage) continue

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
          if (task.status !== 'SUCCESS') newlySucceeded += 1
          updateTaskStatus(task.id, progressData)
          // 轻量端点不带 markdown / transcript，成功那一刻再单条拉完整结果。
          // rehydrateTask 自己吞异常并只 console.warn，不会打断这一轮。
          if (!hasMarkdownContent(task)) void rehydrateTask(task.id)
        } else if (status === 'FAILED') {
          updateTaskStatus(task.id, progressData)
          console.warn(`任务 ${task.id} 失败`)
        } else {
          updateTaskStatus(task.id, progressData)
        }
      }

      if (newlySucceeded > 0) {
        toast.success(newlySucceeded === 1 ? '笔记生成成功' : `已完成 ${newlySucceeded} 个任务`)
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval, updateTaskStatus, rehydrateTask])
}
