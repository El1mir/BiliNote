import { useState, useEffect, useRef, useMemo, memo, FC, Children, isValidElement } from 'react'
import ReactMarkdown from 'react-markdown'
import { Copy, ArrowRight, Play, ExternalLink } from 'lucide-react'
import { toast } from 'react-hot-toast'
import Error from '@/components/Lottie/error.tsx'
import Loading from '@/components/Lottie/Loading.tsx'
import Idle from '@/components/Lottie/Idle.tsx'

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import ProgressTimeline from '@/pages/HomePage/components/ProgressTimeline.tsx'
import { atomDark as codeStyle } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Zoom from 'react-medium-image-zoom'
import 'react-medium-image-zoom/dist/styles.css'
import gfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import 'katex/dist/katex.min.css'
import 'github-markdown-css/github-markdown-light.css'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { useTaskStore, readLatestMarkdown } from '@/store/taskStore'
import { noteDetails, noteScenes } from '@/constant/note.ts'
import { MarkdownHeader } from '@/pages/HomePage/components/MarkdownHeader.tsx'
import TranscriptViewer from '@/pages/HomePage/components/transcriptViewer.tsx'
import MarkmapEditor from '@/pages/HomePage/components/MarkmapComponent.tsx'
import ChatPanel from '@/pages/HomePage/components/ChatPanel.tsx'
import VideoBanner from '@/pages/HomePage/components/VideoBanner.tsx'
import { normalizeMathDelimiters } from '@/utils/markdown'
import { asText } from '@/utils/text'
import { downloadNoteArchive } from '@/services/note'

interface MarkdownViewerProps {
  status: 'idle' | 'loading' | 'success' | 'failed'
}
const remarkPlugins = [gfm, remarkMath]
const rehypePlugins = [rehypeKatex, rehypeSlug]

/**
 * 构建 ReactMarkdown components 对象，baseURL 用于修正图片路径。
 * 使用函数 + useMemo 避免每次渲染都创建新的函数实例。
 */
function createMarkdownComponents(baseURL: string) {
  return {
    h1: ({ children, ...props }: any) => (
      <h1
        className="text-primary my-6 scroll-m-20 text-3xl font-extrabold tracking-tight lg:text-4xl"
        {...props}
      >
        {children}
      </h1>
    ),
    h2: ({ children, ...props }: any) => (
      <h2
        className="text-primary mt-10 mb-4 scroll-m-20 border-b pb-2 text-2xl font-semibold tracking-tight first:mt-0"
        {...props}
      >
        {children}
      </h2>
    ),
    h3: ({ children, ...props }: any) => (
      <h3
        className="text-primary mt-8 mb-4 scroll-m-20 text-xl font-semibold tracking-tight"
        {...props}
      >
        {children}
      </h3>
    ),
    h4: ({ children, ...props }: any) => (
      <h4
        className="text-primary mt-6 mb-2 scroll-m-20 text-lg font-semibold tracking-tight"
        {...props}
      >
        {children}
      </h4>
    ),
    p: ({ children, ...props }: any) => {
      const containsImage = Children.toArray(children).some(child => {
        if (!isValidElement(child)) return false
        const childProps = child.props as { src?: unknown; children?: unknown }
        return (
          typeof childProps.src === 'string' ||
          Children.toArray(childProps.children).some(
            n => isValidElement(n) && typeof (n.props as { src?: unknown }).src === 'string'
          )
        )
      })
      const className = 'leading-7 [&:not(:first-child)]:mt-6'
      return containsImage ? (
        <div className={className}>{children}</div>
      ) : (
        <p className={className} {...props}>
          {children}
        </p>
      )
    },
    a: ({ href, children, ...props }: any) => {
      const isOriginLink =
        typeof children[0] === 'string' && (children[0] as string).startsWith('原片 @')

      if (isOriginLink) {
        const timeMatch = (children[0] as string).match(/原片 @ (\d{2}:\d{2})/)
        const timeText = timeMatch ? timeMatch[1] : '原片'

        return (
          <span className="origin-link my-2 inline-flex">
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
              {...props}
            >
              <Play className="h-3.5 w-3.5" />
              <span>原片（{timeText}）</span>
            </a>
          </span>
        )
      }

      // 处理笔记内部锚点链接（如目录跳转）
      if (href?.startsWith('#')) {
        const handleAnchorClick = (e: React.MouseEvent) => {
          e.preventDefault()
          const id = decodeURIComponent(href.slice(1))

          // 1. 优先精确匹配 id
          let target = document.getElementById(id)

          // 2. 精确失败时按 heading 文本模糊匹配
          // LLM 生成的目录锚点可能和 heading 实际文本不完全一致
          //（例如 heading 带 *Content-[00:00]* 后缀，目录链接里没有）
          if (!target) {
            const normalize = (s: string) => s.replace(/[-：:\s*\[\]]/g, '').toLowerCase()
            const search = normalize(id)
            const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6')
            for (const h of headings) {
              const text = h.textContent || ''
              if (normalize(text).includes(search) || search.includes(normalize(text))) {
                target = h
                break
              }
            }
          }

          if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' })
          } else {
            toast.error('未找到对应章节')
          }
        }

        return (
          <a
            href={href}
            onClick={handleAnchorClick}
            className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
            {...props}
          >
            {children}
          </a>
        )
      }

      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
          {...props}
        >
          {children}
          {href?.startsWith('http') && <ExternalLink className="ml-0.5 inline-block h-3 w-3" />}
        </a>
      )
    },
    img: ({ node, ...props }: any) => {
      let src = props.src
      if (src.startsWith('/')) {
        src = baseURL + src
      }
      props.src = src

      return (
        <div className="my-8 flex justify-center">
          <Zoom>
            <img
              {...props}
              className="max-w-full cursor-zoom-in rounded-lg object-cover shadow-md transition-all hover:shadow-lg"
              style={{ maxHeight: '500px' }}
            />
          </Zoom>
        </div>
      )
    },
    strong: ({ children, ...props }: any) => (
      <strong className="text-primary font-bold" {...props}>
        {children}
      </strong>
    ),
    li: ({ children, ordered: _ordered, index: _index, checked: _checked, ...props }: any) => {
      const rawText = String(children)
      const isFakeHeading = /^\*\*.+\*\*$/.test(rawText.trim())
      if (isFakeHeading)
        return <div className="text-primary my-4 text-lg font-bold">{children}</div>
      return (
        <li className="my-1" {...props}>
          {children}
        </li>
      )
    },
    ul: ({ children, ordered: _ordered, depth: _depth, ...props }: any) => (
      <ul className="my-6 ml-6 list-disc [&>li]:mt-2" {...props}>
        {children}
      </ul>
    ),
    blockquote: ({ children, ...props }: any) => (
      <blockquote
        className="border-primary/20 text-muted-foreground mt-6 border-l-4 pl-4 italic"
        {...props}
      >
        {children}
      </blockquote>
    ),
    code: ({ inline, className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '')
      const codeContent = String(children).replace(/\n$/, '')

      if (!inline && match) {
        return (
          <div className="group bg-muted relative my-6 overflow-hidden rounded-lg border shadow-sm">
            <div className="bg-muted text-muted-foreground flex items-center justify-between px-4 py-1.5 text-sm font-medium">
              <div>{match[1].toUpperCase()}</div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(codeContent)
                  toast.success('代码已复制')
                }}
                className="bg-background/80 hover:bg-background flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
                复制
              </button>
            </div>
            <SyntaxHighlighter
              style={codeStyle}
              language={match[1]}
              PreTag="div"
              className="!bg-muted !m-0 !p-0"
              customStyle={{
                margin: 0,
                padding: '1rem',
                background: 'transparent',
                fontSize: '0.9rem',
              }}
              {...props}
            >
              {codeContent}
            </SyntaxHighlighter>
          </div>
        )
      }

      return (
        <code
          className="bg-muted relative rounded px-[0.3rem] py-[0.2rem] font-mono text-sm"
          {...props}
        >
          {children}
        </code>
      )
    },
    table: ({ children, ...props }: any) => (
      <div className="my-6 w-full overflow-y-auto">
        <table className="w-full border-collapse text-sm" {...props}>
          {children}
        </table>
      </div>
    ),
    th: ({ children, isHeader: _isHeader, ...props }: any) => (
      <th
        className="border-muted-foreground/20 border px-4 py-2 text-left font-medium [&[align=center]]:text-center [&[align=right]]:text-right"
        {...props}
      >
        {children}
      </th>
    ),
    td: ({ children, isHeader: _isHeader, ...props }: any) => (
      <td
        className="border-muted-foreground/20 border px-4 py-2 text-left [&[align=center]]:text-center [&[align=right]]:text-right"
        {...props}
      >
        {children}
      </td>
    ),
    hr: ({ ...props }: any) => <hr className="border-muted-foreground/20 my-8" {...props} />,
  }
}

const MarkdownViewer: FC<MarkdownViewerProps> = memo(({ status }) => {
  const [copied, setCopied] = useState(false)
  const [selectedContent, setSelectedContent] = useState<string>('')
  const [modelName, setModelName] = useState<string>('')
  const [scene, setScene] = useState<string>('')
  const [detail, setDetail] = useState<string>('')
  const [createTime, setCreateTime] = useState<string>('')
  // 确保baseURL没有尾部斜杠
  const baseURL = (
    String(import.meta.env.VITE_API_BASE_URL || '').replace('/api', '') || ''
  ).replace(/\/$/, '')
  const getCurrentTask = useTaskStore.getState().getCurrentTask
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const taskStatus = currentTask?.status || 'PENDING'
  const [showTranscribe, setShowTranscribe] = useState(false)
  const [showChat, setShowChat] = useState<false | 'half' | 'full'>(false)
  const [viewMode, setViewMode] = useState<'map' | 'preview'>('preview')
  const svgRef = useRef<SVGSVGElement>(null)

  // 缓存 ReactMarkdown components，仅在 baseURL 变化时重建
  const markdownComponents = useMemo(() => createMarkdownComponents(baseURL), [baseURL])

  // 笔记内容与元信息（版本功能已删除，spec 008）
  useEffect(() => {
    if (!currentTask) return

    setModelName(asText(currentTask.formData?.model_name, '未知模型'))
    setScene(asText(currentTask.formData?.scene, ''))
    setDetail(asText(currentTask.formData?.detail, ''))
    setCreateTime(currentTask.createdAt)
    setSelectedContent(readLatestMarkdown(currentTask.markdown))
  }, [currentTask?.id, taskStatus])
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(selectedContent)
      setCopied(true)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopied(false), 2000)
    } catch (e) {
      toast.error('复制失败')
    }
  }
  const alertButton = {
    id: 'alert',
    title: '测试警告',
    content: '⚠️',
    onClick: () => alert('你点击了自定义按钮！'),
  }
  const exportButton = {
    id: 'export',
    title: '导出思维导图',
    content: '⤓',
    onClick: () => {
      const svgEl = svgRef.current
      if (!svgEl) return
      // 同上面的序列化逻辑
      const serializer = new XMLSerializer()
      const source = serializer.serializeToString(svgEl)
      const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>', source], {
        type: 'image/svg+xml;charset=utf-8',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'mindmap.svg'
      a.click()
      URL.revokeObjectURL(url)
    },
  }
  const handleDownload = async () => {
    const task = getCurrentTask()
    if (!task?.id) {
      toast.error('找不到笔记任务，无法导出')
      return
    }
    try {
      const blob = await downloadNoteArchive(task.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${asText(task.audioMeta.title, 'note').replace(/[\\/:*?"<>|]/g, '_')}.zip`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '笔记归档下载失败')
    }
  }

  if (status === 'loading') {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center space-y-4 text-neutral-500">
        {currentTask && <ProgressTimeline task={currentTask} />}
        <Loading className="h-5 w-5" />
        <div className="text-center text-sm">
          <p className="text-lg font-bold">正在生成笔记，请稍候…</p>
          <p className="mt-2 text-xs text-neutral-500">这可能需要几秒钟时间，取决于视频长度</p>
        </div>
      </div>
    )
  }

  if (status === 'idle') {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center space-y-3 text-neutral-500">
        <Idle />
        <div className="text-center">
          <p className="text-lg font-bold">输入视频链接并点击"生成笔记"</p>
          <p className="mt-2 text-xs text-neutral-500">支持哔哩哔哩、YouTube 、抖音等视频平台</p>
        </div>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center gap-4 space-y-3">
        <Error />
        <div className="text-center">
          <p className="text-lg font-bold text-red-500">笔记生成失败</p>
          <p className="mt-2 mb-2 text-xs text-red-400">请检查后台或稍后再试</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden">
      <MarkdownHeader
        modelName={modelName}
        scene={scene}
        detail={detail}
        noteScenes={noteScenes}
        noteDetails={noteDetails}
        onCopy={handleCopy}
        onDownload={handleDownload}
        createAt={createTime}
        showTranscribe={showTranscribe}
        setShowTranscribe={setShowTranscribe}
        showChat={showChat}
        setShowChat={setShowChat}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />

      {viewMode === 'map' ? (
        <div className="flex w-full flex-1 overflow-hidden bg-white">
          <div className={'w-full'}>
            <MarkmapEditor
              value={selectedContent}
              onChange={() => {}}
              height="100%" // 根据需求可以设定百分比或固定高度
              title={asText(currentTask?.audioMeta?.title, '思维导图')}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden bg-white py-2">
          {selectedContent && selectedContent !== 'loading' && selectedContent !== 'empty' ? (
            <>
              {showChat === 'full' && currentTask ? (
                <div className="h-full w-full">
                  <ChatPanel taskId={currentTask.id} mode="full" onModeChange={setShowChat} />
                </div>
              ) : (
                <>
                  <ScrollArea className="min-w-0 flex-1">
                    <div className="px-2">
                      <VideoBanner
                        audioMeta={currentTask?.audioMeta}
                        videoUrl={currentTask?.formData?.video_url}
                      />
                    </div>
                    <div className={'markdown-body w-full px-2'}>
                      <ReactMarkdown
                        remarkPlugins={remarkPlugins}
                        rehypePlugins={rehypePlugins}
                        components={markdownComponents}
                      >
                        {normalizeMathDelimiters(
                          selectedContent.replace(/^>\s*来源链接：[^\n]*\n*/m, '')
                        )}
                      </ReactMarkdown>
                    </div>
                  </ScrollArea>
                  {showTranscribe && (
                    <div className={'ml-2 w-2/4'}>
                      <TranscriptViewer />
                    </div>
                  )}
                  {/* 侧边问答模式：markdown + ChatPanel 各占一半 */}
                  {showChat === 'half' && currentTask && (
                    <div className="ml-2 h-full w-1/2 shrink-0">
                      <ChatPanel taskId={currentTask.id} mode="half" onModeChange={setShowChat} />
                    </div>
                  )}
                </>
              )}
            </>
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <div className="w-[300px] flex-col justify-items-center">
                <div className="bg-primary-light mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                  <ArrowRight className="text-primary h-8 w-8" />
                </div>
                <p className="mb-2 text-neutral-600">输入视频链接并点击"生成笔记"按钮</p>
                <p className="text-xs text-neutral-500">支持哔哩哔哩、YouTube等视频网站</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
})

MarkdownViewer.displayName = 'MarkdownViewer'

export default MarkdownViewer
