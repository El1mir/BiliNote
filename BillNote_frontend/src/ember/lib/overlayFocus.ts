import { useEffect, useRef, type RefObject } from 'react'

/**
 * 可聚焦元素选择器。用 :not([disabled]) 而不是 [tabindex="0"]，
 * 因为原生控件（a[href]/button/input）默认就可聚焦，不写 tabindex。
 */
export const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  'audio[controls]',
  'video[controls]',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/** 在容器内收集真正可聚焦的元素（排除 display:none / visibility:hidden）。 */
export function getFocusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(element => {
    if (element.hasAttribute('disabled')) return false
    if (element.getAttribute('aria-hidden') === 'true') return false
    // offsetParent 为 null 说明元素（或祖先）是 display:none；jsdom 里恒为 null，
    // 所以只在浏览器环境下作为额外过滤条件。
    if (element.offsetParent === null && element.getClientRects().length === 0) return false
    return true
  })
}

/**
 * 纯函数：Tab / Shift+Tab 时焦点在列表中的下一个位置。
 * 独立出来是为了能脱离 DOM 单测：焦点陷阱最容易错的就是首尾回绕，
 * 而这一段逻辑不需要真实浏览器。
 */
export function nextFocusIndex(
  current: number,
  count: number,
  options: { shift?: boolean } = {}
): number {
  if (count <= 0) return -1
  const delta = options.shift ? -1 : 1
  // current < 0（焦点在面板本身）时，Tab 应进入第一个、Shift+Tab 应到最后一个。
  if (current < 0) return options.shift ? count - 1 : 0
  return (current + delta + count) % count
}

/**
 * 纯函数：一次 Tab / Shift+Tab 该不该拦截、应该把焦点放到哪。
 *
 * 只在边界回绕时拦截（中间位置的默认 Tab 行为本来就留在面板内），
 * 这样不会破坏浏览器对可见性/顺序的原生处理。抽出来是为了能脱 DOM 单测。
 */
export function trapDecision(input: {
  currentIndex: number
  count: number
  shift: boolean
}): { prevent: boolean; focusIndex: number } {
  const { currentIndex, count, shift } = input
  if (count <= 0) return { prevent: false, focusIndex: -1 }
  const focusIndex = nextFocusIndex(currentIndex, count, { shift })
  const atStart = currentIndex <= 0
  const atEnd = currentIndex === count - 1
  const prevent = shift ? atStart : atEnd
  return { prevent, focusIndex }
}

/**
 * overlay（Dialog / Drawer）的共用焦点行为：
 *
 * - 打开时记住触发元素，并把焦点移进面板（首个可聚焦元素，没有就面板本身）；
 * - Tab / Shift+Tab 在面板内回绕，不逃到背景文档；
 * - Escape 触发 onClose；
 * - 关闭后把焦点还给触发元素 —— 否则键盘用户会回到 body 开头，等于丢失上下文。
 *
 * body 滚动锁也在这里，两个 overlay 原来只有 Dialog 做了。
 */
export function useOverlayFocus(options: {
  open: boolean
  onClose: () => void
  panelRef: RefObject<HTMLElement | null>
  /** 关闭后是否把焦点还给触发元素；默认 true。 */
  restoreFocus?: boolean
}) {
  const { open, onClose, panelRef, restoreFocus = true } = options
  const triggerRef = useRef<HTMLElement | null>(null)
  // onClose 常是内联箭头函数，放进 ref 避免 effect 每次渲染重跑导致焦点被重置。
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return
    const active = document.activeElement
    triggerRef.current = active instanceof HTMLElement ? active : null

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const focusables = getFocusableElements(panelRef.current)
    const target = focusables[0] ?? panelRef.current
    target?.focus()

    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return

      const panel = panelRef.current
      if (!panel) return
      const items = getFocusableElements(panel)
      if (!items.length) {
        // 面板内没有可聚焦元素：把焦点钉在面板上，Tab 也不许跑出去。
        event.preventDefault()
        panel.focus()
        return
      }

      const { prevent, focusIndex } = trapDecision({
        currentIndex: items.indexOf(document.activeElement as HTMLElement),
        count: items.length,
        shift: event.shiftKey,
      })
      if (prevent && focusIndex >= 0) {
        event.preventDefault()
        items[focusIndex]?.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      if (restoreFocus) {
        const trigger = triggerRef.current
        if (trigger && document.contains(trigger)) trigger.focus()
      }
    }
  }, [open, panelRef, restoreFocus])
}