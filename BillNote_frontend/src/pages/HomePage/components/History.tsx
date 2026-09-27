import NoteHistory from '@/pages/HomePage/components/NoteHistory.tsx'
import { useTaskStore } from '@/store/taskStore'
import { Clock, Download } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { Button } from '@/components/ui/button.tsx'
import { useState } from 'react'
import { downloadNoteArchives } from '@/services/note'
import toast from 'react-hot-toast'

const History = () => {
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const tasks = useTaskStore(state => state.tasks)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [downloading, setDownloading] = useState(false)
  const completedIds = tasks.filter(task => task.status === 'SUCCESS').map(task => task.id)

  const downloadSelected = async () => {
    if (!selectedIds.length) return
    setDownloading(true)
    try {
      const blob = await downloadNoteArchives(selectedIds)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'notes.zip'
      link.click()
      URL.revokeObjectURL(url)
      toast.success(`已下载 ${selectedIds.length} 篇笔记`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量归档下载失败')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex h-full w-full flex-col gap-4 px-2.5 py-1.5">
      <div className="my-4 flex min-h-[40px] items-center gap-2">
        <Clock className="h-4 w-4 text-neutral-500" />
        <h2 className="text-base font-medium text-neutral-900">生成历史</h2>
        <Button type="button" size="sm" variant="outline" className="ml-auto" disabled={!selectedIds.length || downloading} onClick={downloadSelected}>
          <Download className="mr-1 h-4 w-4" />
          {downloading ? '打包中…' : `下载选中${selectedIds.length ? ` (${selectedIds.length})` : ''}`}
        </Button>
      </div>
      <label className="flex items-center gap-2 text-xs text-neutral-500">
        <input type="checkbox" checked={completedIds.length > 0 && completedIds.every(id => selectedIds.includes(id))} onChange={event => setSelectedIds(event.target.checked ? completedIds : [])} />
        全选已完成笔记
      </label>
      <ScrollArea className="w-full sm:h-[480px] md:h-[720px] lg:h-[92%]">
        <NoteHistory onSelect={setCurrentTask} selectedId={currentTaskId} selectedIds={selectedIds} onSelectionChange={setSelectedIds} />
      </ScrollArea>
    </div>
  )
}

export default History
