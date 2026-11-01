import { RotateCcw } from 'lucide-react'
import { useI18n } from '@/ember/i18n/context'
import { Button } from '@/ember/ui/Button'

type RetryFailedActionProps = {
  disabled: boolean
  failedFilterActive: boolean
  scope: 'all' | 'group'
  onRetry: () => void
}

/** The endpoint retries every failure in scope; selection prevents accidental empty-scope calls. */
export function RetryFailedAction({ disabled, failedFilterActive, scope, onRetry }: RetryFailedActionProps) {
  const { t } = useI18n()

  return (
    <Button
      size="sm"
      variant="secondary"
      disabled={disabled || !failedFilterActive}
      onClick={onRetry}
      title={t('history.retryScopeHint')}
      data-retry-scope={scope}
    >
      <RotateCcw className="size-3.5" />
      {t('history.retryFailed')}
    </Button>
  )
}
