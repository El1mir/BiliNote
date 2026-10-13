import { FC, useMemo, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  FolderPlus,
  Download,
  Pencil,
  Trash2,
  X,
  Check,
} from 'lucide-react'
import { Button } from '@/components/ui/button.tsx'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import { cn } from '@/lib/utils.ts'
import { UNGROUPED_ID, type NoteGroup } from '@/services/noteGroup.ts'

/** 分组侧栏的展示模型：「未分组」虚拟区也是其中一行，id 用 UNGROUPED_ID 占位。 */
export interface GroupRow {
  id: string
  name: string
  count: number
}

interface GroupPanelProps {
  groups: NoteGroup[]
  ungroupedCount: number
  loading: boolean
  maxGroups: number
  maxNameLength: number
  /** 当前「聚焦」的分组：null = 展示全部任务，否则只展示该组（UNGROUPED_ID 表示未分组）。 */
  activeGroupId: string | null
  /** 勾选用于「下载选中分组」的分组行；「未分组」也可勾。 */
  selectedGroupIds: string[]
  downloading: boolean
  creating: boolean
  /** 拖拽悬停到某个分组行时的高亮目标。 */
  dropTargetId: string | null
  onSelect: (groupId: string | null) => void
  onToggleChecked: (groupId: string) => void
  onCheckAll: (checked: boolean) => void
  onCreate: (name: string) => void
  onRename: (groupId: string, name: string) => void
  onDelete: (group: NoteGroup) => void
  onDownload: () => void
  onDragOverGroup: (groupId: string) => void
  onDragLeaveGroup: (groupId: string) => void
  onDropOnGroup: (groupId: string) => void
  /** 展开/收起的分组 id 集合，收起后组内任务不渲染。 */
  collapsed: string[]
  onToggleCollapsed: (groupId: string) => void
}

const GroupPanel: FC<GroupPanelProps> = ({
  groups,
  ungroupedCount,
  loading,
  maxGroups,
  maxNameLength,
  activeGroupId,
  selectedGroupIds,
  downloading,
  creating,
  dropTargetId,
  onSelect,
  onToggleChecked,
  onCheckAll,
  onCreate,
  onRename,
  onDelete,
  onDownload,
  onDragOverGroup,
  onDragLeaveGroup,
  onDropOnGroup,
  collapsed,
  onToggleCollapsed,
}) => {
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')

  const rows: GroupRow[] = useMemo(
    () => [
      ...groups.map(group => ({
        id: group.id,
        name: group.name,
        count: group.task_count ?? 0,
      })),
      { id: UNGROUPED_ID, name: '未分组', count: ungroupedCount },
    ],
    [groups, ungroupedCount]
  )

  const allChecked = rows.length > 0 && rows.every(row => selectedGroupIds.includes(row.id))
  const atLimit = maxGroups > 0 && groups.length >= maxGroups

  const submitCreate = () => {
    const name = newName.trim()
    if (!name) return
    // 名称长度先在前端拦一道（输入框已带 maxLength，这里防粘贴绕过）。
    if (name.length > maxNameLength) {
      onCreate(name)
      return
    }
    onCreate(name)
    setNewName('')
  }

  const submitRename = (groupId: string) => {
    const name = editingName.trim()
    setEditingId(null)
    if (!name) return
    onRename(groupId, name)
  }

  return (
    <div className="flex flex-col gap-2 border-b border-slate-200 px-2.5 pb-3">
      <div className="flex items-center gap-2 pt-2">
        <span className="text-sm font-medium text-neutral-900">笔记分组</span>
        <span className="text-[10px] text-neutral-400">
          {groups.length}/{maxGroups}
        </span>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={downloading || !selectedGroupIds.length}
                onClick={onDownload}
              >
                <Download className="mr-1 h-4 w-4" />
                {downloading
                  ? '打包中…'
                  : `下载选中分组${selectedGroupIds.length ? ` (${selectedGroupIds.length})` : ''}`}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>下载所选分组内全部「已完成」的笔记</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* 新建分组：名称长度由 maxLength 与后端 max_name_length 双重把关 */}
      <div className="flex items-center gap-1">
        <input
          type="text"
          value={newName}
          maxLength={maxNameLength}
          disabled={atLimit}
          placeholder={
            atLimit ? `已达上限 ${maxGroups} 个分组` : `新建分组…（最多 ${maxNameLength} 字）`
          }
          onChange={event => setNewName(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') submitCreate()
          }}
          className="focus:border-primary min-w-0 flex-1 rounded border border-neutral-300 px-2 py-1 text-xs outline-none disabled:bg-neutral-100"
        />
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={creating || atLimit || !newName.trim()}
                onClick={submitCreate}
              >
                <FolderPlus className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>新建分组</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2 text-xs text-neutral-500">
          <input
            type="checkbox"
            checked={allChecked}
            onChange={event => onCheckAll(event.target.checked)}
          />
          全选分组
        </label>
        <button
          type="button"
          className="text-primary ml-auto cursor-pointer text-xs hover:underline"
          onClick={() => onSelect(null)}
        >
          显示全部
        </button>
      </div>

      {loading && !groups.length ? (
        <div className="py-2 text-center text-xs text-neutral-400">分组加载中…</div>
      ) : (
        <div className="flex flex-col gap-1">
          {rows.map(row => {
            const isUngrouped = row.id === UNGROUPED_ID
            const active = activeGroupId === row.id
            const isCollapsed = collapsed.includes(row.id)
            const isDropTarget = dropTargetId === row.id
            const editing = editingId === row.id
            return (
              <div
                key={row.id}
                onClick={() => onSelect(row.id)}
                onDragOver={event => {
                  // 不 preventDefault 的话 drop 根本不会触发。
                  event.preventDefault()
                  event.dataTransfer.dropEffect = 'move'
                  onDragOverGroup(row.id)
                }}
                onDragLeave={() => onDragLeaveGroup(row.id)}
                onDrop={event => {
                  event.preventDefault()
                  onDropOnGroup(row.id)
                }}
                className={cn(
                  'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs',
                  active
                    ? 'border-primary bg-primary-light text-neutral-900'
                    : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
                  isDropTarget && 'border-primary bg-primary-light ring-primary ring-1'
                )}
              >
                <button
                  type="button"
                  className="cursor-pointer text-neutral-400"
                  onClick={event => {
                    event.stopPropagation()
                    onToggleCollapsed(row.id)
                  }}
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" />
                  )}
                </button>

                <input
                  type="checkbox"
                  checked={selectedGroupIds.includes(row.id)}
                  onClick={event => event.stopPropagation()}
                  onChange={() => onToggleChecked(row.id)}
                />

                {editing ? (
                  <input
                    autoFocus
                    type="text"
                    value={editingName}
                    maxLength={maxNameLength}
                    onClick={event => event.stopPropagation()}
                    onChange={event => setEditingName(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === 'Enter') submitRename(row.id)
                      if (event.key === 'Escape') setEditingId(null)
                    }}
                    className="focus:border-primary min-w-0 flex-1 rounded border border-neutral-300 px-1 py-0.5 text-xs outline-none"
                  />
                ) : (
                  <span className="min-w-0 flex-1 truncate" title={row.name}>
                    {row.name}
                  </span>
                )}

                <span className="shrink-0 text-[10px] text-neutral-400">{row.count}</span>

                {editing ? (
                  <>
                    <button
                      type="button"
                      className="text-primary shrink-0 cursor-pointer"
                      onClick={event => {
                        event.stopPropagation()
                        submitRename(row.id)
                      }}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      className="shrink-0 cursor-pointer text-neutral-400"
                      onClick={event => {
                        event.stopPropagation()
                        setEditingId(null)
                      }}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  !isUngrouped && (
                    <>
                      <button
                        type="button"
                        title="重命名"
                        className="text-muted-foreground hover:text-primary shrink-0 cursor-pointer"
                        onClick={event => {
                          event.stopPropagation()
                          setEditingId(row.id)
                          setEditingName(row.name)
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        title="删除分组"
                        className="text-muted-foreground hover:text-destructive shrink-0 cursor-pointer"
                        onClick={event => {
                          event.stopPropagation()
                          onDelete(groups.find(group => group.id === row.id)!)
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default GroupPanel
