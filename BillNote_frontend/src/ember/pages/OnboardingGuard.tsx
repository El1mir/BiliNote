import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { hasCompletedOnboarding } from '@/ember/pages/onboardingStorage'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

/**
 * Desktop first-run gate.
 *
 * Only the Tauri build is intercepted — a browser deployment was configured by
 * whoever installed it, and interrupting a web user with desktop setup steps
 * would be noise.
 */
export function OnboardingGuard({ children }: { children: ReactNode }) {
  if (!isTauri) return <>{children}</>
  if (!hasCompletedOnboarding()) return <Navigate to="/onboarding" replace />
  return <>{children}</>
}
