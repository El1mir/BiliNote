import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 分区保存的状态机（W3）：idle → saving → saved / error → idle。
 *
 * 以前保存结果只有 toast：一闪而过，失败时用户回看页面无从判断「刚才到底存没存上」。
 * 这里把状态放在分区抬头旁（SaveStatus），toast 不再承担保存结果；
 * 预览、下载、删除这类一次性动作仍用 toast，它们没有"当前状态"可留。
 *
 * 内联状态会自己回落（默认 4s），避免"已保存"永远挂在页面上。
 */
export type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export function useSaveFeedback(resetMs = 4000) {
  const [state, setState] = useState<SaveState>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => clearTimer, [clearTimer])

  /** 跑一次保存；别在 task 里再 try/catch —— 状态由这里统一收口。 */
  const run = useCallback(
    async (task: () => Promise<void>): Promise<boolean> => {
      clearTimer()
      setState('saving')
      let ok = true
      try {
        await task()
        setState('saved')
      } catch {
        ok = false
        setState('error')
      }
      timer.current = setTimeout(() => setState('idle'), resetMs)
      return ok
    },
    [clearTimer, resetMs],
  )

  return { state, saving: state === 'saving', run }
}
