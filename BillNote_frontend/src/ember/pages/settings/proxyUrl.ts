/**
 * 代理地址的校验与归一（T-062 / 上游 UI 计划 §4 F2：把 /proxy_config 接进设置页）。
 *
 * 后端 ProxyConfigManager.apply_to_env() 的值会直接写进 HTTP_PROXY / HTTPS_PROXY /
 * ALL_PROXY 环境变量并交给 httpx、yt-dlp、huggingface 下载使用，所以这里只做
 * "能不能用"的判断：必须是一个带 scheme 的 http/https 地址，不接受裸 host:port
 * （requests/httpx 对裸 host 的处理各不相同，会让"配了但没生效"变得难以解释）。
 */

export type ProxyDraft = { enabled: boolean; url: string }

/** 返回校验失败的原因 key；通过时返回 null。 */
export function proxyUrlError(url: string): 'empty' | 'scheme' | 'malformed' | null {
  const trimmed = url.trim()
  if (!trimmed) return 'empty'
  if (!/^https?:\/\//i.test(trimmed)) return 'scheme'
  try {
    const parsed = new URL(trimmed)
    if (!parsed.hostname) return 'malformed'
    return null
  } catch {
    return 'malformed'
  }
}

/**
 * 能否保存：关闭代理时不需要地址（address 会原样保留，方便下次打开）；
 * 打开时必须有一个合法地址，否则保存等于把代理置成"开了但无效"。
 */
export function canSaveProxy(draft: ProxyDraft): boolean {
  if (!draft.enabled) return true
  return proxyUrlError(draft.url) === null
}
