import { useState } from 'react'
import { Archive, Copy, Download, FileText, ListTree } from 'lucide-react'
import toast from 'react-hot-toast'
import { readLatestMarkdown, type Task } from '@/store/taskStore'
import { downloadNoteArchive } from '@/services/note'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'
import { EmptyState } from '@/ember/ui/EmptyState'
import { Tabs } from '@/ember/ui/Tabs'
import { MarkdownNote } from '@/ember/features/reader/MarkdownNote'
import { scrollToAnchor } from '@/ember/features/reader/anchors'
import { extractOutline } from '@/ember/features/reader/outline'
import { TranscriptView } from '@/ember/features/reader/TranscriptView'

type ReaderTab = 'note' | 'transcript'

type NotePanelProps = {
  task: Task | undefined
}

/**
 * The reading surface: the generated note and the transcript it came from,
 * tabbed rather than split — on a laptop, side-by-side panes make both halves
 * too narrow to read.
 *
 * The mind map and the RAG chat that used to sit here were removed together
 * with their backends: both were extra surfaces over the same note, and the
 * vector index the chat needed was rebuilt on every finished task.
 */
export function NotePanel({ task }: NotePanelProps) {
  const { t } = useI18n()
  const [tab, setTab] = useState<ReaderTab>('note')
  const [exporting, setExporting] = useState(false)
  const markdown = readLatestMarkdown(task?.markdown)

  const outline = markdown ? extractOutline(markdown) : []

  const copyMarkdown = async () => {
    try {
      await navigator.clipboard.writeText(markdown)
      toast.success(t('common.copied'))
    } catch {
      toast.error(t('common.error'))
    }
  }

  /** Windows-safe file stem for the two downloads below. */
  const fileName = (task?.audioMeta?.title || task?.id || 'note').replace(/[\\/:*?"<>|]/g, '_')

  const saveBlob = (blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const downloadMarkdown = () => {
    saveBlob(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }), fileName + '.md')
  }

  /**
   * Zips the note folder the backend keeps for this task (markdown +
   * screenshots). Errors are surfaced, never swallowed: the endpoint answers
   * HTTP 200 with a JSON body when there is nothing to package, so a silent
   * path here would hand the user a broken download.
   */
  const downloadArchive = async () => {
    if (!task?.id || exporting) return
    setExporting(true)
    try {
      saveBlob(await downloadNoteArchive(task.id), fileName + '.zip')
      toast.success(t('group.archiveDone', { count: 1 }))
    } catch (error) {
      toast.error(
        t('note.exportFailed', {
          detail: error instanceof Error && error.message ? error.message : t('common.error'),
        })
      )
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs
          value={tab}
          onChange={next => setTab(next as ReaderTab)}
          items={[
            { id: 'note', label: t('note.tab.markdown') },
            { id: 'transcript', label: t('note.tab.transcript') },
          ]}
          className="border-b-0"
        />
        {tab === 'note' && markdown ? (
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" onClick={copyMarkdown}>
              <Copy className="size-3.5" />
              <span className="hidden sm:inline">{t('note.copyMarkdown')}</span>
            </Button>
            <Button size="sm" variant="ghost" onClick={downloadMarkdown}>
              <Download className="size-3.5" />
              <span className="hidden sm:inline">{t('note.download')}</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              loading={exporting}
              onClick={() => void downloadArchive()}
            >
              <Archive className="size-3.5" />
              <span className="hidden sm:inline">{t('note.exportArchive')}</span>
            </Button>
          </div>
        ) : null}
      </div>

      {tab === 'note' ? (
        markdown ? (
          <div className="flex min-h-0 gap-6">
            {outline.length > 2 ? (
              <aside className="sticky top-4 hidden w-56 shrink-0 self-start xl:block">
                <p className="ember-overline mb-2 flex items-center gap-1.5">
                  <ListTree className="size-3" />
                  {t('note.outline')}
                </p>
                <nav className="flex flex-col gap-1 border-l border-line">
                  {outline.map(item => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => scrollToAnchor(item.id)}
                      className="truncate border-l-2 border-transparent py-0.5 text-left text-caption text-ink-soft transition-colors hover:border-ember hover:text-ember"
                      // rem, not px: the rail has to breathe with the user's
                      // font-size setting instead of staying nailed to 10px steps.
                      style={{ paddingLeft: `${0.75 + Math.max(0, item.depth - 2) * 0.5}rem` }}
                    >
                      {item.text}
                    </button>
                  ))}
                </nav>
              </aside>
            ) : null}
            {/* ~68ch is the comfortable long-form measure. Wider viewports keep
                the column centred instead of stretching paragraphs to 1400px. */}
            <div className="mx-auto min-w-0 w-full max-w-[68ch] flex-1">
              <MarkdownNote markdown={markdown} />
            </div>
          </div>
        ) : (
          <EmptyState icon={<FileText className="size-6" />} title={t('note.empty')} />
        )
      ) : null}

      {tab === 'transcript' ? <TranscriptView task={task} /> : null}
    </div>
  )
}
