import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useCheckBackend } from '@/hooks/useCheckBackend'
import { systemCheck } from '@/services/system'
import { StartupScreen } from '@/ember/startup/StartupScreen'
import { ErrorBoundary } from '@/ember/shell/ErrorBoundary'
import { WorkspacePage } from '@/ember/pages/WorkspacePage'
import { NotFoundPage } from '@/ember/pages/NotFoundPage'
import { Spinner } from '@/ember/ui/Spinner'
import { useEffect } from 'react'

const SettingsPage = lazy(() => import('@/ember/pages/settings/SettingsPage'))
const OnboardingPage = lazy(() =>
  import('@/ember/pages/OnboardingPage').then(module => ({ default: module.OnboardingPage })),
)

/**
 * Ember application root. Keeps the two long-standing runtime concerns in one
 * place — waiting for the backend to initialise, and running the system check
 * once it has — and hands everything else to the router.
 */
export function EmberApp() {
  const { loading, initialized, failed, lastError, reason, retry } = useCheckBackend()

  useEffect(() => {
    if (initialized) void systemCheck()
  }, [initialized])

  if (!initialized) {
    return (
      <StartupScreen
        loading={loading}
        failed={failed}
        lastError={lastError}
        reason={reason}
        onRetry={retry}
      />
    )
  }

  return (
    <>
      {/* Outermost render guard: without it a throw below the router blanks the page. */}
      <ErrorBoundary scope="router">
        <BrowserRouter>
          <Suspense
            fallback={
              <div className="grid h-screen place-items-center">
                <Spinner className="size-5 text-primary" />
              </div>
            }
          >
            <Routes>
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route
                path="/"
                element={<WorkspacePage />}
              />
              <Route path="/settings" element={<SettingsPage />}>
                <Route index element={<Navigate to="general" replace />} />
                <Route path="*" element={<Navigate to="general" replace />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ErrorBoundary>
    </>
  )
}
