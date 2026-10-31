import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { EmberApp } from './ember/EmberApp'
import { EmberI18nProvider } from './ember/i18n'
import { EmberToaster } from './ember/shell/EmberToaster'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <EmberI18nProvider>
      <EmberApp />
      <EmberToaster />
    </EmberI18nProvider>
  </StrictMode>
)
