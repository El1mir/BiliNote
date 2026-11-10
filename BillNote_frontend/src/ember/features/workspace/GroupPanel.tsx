import { useState, type DragEvent, type FormEvent } from 'react'
import { Check, Download, FolderPlus, Pencil, Trash2, X } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { Checkbox } from '@/ember/ui/Checkbox'
import { Dialog } from '@/ember/ui/Dialog'
import { Input } from '@/ember/ui/Input'
import { cn } from '@/ember/lib/cn'
import { UNGROUPED_ID } from '@/services/noteGroup'
import type { useNoteGroups } from '@/ember/features/workspace/useNoteGroups'

type GroupPanelProps = {
  /** The single hook instance owned by the workspace page, shared with the task list. */
  state: ReturnType<typeof useNoteGroups>
  /** Every task in the store, so the "all notes" row has a number too. */
  totalCount: number
}

const ROW =
  'flex w-full items-center gap-1.5 rounded-control px-1.5 py-1 text-left transition-colors ease-[var(--ease)] duration-[var(--dur-hover)]'

/**
 * Note groups above the history list. Rows act as filters (click) and as drop
 * targets (drag a task card here), which keeps a 340px rail from growing a nested
 * tree that would hide most of the history.
 */
export function GroupPanel({ state, totalCount }: GroupPanelProps) {
  const { t } = useI18n()
  const {
    groups,
    ungroupedCount,
    maxGroups,
    maxNameLength,
    busy,
    activeGroupId,
    setActiveGroupId,
    checkedGroupIds,
    toggleGroupChecked,
    setAllChecked,
    downloadCheckedGroups,
    downloading,
    createGroup,
    renameGroup,
    removeGroup,
    moveTasks,
    draggingIds,
    setDraggingIds,
    dropTargetId,
    setDropTargetId,
  } = state

  const [draft, setDraft] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [pendingDelete, setPendingDelete] = useState<{
    id: string
    name: string
    count: number
  } | null>(null)
  const [deleteTasks, setDeleteTasks] = useState(false)

  const atLimit = groups.length >= maxGroups
  const checkable = groups.length + 1
  const allChecked = checkedGroupIds.length === checkable

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (atLimit || !draft.trim()) return
    if (await createGroup(draft)) setDraft('')
  }

  const startRename = (id: string, name: string) => {
    setRenamingId(id)
    setRenameDraft(name)
  }

  const submitRename = async (event: FormEvent, id: string) => {
    event.preventDefault()
    if (await renameGroup(id, renameDraft)) setRenamingId(null)
  }

  /** Task ids travel in the drag payload too, so a drop still works if state lags. */
  const onDrop = (event: DragEvent<HTMLDivElement>, target: string) => {
    event.preventDefault()
    const payload = event.dataTransfer.getData('text/plain')
    const ids = draggingIds.length ? draggingIds : payload.split(',').filter(Boolean)
    setDropTargetId(null)
    setDraggingIds([])
    if (ids.length) void moveTasks(ids, target)
  }

  const dropProps = (target: string) => ({
    onDragOver: (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
      setDropTargetId(target)
    },
    onDragLeave: () => setDropTargetId(current => (current === target ? null : current)),
    onDrop: (event: DragEvent<HTMLDivElement>) => onDrop(event, target),
  })

  return (
    <section
      aria-label={t('group.title')}
      className="rounded-surface border-line bg-canvas flex shrink-0 flex-col gap-2 border p-2.5"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-small text-ink flex items-baseline gap-1.5 font-semibold">
          {t('group.title')}
          <span className="text-caption text-ink-mute font-normal tabular-nums">
            {groups.length}/{maxGroups}
          </span>
        </h3>
        <Button
          size="sm"
          variant="ghost"
          className="text-caption h-7 gap-1 px-2"
          disabled={!checkedGroupIds.length}
          loading={downloading}
          onClick={() => void downloadCheckedGroups()}
          title={t('group.download')}
          aria-label={t('group.download')}
        >
          <Download className="size-3.5" />
          {checkedGroupIds.length ? checkedGroupIds.length : null}
        </Button>
      </div>

      <form onSubmit={submitCreate} className="flex items-center gap-1.5">
        <Input
          value={draft}
          onChange={event => setDraft(event.target.value)}
          maxLength={maxNameLength}
          disabled={atLimit || busy}
          placeholder={
            atLimit ? t('group.limit', { count: maxGroups }) : t('group.namePlaceholder')
          }
          aria-label={t('history.group.new')}
          className="text-small h-8 px-2.5"
        />
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          className="h-8 px-2"
          disabled={atLimit || !draft.trim()}
          aria-label={t('group.create')}
        >
          <FolderPlus className="size-3.5" />
        </Button>
      </form>

      {/* spec 020：分组多时这块必须能滚，且高度跟着视口走 ——
          固定 264px 在 900px 高的窗口里会把最后一行切一半，看起来像「不能滚」。 */}
      <div className="-mx-1 flex max-h-[min(45vh,420px)] flex-col gap-0.5 overflow-y-auto overscroll-contain px-1">
        <button
          type="button"
          onClick={() => setActiveGroupId(null)}
          aria-pressed={activeGroupId === null}
          className={cn(
            ROW,
            activeGroupId === null ? 'bg-primary-soft text-ink' : 'text-ink-soft hover:bg-surface'
          )}
        >
          <span className="text-small flex-1 truncate font-semibold">{t('group.all')}</span>
          <span className="text-caption text-ink-mute shrink-0 tabular-nums">{totalCount}</span>
        </button>

        {groups.map(group => {
          const active = activeGroupId === group.id
          const dropping = dropTargetId === group.id
          return (
            <div
              key={group.id}
              {...dropProps(group.id)}
              className={cn(
                'group/row rounded-control flex items-center gap-1.5 px-1 py-0.5 transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]',
                active && 'bg-primary-soft',
                dropping && 'bg-primary-soft ring-primary/50 ring-1'
              )}
            >
              <Checkbox
                checked={checkedGroupIds.includes(group.id)}
                onChange={() => toggleGroupChecked(group.id)}
                label={group.name}
              />
              {renamingId === group.id ? (
                <form
                  onSubmit={event => void submitRename(event, group.id)}
                  className="flex min-w-0 flex-1 items-center gap-1"
                >
                  <Input
                    autoFocus
                    value={renameDraft}
                    onChange={event => setRenameDraft(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === 'Escape') {
                        event.preventDefault()
                        setRenamingId(null)
                      }
                    }}
                    maxLength={maxNameLength}
                    aria-label={t('history.group.rename')}
                    className="text-small h-7 px-2"
                  />
                  <Button
                    type="submit"
                    size="sm"
                    variant="ghost"
                    className="h-7 px-1.5"
                    aria-label={t('common.save')}
                  >
                    <Check className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 px-1.5"
                    aria-label={t('common.cancel')}
                    onClick={() => setRenamingId(null)}
                  >
                    <X className="size-3.5" />
                  </Button>
                </form>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setActiveGroupId(active ? null : group.id)}
                    aria-pressed={active}
                    className={cn(
                      'rounded-control flex min-w-0 flex-1 items-center gap-1.5 px-1 py-0.5 text-left',
                      active ? 'text-ink' : 'text-ink-soft hover:text-ink'
                    )}
                  >
                    <span className="text-small truncate font-semibold">{group.name}</span>
                    <span className="text-caption text-ink-mute ml-auto shrink-0 tabular-nums">
                      {group.task_count ?? 0}
                    </span>
                  </button>
                  <div
                    className={cn(
                      'flex shrink-0 items-center gap-0.5 transition-opacity duration-[var(--dur-hover)] ease-[var(--ease)]',
                      'group-hover/row:opacity-100 focus-within:opacity-100',
                      active ? 'opacity-100' : 'opacity-0'
                    )}
                  >
                    <button
                      type="button"
                      aria-label={t('history.group.rename')}
                      onClick={() => startRename(group.id, group.name)}
                      className="ember-press rounded-control text-ink-mute hover:bg-raised hover:text-ink inline-flex size-11 shrink-0 items-center justify-center"
                    >
                      <Pencil className="size-3" />
                    </button>
                    <button
                      type="button"
                      aria-label={t('history.group.delete')}
                      onClick={() => {
                        setDeleteTasks(false)
                        setPendingDelete({
                          id: group.id,
                          name: group.name,
                          count: group.task_count ?? 0,
                        })
                      }}
                      className="ember-press rounded-control text-ink-mute hover:bg-raised hover:text-danger inline-flex size-11 shrink-0 items-center justify-center"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                </>
              )}
            </div>
          )
        })}

        <div
          {...dropProps(UNGROUPED_ID)}
          className={cn(
            'rounded-control flex items-center gap-1.5 px-1 py-0.5 transition-colors duration-[var(--dur-hover)] ease-[var(--ease)]',
            activeGroupId === UNGROUPED_ID && 'bg-primary-soft',
            dropTargetId === UNGROUPED_ID && 'bg-primary-soft ring-primary/50 ring-1'
          )}
        >
          <Checkbox
            checked={checkedGroupIds.includes(UNGROUPED_ID)}
            onChange={() => toggleGroupChecked(UNGROUPED_ID)}
            label={t('history.group.ungrouped')}
          />
          <button
            type="button"
            onClick={() => setActiveGroupId(activeGroupId === UNGROUPED_ID ? null : UNGROUPED_ID)}
            aria-pressed={activeGroupId === UNGROUPED_ID}
            className={cn(
              'rounded-control flex min-w-0 flex-1 items-center gap-1.5 px-1 py-0.5 text-left',
              activeGroupId === UNGROUPED_ID ? 'text-ink' : 'text-ink-soft hover:text-ink'
            )}
          >
            <span className="text-small truncate font-semibold">
              {t('history.group.ungrouped')}
            </span>
            <span className="text-caption text-ink-mute ml-auto shrink-0 tabular-nums">
              {ungroupedCount}
            </span>
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 px-1">
        <label className="text-caption text-ink-soft flex items-center gap-1.5">
          <Checkbox
            checked={allChecked}
            onChange={setAllChecked}
            disabled={!groups.length && !ungroupedCount}
            label={t('group.selectAll')}
          />
          <span>{t('group.selectAll')}</span>
        </label>
        <span className="text-caption text-ink-mute truncate">{t('group.dragHint')}</span>
      </div>

      <Dialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        size="sm"
        title={t('group.deleteTitle')}
        description={
          pendingDelete
            ? t('group.deleteBody', { name: pendingDelete.name, count: pendingDelete.count })
            : undefined
        }
        footer={
          <>
            <Button size="sm" variant="ghost" onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={async () => {
                if (!pendingDelete) return
                const ok = await removeGroup(pendingDelete.id, deleteTasks)
                if (ok) setPendingDelete(null)
              }}
            >
              {t('common.delete')}
            </Button>
          </>
        }
      >
        <label className="text-small text-ink-soft flex items-center gap-2">
          <Checkbox
            checked={deleteTasks}
            onChange={setDeleteTasks}
            label={t('history.group.deleteAlsoTasks')}
          />
          <span>{t('history.group.deleteAlsoTasks')}</span>
        </label>
      </Dialog>
    </section>
  )
}
