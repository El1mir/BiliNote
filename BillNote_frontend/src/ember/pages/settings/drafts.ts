/**
 * 设置页的未保存草稿（T-062 / 上游 UI 计划 §5）。
 *
 * 问题：`SettingsPage` 的路由一次只挂载一个分区，切走即卸载，草稿随组件一起没了 ——
 * 用户在 General 改了 26 个数值，点去看一眼 Prompt，回来全变回原值，且没有任何提示。
 *
 * 做法：草稿放在 React 之外的小仓库里（按分区 id 存），组件挂载时从这里取初值，
 * 每次编辑写回。这样"切走再切回"草稿仍在；导航上能标出哪些分区有未保存改动。
 *
 * 明确不做路由拦截（useBlocker / createBrowserRouter 在本仓库 0 命中，引入成本大于收益）：
 * 保存成功后由分区自己 clearDraft，用户始终能看出"哪些还没保存"。
 */

type Listener = () => void

const drafts = new Map<string, unknown>()
const listeners = new Set<Listener>()

/** useSyncExternalStore 的快照：变化时递增，避免返回 Map（引用稳定，React 不重渲染）。 */
let version = 0

function emit(): void {
  version += 1
  for (const listener of listeners) listener()
}

export function subscribeDrafts(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function draftsVersion(): number {
  return version
}

/** 读某分区的未保存草稿；没有则 undefined。 */
export function readDraft<T>(key: string): T | undefined {
  return drafts.get(key) as T | undefined
}

/**
 * 写草稿。传 undefined 等价于清除 —— 分区保存成功后用 clearDraft 表达"回到已保存状态"，
 * 这样"有没有未保存改动"只有一个判据：Map 里还有没有这个 key。
 */
export function writeDraft<T>(key: string, value: T | undefined): void {
  if (value === undefined) {
    if (!drafts.delete(key)) return
  } else {
    drafts.set(key, value)
  }
  emit()
}

export function clearDraft(key: string): void {
  writeDraft(key, undefined)
}

export function hasDraft(key: string): boolean {
  return drafts.has(key)
}

export function draftKeys(): string[] {
  return [...drafts.keys()]
}

/** 仅供测试：把仓库清空，避免用例之间互相污染。 */
export function resetDrafts(): void {
  drafts.clear()
  emit()
}
