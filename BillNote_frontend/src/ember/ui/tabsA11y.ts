/**
 * WAI-ARIA tabs 模式的 id 约定与键盘映射。
 *
 * 抽成独立文件，一是组件文件只导出组件（Fast Refresh），
 * 二是这些是纯函数，可以脱离 DOM 单测。
 */

/** tab 按钮的 id。 */
export const tabId = (idBase: string, id: string) => `${idBase}-tab-${id}`

/** 对应面板的 id。 */
export const panelId = (idBase: string, id: string) => `${idBase}-panel-${id}`

/**
 * 面板要挂的属性：role / aria-labelledby / 反向指针。
 * 面板自身负责显隐（hidden 或条件渲染），Tabs 只负责按钮一侧。
 */
export const tabPanelProps = (idBase: string, id: string) => ({
  role: 'tabpanel' as const,
  id: panelId(idBase, id),
  'aria-labelledby': tabId(idBase, id),
  tabIndex: 0,
})

/**
 * 把方向键映射成目标下标；不认识的键返回 null。
 *
 * 焦点陷阱/键盘导航最容易错的是边界回绕，而这一段不需要真实浏览器。
 */
export function resolveTabKey(key: string, currentIndex: number, count: number): number | null {
  if (count <= 0) return null
  switch (key) {
    case 'ArrowRight':
      return (currentIndex + 1) % count
    case 'ArrowLeft':
      return (currentIndex - 1 + count) % count
    case 'Home':
      return 0
    case 'End':
      return count - 1
    default:
      return null
  }
}
