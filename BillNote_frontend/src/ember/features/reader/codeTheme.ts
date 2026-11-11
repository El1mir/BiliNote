import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { ResolvedTheme } from '@/ember/theme/theme'

/**
 * Prism palette for a resolved theme.
 *
 * Kept as a pure mapping so the choice can be asserted without mounting a
 * component: a single hard-coded palette is exactly the bug this guards —
 * oneLight on a #111719 surface renders keywords nearly invisible.
 */
export function prismStyleFor(resolved: ResolvedTheme) {
  return resolved === 'dark' ? oneDark : oneLight
}
