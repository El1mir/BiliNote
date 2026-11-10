import { describe, expect, it } from 'vitest'
import { canSaveProxy, proxyUrlError } from '../../src/ember/pages/settings/proxyUrl'

/**
 * T-062 / 上游 UI 计划 §4 F2：代理分区接 /proxy_config。
 *
 * 后端把配置值写进 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY，所以这里锁的是"什么算合法"：
 * 打开代理却没地址，等于保存了一个"开了但无效"的配置，会让 yt-dlp 与模型请求
 * 的失败变得难以归因 —— 这种情况必须拦住保存。
 */

describe('proxyUrlError', () => {
  it('accepts an http or https endpoint', () => {
    expect(proxyUrlError('http://127.0.0.1:7890')).toBeNull()
    expect(proxyUrlError('https://proxy.example.com:8443')).toBeNull()
    expect(proxyUrlError('  http://127.0.0.1:7890  ')).toBeNull()
  })

  it('rejects a bare host:port, which the HTTP clients disagree about', () => {
    expect(proxyUrlError('127.0.0.1:7890')).toBe('scheme')
  })

  it('rejects an empty address', () => {
    expect(proxyUrlError('   ')).toBe('empty')
  })

  it('rejects an unparseable address', () => {
    expect(proxyUrlError('http://')).toBe('malformed')
  })
})

describe('canSaveProxy', () => {
  it('blocks saving while the proxy is on without a usable address', () => {
    expect(canSaveProxy({ enabled: true, url: '' })).toBe(false)
    expect(canSaveProxy({ enabled: true, url: '127.0.0.1:7890' })).toBe(false)
    expect(canSaveProxy({ enabled: true, url: 'http://127.0.0.1:7890' })).toBe(true)
  })

  it('lets a disabled proxy keep any address for later', () => {
    // 关闭时代理会保留地址，下次打开不必重填；空地址也同样允许保存。
    expect(canSaveProxy({ enabled: false, url: 'http://127.0.0.1:7890' })).toBe(true)
    expect(canSaveProxy({ enabled: false, url: '' })).toBe(true)
  })
})
