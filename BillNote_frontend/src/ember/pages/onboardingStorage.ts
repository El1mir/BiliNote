/**
 * First-run bookkeeping, kept out of OnboardingGuard.tsx so that file exports
 * nothing but a component (React Fast Refresh can only hot-swap such a file).
 */
export const ONBOARDING_STORAGE_KEY = 'bilinote-onboarded'

export function hasCompletedOnboarding(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDING_STORAGE_KEY) === '1'
  } catch {
    // Storage disabled: never trap the user in setup they cannot complete.
    return true
  }
}
