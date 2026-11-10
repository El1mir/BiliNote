import { type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Menu, Sparkles } from 'lucide-react'
import { Button } from '@/ember/ui/Button'
import { Drawer } from '@/ember/ui/Drawer'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { ThemeToggle } from '@/ember/shell/ThemeToggle'
import { Topbar } from '@/ember/shell/Topbar'
import { useEmberNav } from '@/ember/shell/useEmberNav'
import { cn } from '@/ember/lib/cn'
import { useState } from 'react'

type NavItem = { to: string; label: string; icon: ReactNode; end?: boolean }

type AppShellProps = {
  nav: NavItem[]
  /** Content pinned to the bottom of the sidebar (backend status, settings link…). */
  sidebarFooter?: ReactNode
  /** Right-hand rail. Rendered inside the content column on large screens. */
  rail?: ReactNode
  railWidth?: number
  children: ReactNode
}

/**
 * BiliNote workbench application shell.
 * - >=1280px: 256px sidebar + fluid content + optional rail
 * - 768–1279px: icon-only sidebar + fluid content (rail collapses under content)
 * - <768px: top bar + slide-in drawer
 * Only the sidebar's own width changes across breakpoints; page content never
 * re-mounts, so switching viewports cannot drop state.
 */
export function AppShell({ nav, sidebarFooter, rail, railWidth = 340, children }: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { pathname } = useLocation()
  const { overline, openNav } = useEmberNav()

  const isActive = (item: NavItem) =>
    item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)

  const navList = (onNavigate?: () => void) => (
    <nav className="flex flex-col gap-1">
      {nav.map(item => {
        const active = isActive(item)
        return (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            aria-current={active ? 'page' : undefined}
            // The 72px rail hides the label visually; the name has to survive.
            aria-label={item.label}
            className={cn(
              'ember-press ember-accent-bar relative flex items-center gap-3 rounded-control py-2.5 pr-3 pl-4 text-small font-semibold',
              active ? 'bg-primary-soft text-primary' : 'text-ink-soft hover:bg-surface hover:text-ink',
            )}
          >
            <span className={cn('shrink-0', active ? 'text-primary' : 'text-ink-mute')}>{item.icon}</span>
            {/* 76px rail (md–lg) has no room for labels; hidden, not truncated. */}
            <span className="hidden truncate xl:inline">{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )

  return (
    <div className="flex min-h-screen bg-canvas">
      {/* Desktop / tablet sidebar */}
      <aside className="sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-canvas md:flex md:w-[72px] xl:w-[256px]">
        <div className="flex items-center gap-2.5 px-4 py-5">
          <span className="grid size-9 shrink-0 place-items-center rounded-control bg-primary text-on-primary">
            <Sparkles className="size-4" />
          </span>
          <div className="hidden min-w-0 flex-col xl:flex">
            <span className="font-display text-subhead leading-tight">BiliNote</span>
            <span className="ember-overline">{overline}</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-3 pb-4">{navList()}</div>
        {/* Global switches sit at the bottom of the rail. The language switcher
            is supplied by the page (sidebarFooter) and only fits the labelled
            rail; below xl it lives in the mobile header and the drawer. */}
        <div className="flex items-center justify-between gap-2 border-t border-line px-2 py-2 xl:px-3">
          <ThemeToggle compact />
          {sidebarFooter ? <span className="hidden xl:block">{sidebarFooter}</span> : null}
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur md:hidden">
          <Button variant="ghost" size="sm" aria-label={openNav} className="px-2" onClick={() => setDrawerOpen(true)}>
            <Menu className="size-5" />
          </Button>
          <span className="font-display text-subhead">BiliNote</span>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle compact />
            <LanguageSwitcher compact />
          </div>
        </header>

        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="BiliNote">
          <div className="flex flex-col gap-4">
            {navList(() => setDrawerOpen(false))}
            <div className="flex items-center gap-1 border-t border-line pt-3">
              <ThemeToggle compact />
              <LanguageSwitcher compact />
            </div>
            {sidebarFooter ? <div className="border-t border-line pt-3">{sidebarFooter}</div> : null}
          </div>
        </Drawer>

        {/* Desktop chrome: location + backend liveness + global switches. The
            mobile header above already carries the same switches. */}
        <Topbar label={nav.find(isActive)?.label ?? nav[0]?.label ?? ''} />

        <main className="min-w-0 flex-1">
          {rail ? (
            <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-4 py-6 sm:px-6 lg:flex-row lg:gap-8 lg:py-8">
              {/* Below lg the history rail comes first (it is the way back into a task);
                  from lg up it returns to the right-hand column. */}
              <div className="order-2 min-w-0 flex-1 lg:order-1">{children}</div>
              <div
                className="order-1 shrink-0 lg:order-2 lg:w-[var(--rail-w)]"
                style={{ ['--rail-w' as string]: `${railWidth}px` }}
              >
                {rail}
              </div>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-[var(--shell-max)] px-4 py-6 sm:px-6 lg:py-8">{children}</div>
          )}
        </main>
      </div>
    </div>
  )
}
