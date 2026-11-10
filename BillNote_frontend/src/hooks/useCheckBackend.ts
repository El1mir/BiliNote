import { useCallback, useEffect, useRef, useState } from 'react'

// 后端就绪检测的几个时间常量
// - 总等待上限 60s：超过这个时间没就绪就切「启动失败」UI，
//   不再像旧实现 while(true) 无限转
// - 轮询间隔 2s：比旧的 10s 更敏感，桌面端 sidecar 5-15s 解压期内能尽快感知就绪
// - 单次请求超时 5s，避免连接 hang 拖到下一轮
const TOTAL_TIMEOUT_MS = 60_000
const POLL_INTERVAL_MS = 2_000
const PROBE_TIMEOUT_MS = 5_000


// 直接用 fetch 而非 utils/request 的共享 axios：那个 axios 装了全局 toast 拦截器，
// 启动期每次 /sys_check 失败都会弹一个红色 toast，2s 一次轮询会叠出十几个。
function getBackendBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL
  return (fromEnv && fromEnv.length > 0 ? fromEnv : '/api').replace(/\/$/, '')
}

/**
 * 启动失败的结构化原因。hook 只给出 code + 原始细节，人话文案由前端按当前语言渲染 ——
 * 否则失败页在英文界面里会蹦出一句中文（旧实现把整句话拼在 hook 里）。
 */
export type BootFailureCode = 'timeout' | 'connect' | 'http' | 'terminated' | 'startup_timeout' | 'unknown'

export interface BootFailureReason {
  code: BootFailureCode
  detail?: string
}

/** 探活结果：ok=就绪；ready=后端确实答复了（哪怕业务码非 0）；err=网络层原因。 */
interface ProbeResult {
  ok: boolean
  ready: boolean
  err?: string
  code: BootFailureCode
  detail?: string
}

/**
 * 探测一次后端。
 *
 * 判定口径刻意放宽：**只要后端答复了 HTTP 2xx 就认为「已就绪」**，不再要求
 * `code === 0`。原因是一次误判为「网络异常」的现场排查（2026-10-04）：
 * `/sys_check` 是装配级检查，ffmpeg / whisper / db 任何一项不达标它都可能返回
 * 非 0 业务码。旧的 `json?.code === 0` 会把这种「后端活得好好的、只是某项检查
 * 没过」也判成未就绪，前端于是整屏停在「网络异常」，用户完全无从下手。
 * 真正的健康细节交给 `/sys_health` + StartupBanner / 设置页展示。
 */
async function probeSysCheck(): Promise<ProbeResult> {
  const url = `${getBackendBase()}/sys_check`
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS)
  try {
    const res = await fetch(url, { signal: ctrl.signal })
    if (!res.ok) {
      return { ok: false, ready: false, code: 'http', detail: `HTTP ${res.status}`, err: `后端返回 HTTP ${res.status}` }
    }
    // 2xx 就算答复了：业务码细节交给 /sys_health，别在这里卡启动。
    const json = await res.json().catch(() => null)
    // 2xx 且能解析出 code === 0 → 完全就绪；2xx 但业务码非 0 → 仍然算「后端在线」。
    return { ok: json?.code === 0, ready: true, code: 'unknown' }
  } catch (e) {
    // AbortError 是本地 5s 超时；TypeError: Failed to fetch 是连不上 / 被代理挡掉。
    // 失败页要直接展示这句，所以给出人话而不是裸的 e.name（旧实现只留 "TypeError"，
    // 用户看到等于没看到）。
    if (e instanceof Error && e.name === 'AbortError') {
      return { ok: false, ready: false, code: 'timeout', detail: '5s', err: '探测超时（后端未在 5s 内响应）' }
    }
    const detail = e instanceof Error ? `${e.name}: ${e.message}` : String(e)
    return { ok: false, ready: false, code: 'connect', detail, err: `无法连接到后端服务（${detail}）` }
  } finally {
    clearTimeout(t)
  }
}

interface Status {
  loading: boolean
  initialized: boolean
  failed: boolean
  lastError: string | null
  /** 结构化失败原因；失败页按当前语言渲染它，lastError 只作兜底。 */
  reason: BootFailureReason | null
}

interface BackendCheck extends Status {
  retry: () => void
}

const initialStatus: Status = {
  loading: true,
  initialized: false,
  failed: false,
  lastError: null,
  reason: null,
}

/**
 * 后端就绪检测。
 *
 * HTTP 轮询 /sys_check 直到成功、或在 TOTAL_TIMEOUT_MS 内一直失败。
 *
 * 桌面端 sidecar 已移除（T-066）：不再有 backend-ready / backend-terminated
 * 事件通道，就绪与否只有 HTTP 一个真源。
 */
export const useCheckBackend = (): BackendCheck => {
  const [status, setStatus] = useState<Status>(initialStatus)
  // tick 用来强制重启 useEffect（retry 时 +1），不引入 ref 互斥逻辑的复杂性
  const [tick, setTick] = useState(0)
  // 标记当前 effect 是否已 settle（避免后到的事件覆盖已确定的成功/失败态）
  const settledRef = useRef(false)

  const retry = useCallback(() => {
    settledRef.current = false
    setStatus(initialStatus)
    setTick(t => t + 1)
  }, [])

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null
    let pollTimerId: ReturnType<typeof setTimeout> | null = null
    let cancelled = false

    const markReady = () => {
      if (cancelled || settledRef.current) return
      settledRef.current = true
      setStatus({ loading: false, initialized: true, failed: false, lastError: null, reason: null })
    }

    const poll = async () => {
      if (cancelled || settledRef.current) return
      const probe = await probeSysCheck()
      if (cancelled || settledRef.current) return
      // 后端只要答复过（哪怕某项装配检查没通过）就放行进主界面，
      // 否则一次 `/sys_check` 非 0 就会让用户整屏卡在「网络异常」。
      if (probe.ready) {
        markReady()
        return
      }
      // 真·网络层失败：不报 toast、不抛错，继续轮询，但把原始原因记下来，
      // 这样 60s 后失败态里能显示「连不上」还是「超时」，而不是笼统一句网络异常。
      setStatus(s => ({
        ...s,
        lastError: probe.err || '后端尚未响应',
        reason: { code: probe.code, detail: probe.detail || probe.err },
      }))
      pollTimerId = setTimeout(poll, POLL_INTERVAL_MS)
    }

    // 总超时兜底：带上最后一轮的真实原因，方便用户自己定位。
    timeoutId = setTimeout(() => {
      // 注意：settle 标记必须在 updater 之外完成。React StrictMode 会双调用
      // updater 以检测副作用，若在 updater 内改 ref，第二次调用就会走
      // `return s` 分支，把已经算好的失败态丢掉 —— 结果就是开发环境永远
      // 停在「正在启动后端服务」。
      if (cancelled || settledRef.current) return
      settledRef.current = true
      setStatus(s => ({
        loading: false,
        initialized: false,
        failed: true,
        lastError: `后端 ${TOTAL_TIMEOUT_MS / 1000}s 内未就绪（${s.lastError || '无响应'}），请检查后端是否已启动，或点「重试」`,
        reason: {
          code: s.reason?.code === 'connect' ? 'connect' : 'timeout',
          detail: s.reason?.detail || s.lastError || undefined,
        },
      }))
    }, TOTAL_TIMEOUT_MS)

    // 立刻开始第一轮轮询
    poll()

    return () => {
      cancelled = true
      if (timeoutId) clearTimeout(timeoutId)
      if (pollTimerId) clearTimeout(pollTimerId)

    }
  }, [tick])

  return { ...status, retry }
}
