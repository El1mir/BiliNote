import React, { FC, useEffect, useRef, useState } from 'react'
import {
  SlidersHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  History as HistoryIcon,
  Columns3,
} from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'

import { Link } from 'react-router-dom'
import { ResizablePanel, ResizablePanelGroup, ResizableHandle } from '@/components/ui/resizable'

import type { ImperativePanelHandle } from 'react-resizable-panels'
import logo from '@/assets/icon.svg'

interface IProps {
  NoteForm: React.ReactNode
  Preview: React.ReactNode
  History: React.ReactNode
}

/**
 * 三栏的宽度断点。窄屏（半屏笔记本、平板竖屏）下三栏并排会把中栏挤成一条
 * 十几像素的缝 —— 文字换行成竖排、按钮全被裁掉。窄屏下改成「默认只留正文，
 * 目录/历史按需从左侧滑轨展开」。
 */
const COMPACT_QUERY = '(max-width: 1279px)'

const useIsCompact = () => {
  const [compact, setCompact] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia(COMPACT_QUERY).matches
  )
  useEffect(() => {
    const mql = window.matchMedia(COMPACT_QUERY)
    const onChange = (event: MediaQueryListEvent) => setCompact(event.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return compact
}

const HomeLayout: FC<IProps> = ({ NoteForm, Preview, History }) => {
  const [, setShowSettings] = useState(false)
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false)
  const [isMiddleCollapsed, setIsMiddleCollapsed] = useState(false)
  const isCompact = useIsCompact()
  const leftPanelRef = useRef<ImperativePanelHandle>(null)
  const middlePanelRef = useRef<ImperativePanelHandle>(null)

  /**
   * 窄屏进入时自动把左右两栏收起，回到宽屏再展开。
   * 只动「因窄屏而收起」的这一次，不覆盖用户自己手动收起的选择 ——
   * 用户手动收起后切一次窗口宽度就被强行展开，是很讨厌的行为。
   */
  const compactAutoCollapsed = useRef(false)
  useEffect(() => {
    if (isCompact) {
      if (compactAutoCollapsed.current) return
      leftPanelRef.current?.collapse()
      middlePanelRef.current?.collapse()
      compactAutoCollapsed.current = true
      return
    }
    if (!compactAutoCollapsed.current) return
    leftPanelRef.current?.expand()
    middlePanelRef.current?.expand()
    compactAutoCollapsed.current = false
  }, [isCompact])

  /** 窄屏下两栏都收起了，给用户一个「恢复三栏」的出口。 */
  const restorePanels = () => {
    compactAutoCollapsed.current = false
    leftPanelRef.current?.expand()
    middlePanelRef.current?.expand()
  }

  return (
    <div className="app-shell flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-slate-50">
      <ResizablePanelGroup direction="horizontal" className="h-full min-h-0 w-full">
        {/* 左边表单 */}
        <ResizablePanel
          className="min-h-0"
          ref={leftPanelRef}
          defaultSize={22}
          minSize={18}
          maxSize={34}
          collapsible
          collapsedSize={0}
          onCollapse={() => setIsLeftCollapsed(true)}
          onExpand={() => setIsLeftCollapsed(false)}
        >
          <aside className="flex h-full min-h-0 flex-col overflow-hidden border-r border-slate-200 bg-white">
            <header className="flex h-16 shrink-0 items-center justify-between gap-2 px-4">
              <div className="flex min-w-0 items-center gap-2">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-2xl">
                  <img src={logo} alt="logo" className="h-full w-full object-contain" />
                </div>
                <div className="truncate text-xl font-bold text-gray-800">BiliNote</div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => leftPanelRef.current?.collapse()}
                        className="text-muted-foreground hover:text-primary cursor-pointer rounded p-1 hover:bg-neutral-100"
                      >
                        <PanelLeftClose className="h-5 w-5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <span>收起工作区</span>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger onClick={() => setShowSettings(true)}>
                      <Link to={'/settings'}>
                        <SlidersHorizontal className="text-muted-foreground hover:text-primary cursor-pointer" />
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent>
                      <span>全局配置</span>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </header>
            <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
              <div className="p-4">{NoteForm}</div>
            </div>
          </aside>
        </ResizablePanel>

        <ResizableHandle />

        {/* 左边面板折叠时的展开滑轨 */}
        {isLeftCollapsed && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => leftPanelRef.current?.expand()}
                  className="flex h-full w-9 shrink-0 cursor-pointer items-center justify-center border-r border-slate-200 bg-white hover:bg-neutral-50"
                >
                  <PanelLeftOpen className="text-muted-foreground h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">
                <span>展开工作区</span>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* 中间历史：默认 1/4 宽（原先 16% 只有 200px 出头，标题一行都放不下） */}
        <ResizablePanel
          ref={middlePanelRef}
          className="min-h-0"
          defaultSize={25}
          minSize={20}
          maxSize={45}
          collapsible
          collapsedSize={0}
          onCollapse={() => setIsMiddleCollapsed(true)}
          onExpand={() => setIsMiddleCollapsed(false)}
        >
          <aside className="flex h-full min-h-0 flex-col overflow-hidden border-r border-slate-200 bg-white">
            <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-slate-200 px-3">
              <span className="truncate text-sm font-semibold text-gray-700">生成历史</span>
              <div className="flex shrink-0 items-center gap-1">
                {isCompact && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={restorePanels}
                          className="text-muted-foreground hover:text-primary cursor-pointer rounded p-1 hover:bg-neutral-100"
                        >
                          <Columns3 className="h-4 w-4" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <span>恢复三栏</span>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => middlePanelRef.current?.collapse()}
                        className="text-muted-foreground hover:text-primary cursor-pointer rounded p-1 hover:bg-neutral-100"
                      >
                        <PanelLeftClose className="h-4 w-4" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <span>收起历史</span>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </header>
            <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
              <div>{History}</div>
            </div>
          </aside>
        </ResizablePanel>

        <ResizableHandle />

        {/* 中间面板折叠时的展开滑轨 */}
        {isMiddleCollapsed && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => middlePanelRef.current?.expand()}
                  className="flex h-full w-9 shrink-0 cursor-pointer items-center justify-center border-r border-slate-200 bg-white hover:bg-neutral-50"
                >
                  <HistoryIcon className="text-muted-foreground h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">
                <span>展开历史</span>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* 右边预览 */}
        <ResizablePanel className="min-h-0" defaultSize={53} minSize={30}>
          <main className="flex h-full min-h-0 flex-col overflow-hidden bg-slate-50 px-4 py-4 lg:px-6 lg:py-6">
            {Preview}
          </main>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

export default HomeLayout
