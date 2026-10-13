import { FC, useEffect, useState } from 'react'
import HomeLayout from '@/layouts/HomeLayout.tsx'
import NoteForm from '@/pages/HomePage/components/NoteForm.tsx'
import MarkdownViewer from '@/pages/HomePage/components/MarkdownViewer.tsx'
import { useTaskStore } from '@/store/taskStore'
import History from '@/pages/HomePage/components/History.tsx'

type ViewStatus = 'idle' | 'loading' | 'success' | 'failed'

/**
 * StrictMode 下 React 18/19 会「挂载 → 卸载 → 再挂载」，effect 跑两次；
 * 任务列表重载是幂等的网络请求，但还是按住这个开关只打一次，省掉一次无谓请求。
 */
let hasLoadedTasks = false

export const HomePage: FC = () => {
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)

  // 前端不再做任何本地存储（用户决策 m04951）：刷新页面后 tasks 是空的，
  // 这里从后端 `GET /api/task_list` 把列表重建回来（store 内部只合并不覆盖，
  // 不会打断 useTaskPolling 正在更新的活跃任务）。
  useEffect(() => {
    if (hasLoadedTasks) return
    hasLoadedTasks = true
    void useTaskStore.getState().loadTasks()
  }, [])

  const currentTask = tasks.find(t => t.id === currentTaskId)

  const [status, setStatus] = useState<ViewStatus>('idle')

  const content = currentTask?.markdown || ''

  useEffect(() => {
    if (!currentTask) {
      setStatus('idle')
    } else if (currentTask.status === 'SUCCESS') {
      setStatus('success')
    } else if (currentTask.status === 'FAILED') {
      setStatus('failed')
    } else {
      // PENDING、PARSING、DOWNLOADING、TRANSCRIBING、SUMMARIZING 等所有进行中状态
      setStatus('loading')
    }
  }, [currentTask, currentTask?.status])

  // useEffect( () => {
  //     get_task_status('d4e87938-c066-48a0-bbd5-9bec40d53354').then(res=>{
  //         console.log('res1',res)
  //         setContent(res.data.result.markdown)
  //     })
  // }, [tasks]);
  return (
    <HomeLayout
      NoteForm={<NoteForm />}
      Preview={<MarkdownViewer status={status} />}
      History={<History />}
    />
  )
}
