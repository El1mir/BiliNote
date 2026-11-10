import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { EmberApp } from './ember/EmberApp'
import { EmberI18nProvider } from './ember/i18n'
import { EmberToaster } from './ember/shell/EmberToaster'
import { initTheme } from './ember/theme/theme'

// Paint the stored palette before the first render: a theme swap after mount
// would flash the default light background on every reload.
initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <EmberI18nProvider>
      <EmberApp />
      <EmberToaster />
    </EmberI18nProvider>
  </StrictMode>
)
