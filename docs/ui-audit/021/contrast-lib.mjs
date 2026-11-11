export function parseThemes(css) {
  const grab = (selector) => {
    const start = css.indexOf(selector + ' {')
    if (start < 0) throw new Error('selector not found: ' + selector)
    const end = css.indexOf('\n}', start)
    const block = css.slice(start, end)
    const vars = {}
    for (const m of block.matchAll(/--([\w-]+):\s*([^;]+);/g)) vars[m[1]] = m[2].trim()
    return vars
  }
  return { light: grab(':root'), dark: grab('.dark') }
}

export function luminance(hex) {
  const h = hex.replace('#', '')
  const rgb = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
  const lin = rgb.map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

export function contrast(fg, bg) {
  const a = luminance(fg)
  const b = luminance(bg)
  const [hi, lo] = a > b ? [a, b] : [b, a]
  return (hi + 0.05) / (lo + 0.05)
}