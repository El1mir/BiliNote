import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '@/ember/lib/cn'
import { resolveTabKey, tabId, panelId } from '@/ember/ui/tabsA11y'

export type TabItem = { id: string; label: ReactNode; badge?: ReactNode }

type TabsProps = {
  items: TabItem[]
  value: string
  onChange: (id: string) => void
  /**
   * 稳定前缀，用来把 tab 与面板的 id 关联起来。缺省用 useId() 生成，
   * 但调用方若渲染了 role="tabpanel" 的面板，必须传一个与渲染生命周期一致的
   * 值（字面量），否则每次挂载 id 都会变，aria-controls 会指向旧节点。
   */
  idBase?: string
  className?: string
}

/**
 * Underline tabs — active tab is terracotta with a 2px bottom border.
 *
 * WAI-ARIA tabs 模式：tablist 内只有当前 tab 可 Tab 进入（roving tabindex），
 * 左右方向键在 tab 之间移动并聚焦，Home/End 跳到首尾。鼠标点击仍然直接切换。
 * 面板一侧的属性由 tabPanelProps() 提供（见 tabsA11y.ts）。
 */
export function Tabs({ items, value, onChange, idBase, className }: TabsProps) {
  const generatedId = useId()
  const base = idBase ?? generatedId.replace(/:/g, '')
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  const moveTo = (index: number) => {
    const next = items[(index + items.length) % items.length]
    if (!next) return
    onChange(next.id)
    buttonRefs.current[next.id]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const target = resolveTabKey(event.key, index, items.length)
    if (target === null) return
    event.preventDefault()
    moveTo(target)
  }

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={cn('flex items-center gap-1 border-b border-line', className)}
    >
      {items.map((item, index) => {
        const active = item.id === value
        return (
          <button
            key={item.id}
            ref={node => {
              buttonRefs.current[item.id] = node
            }}
            type="button"
            role="tab"
            id={tabId(base, item.id)}
            aria-selected={active}
            aria-controls={panelId(base, item.id)}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={event => onKeyDown(event, index)}
            className={cn(
              'ember-press relative -mb-px inline-flex items-center gap-1.5 rounded-t-control px-3 py-2 text-small font-semibold',
              active ? 'text-ember' : 'text-ink-soft hover:bg-surface hover:text-ink',
            )}
          >
            {item.label}
            {item.badge}
            {active ? (
              <span aria-hidden="true" className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-ember" />
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
