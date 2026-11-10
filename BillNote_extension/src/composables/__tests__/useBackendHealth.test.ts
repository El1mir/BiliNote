import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useBackendHealth } from '../useBackendHealth'

vi.mock('~/logic/storage', () => ({
  settings: { value: { backendUrl: 'http://localhost:8483' } },
  settingsReady: Promise.resolve(),
}))

function mountProbe() {
  let api: ReturnType<typeof useBackendHealth> | undefined
  const Comp = defineComponent({
    setup() {
      api = useBackendHealth(60_000)
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  return { wrapper, api: api! }
}

const flush = () => new Promise(r => setTimeout(r, 0))

describe('useBackendHealth', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('marks the backend ok on a 2xx sys_check', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    const { wrapper, api } = mountProbe()
    await flush()
    expect(api.state.value).toBe('ok')
    wrapper.unmount()
  })

  it('marks the backend down on a non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 503 })))
    const { wrapper, api } = mountProbe()
    await flush()
    expect(api.state.value).toBe('down')
    expect(api.detail.value).toContain('503')
    wrapper.unmount()
  })

  it('marks the backend down when the request throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connect ECONNREFUSED')))
    const { wrapper, api } = mountProbe()
    await flush()
    expect(api.state.value).toBe('down')
    expect(api.detail.value).toContain('ECONNREFUSED')
    wrapper.unmount()
  })
})
