import { beforeEach, describe, expect, it } from 'vitest'
import { useTaskStore } from '../../src/store/taskStore'

describe('taskStore revision ordering', () => {
  beforeEach(() => {
    useTaskStore.setState({ tasks: [], currentTaskId: null })
  })

  it('keeps the newest status when older or duplicate revisions arrive', () => {
    const store = useTaskStore.getState()
    store.addPendingTask('revision-task', 'bilibili', { video_url: 'https://example.test/video' } as never)
    store.updateTaskStatus('revision-task', {
      status: 'TRANSCRIBING',
      revision: 7,
      stage: 'transcribing',
      progress: 70,
      message: 'newest update',
      detail: { current: 7, total: 10 },
    })

    const newest = useTaskStore.getState().tasks[0]
    expect(newest).toMatchObject({
      status: 'TRANSCRIBING',
      revision: 7,
      stage: 'transcribing',
      progress: 70,
      message: 'newest update',
      detail: { current: 7, total: 10 },
    })

    useTaskStore.getState().updateTaskStatus('revision-task', {
      status: 'DOWNLOADING',
      revision: 6,
      stage: 'downloading_audio',
      progress: 40,
      message: 'late stale update',
      detail: { current: 4, total: 10 },
    })
    useTaskStore.getState().updateTaskStatus('revision-task', {
      status: 'SUMMARIZING',
      revision: 7,
      stage: 'summarizing',
      progress: 80,
      message: 'duplicate revision update',
      detail: { current: 8, total: 10 },
    })

    expect(useTaskStore.getState().tasks[0]).toEqual(newest)
  })
})
