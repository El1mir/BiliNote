import { Toaster } from 'react-hot-toast'

/**
 * Ember-tuned toasts.
 *
 * The app talks to one toast library only — \`react-hot-toast\` — because the
 * preserved data layer (src/services, src/hooks) raises its own toasts from
 * there. Mounting a second system (sonner) alongside it meant half the
 * notifications were styled and half were invisible.
 *
 * Motion: enter from below with a small rise, exit faster than entry, so the
 * surface feels responsive without ever starting from scale(0).
 */
export function EmberToaster() {
  return (
    <Toaster
      position="bottom-right"
      gutter={10}
      containerClassName="ember-toaster"
      toastOptions={{
        duration: 4000,
        className:
          'rounded-surface border border-line bg-canvas px-3.5 py-2.5 text-small text-ink shadow-float',
        success: { className: 'border-ok/30', iconTheme: { primary: '#16a34a', secondary: '#ffffff' } },
        error: { className: 'border-danger/30', iconTheme: { primary: '#dc2626', secondary: '#ffffff' } },
      }}
    />
  )
}
