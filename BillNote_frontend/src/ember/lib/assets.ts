/**
 * Where the backend's static media lives.
 *
 * Notes embed screenshots as root-relative paths (`/static/screenshots/x.jpg`)
 * because that is what the backend can know about itself. The browser resolves
 * such a path against the page origin, which is only correct when the frontend
 * and the API share one origin (dev server proxy, nginx). In the desktop build
 * the page origin is the app asset protocol, so the request goes nowhere and
 * every screenshot shows up broken.
 *
 * The pre-rewrite reader prefixed these paths with the API origin; this module
 * restores that, and keeps one definition of it for every consumer.
 */
const API_BASE_URL = String(import.meta.env.VITE_API_BASE_URL ?? '')

/** Origin that serves `/static`: the API base with a trailing `/api` removed. */
export const ASSET_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, '').replace(/\/+$/, '')

/**
 * Resolve an image/link target from note markdown.
 *
 * Absolute URLs, protocol-relative URLs and data/blob URIs are left alone:
 * they already name their own host. Only root-relative paths are re-anchored.
 */
export function resolveAssetUrl(src: string | undefined | null): string | undefined {
  if (!src) return undefined
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith('//')) return src
  if (src.startsWith('/')) return ASSET_ORIGIN + src
  return src
}
