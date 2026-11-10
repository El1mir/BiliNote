import { onMounted, onUnmounted, ref } from 'vue'
import { settings, settingsReady } from '~/logic/storage'

export type BackendState = 'checking' | 'ok' | 'down'

/**
 * Reachability probe for the configured backend. The popup and the side panel
 * are useless when the backend is not running, and both used to render an empty
 * shell with no explanation — so both surfaces show an explicit "后端不可用"
 * state instead of an empty result.
 */
export function useBackendHealth(intervalMs = 15000) {
  const state = ref<BackendState>('checking')
  const detail = ref('')
  let timer: ReturnType<typeof setInterval> | null = null

  async function probe() {
    await settingsReady
    const base = (settings.value?.backendUrl || 'http://localhost:8483').replace(/\/$/, '')
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 4000)
    try {
      const res = await fetch(`${base}/api/sys_check`, { signal: controller.signal })
      state.value = res.ok ? 'ok' : 'down'
      detail.value = res.ok ? '' : `HTTP ${res.status}`
    }
    catch (e) {
      state.value = 'down'
      detail.value = (e as Error).message
    }
    finally {
      clearTimeout(timeout)
    }
  }

  onMounted(() => {
    probe()
    timer = setInterval(probe, intervalMs)
  })
  onUnmounted(() => {
    if (timer)
      clearInterval(timer)
  })

  return { state, detail, probe }
}
