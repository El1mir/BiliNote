import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import {
  draftKeys,
  draftsVersion,
  readDraft,
  subscribeDrafts,
  writeDraft,
} from '@/ember/pages/settings/drafts'

type Updater<T> = T | undefined | ((prev: T | undefined) => T | undefined)

/**
 * 分区草稿：初值来自跨卸载的草稿仓库，每次修改写回仓库。
 *
 * 与 useState 同形（可直接赋值，也可传 updater），但值同时写进模块级仓库 ——
 * 组件被路由卸载后草稿仍在，切回来时从仓库取初值。
 *
 * 现在值用 ref 保存最新引用再算 updater，而不是把写仓库塞进 setState 的 updater 里：
 * 后者在 StrictMode 下会被调用两次（虽然幂等，但把副作用放在 state updater 里是错的）。
 */
export function useSectionDraft<T>(key: string) {
  const [value, setValue] = useState<T | undefined>(() => readDraft<T>(key))
  const latest = useRef(value)

  useEffect(() => {
    latest.current = value
  }, [value])

  const update = useCallback(
    (next: Updater<T>) => {
      const resolved = typeof next === 'function' ? (next as (p: T | undefined) => T | undefined)(latest.current) : next
      latest.current = resolved
      setValue(resolved)
      writeDraft(key, resolved)
    },
    [key],
  )

  return [value, update] as const
}

/** 未保存改动的分区数：订阅仓库版本号即可，不需要草稿内容。 */
export function useUnsavedCount(): number {
  return useSyncExternalStore(
    subscribeDrafts,
    () => draftKeys().length,
    () => 0,
  )
}

/** 某个分区是否有未保存改动（导航角标用）。 */
export function useHasDraft(key: string): boolean {
  useSyncExternalStore(subscribeDrafts, draftsVersion, () => 0)
  return draftKeys().includes(key)
}

/** 有草稿的分区集合（窄屏下拉的未保存标记用；订阅版本号，内容每次渲染取最新）。 */
export function useDraftKeySet(): ReadonlySet<string> {
  useSyncExternalStore(subscribeDrafts, draftsVersion, () => 0)
  return new Set(draftKeys())
}
