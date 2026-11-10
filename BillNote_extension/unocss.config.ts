import { defineConfig } from 'unocss/vite'
import { presetAttributify, presetIcons, presetUno, transformerDirectives } from 'unocss'

/* UnoCSS theme mirrors BillNote_frontend/src/ember/tokens.css. Every colour is
   a CSS variable (see src/styles/tokens.css), so dark mode and the Web app stay
   in sync without a shared package. */
export default defineConfig({
  presets: [
    presetUno(),
    presetAttributify(),
    presetIcons(),
  ],
  transformers: [transformerDirectives()],
  theme: {
    colors: {
      canvas: 'var(--canvas)',
      surface: 'var(--surface)',
      raised: 'var(--raised)',
      'raised-hover': 'var(--raised-hover)',
      ink: 'var(--ink)',
      'ink-soft': 'var(--ink-soft)',
      'ink-muted': 'var(--ink-muted)',
      line: 'var(--line)',
      'line-strong': 'var(--line-strong)',
      accent: 'var(--accent)',
      'accent-hover': 'var(--accent-hover)',
      'accent-soft': 'var(--accent-soft)',
      'on-accent': 'var(--on-accent)',
      success: 'var(--success)',
      'success-soft': 'var(--success-soft)',
      warning: 'var(--warning)',
      'warning-soft': 'var(--warning-soft)',
      danger: 'var(--danger)',
      'danger-soft': 'var(--danger-soft)',
      'on-danger': 'var(--on-danger)',
      info: 'var(--info)',
      'info-soft': 'var(--info-soft)',
    },
    radius: {
      inline: '4px',
      control: '8px',
      surface: '12px',
    },
    fontFamily: {
      sans: 'var(--font-sans)',
      mono: 'var(--font-mono)',
    },
  },
})
