import { describe, expect, it, vi } from 'vitest'
import type { RetryFailedResult } from '../../src/services/note'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nContext, type I18nValue } from '../../src/ember/i18n/context'
import { dictionaries, format } from '../../src/ember/i18n/strings'
import type { Locale, MessageKey } from '../../src/ember/i18n/strings'
import { RetryFailedAction } from '../../src/ember/features/workspace/RetryFailedAction'
import type { Task } from '../../src/store/taskStore'
import { retryResultKind, retryScopeForGroup, retrySelectedFailedTasks } from '../../src/ember/features/workspace/retryFailed'
import { UNGROUPED_ID } from '../../src/services/noteGroup'

const task = (id: string, status: string, groupId: string | null = 'group-a') =>
  ({ id, status, groupId }) as Task

const result = (overrides: Partial<RetryFailedResult> = {}): RetryFailedResult => ({
  scope: 'group',
  group_id: 'group-a',
  candidates: 1,
  requeued: ['failed-1'],
  skipped: [],
  missing: [],
  ...overrides,
})

const renderAction = (
  disabled: boolean,
  scope: 'all' | 'group',
  locale: Locale = 'zh-CN',
  failedFilterActive = true,
) => {
  const value: I18nValue = {
    locale,
    setLocale: () => {},
    t: (key: MessageKey, values?: Record<string, string | number>) =>
      format(dictionaries[locale][key] ?? key, values),
  }
  return renderToStaticMarkup(
    <I18nContext.Provider value={value}>
      <RetryFailedAction disabled={disabled} failedFilterActive={failedFilterActive} scope={scope} onRetry={() => {}} />
    </I18nContext.Provider>,
  )
}

describe('batch failed-task retry', () => {
  it('renders a scope-labeled, disabled-until-selected retry control in both locales', () => {
    const allHtml = renderAction(true, 'all')
    const groupHtml = renderAction(false, 'group', 'en-US')

    expect(allHtml).toContain('重试范围内失败任务')
    expect(allHtml).toContain('title="勾选至少一个失败任务后，将重试当前范围内所有可重试的失败任务"')
    expect(allHtml).toContain('data-retry-scope="all"')
    expect(allHtml).toContain('disabled=""')
    expect(groupHtml).toContain('Retry failed tasks in scope')
    expect(groupHtml).toContain('data-retry-scope="group"')
    expect(groupHtml).not.toContain('disabled=""')
    expect(renderAction(false, 'all', 'zh-CN', false)).toContain('disabled=""')
  })
  it('maps all, selected group, and ungrouped view to the existing API scope', () => {
    expect(retryScopeForGroup(null)).toEqual({ scope: 'all', groupId: null })
    expect(retryScopeForGroup('group-a')).toEqual({ scope: 'group', groupId: 'group-a' })
    expect(retryScopeForGroup(UNGROUPED_ID)).toEqual({ scope: 'group', groupId: null })
  })

  it('does not call the API or refresh for empty selection or only non-failed selections', async () => {
    const retry = vi.fn(async () => result())
    const refresh = vi.fn(async () => {})

    await expect(retrySelectedFailedTasks([task('success-1', 'SUCCESS')], [], 'all', null, retry, refresh)).resolves.toBeNull()
    await expect(retrySelectedFailedTasks([task('success-1', 'SUCCESS')], ['success-1'], 'all', null, retry, refresh)).resolves.toBeNull()
    expect(retry).not.toHaveBeenCalled()
    expect(refresh).not.toHaveBeenCalled()
  })

  it('calls the scoped retry API and refreshes after at least one selected failed task', async () => {
    const retry = vi.fn(async () => result())
    const refresh = vi.fn(async () => {})
    const tasks = [task('failed-1', 'FAILED'), task('success-1', 'SUCCESS')]

    const response = await retrySelectedFailedTasks(tasks, ['success-1', 'failed-1'], 'group', 'group-a', retry, refresh)

    expect(response?.requeued).toEqual(['failed-1'])
    expect(retry).toHaveBeenCalledWith('group', 'group-a')
    expect(refresh).toHaveBeenCalledOnce()
  })

  it('propagates API failures so the Workspace can show an error toast', async () => {
    const error = new Error('backend unavailable')
    const retry = vi.fn().mockRejectedValue(error)
    const refresh = vi.fn(async () => {})

    await expect(
      retrySelectedFailedTasks([task('failed-1', 'FAILED')], ['failed-1'], 'all', null, retry, refresh),
    ).rejects.toBe(error)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('classifies no-retry and partial responses for user feedback', () => {
    expect(retryResultKind(result({ requeued: [] }))).toBe('none')
    expect(retryResultKind(result({ skipped: [{ task_id: 'success-1', reason: 'already complete' }] }))).toBe('partial')
    expect(retryResultKind(result({ missing: ['deleted-1'] }))).toBe('partial')
    expect(retryResultKind(result())).toBe('done')
  })
})
