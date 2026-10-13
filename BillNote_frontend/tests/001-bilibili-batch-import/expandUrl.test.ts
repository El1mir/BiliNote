import { describe, expect, it, vi } from 'vitest'

const { post } = vi.hoisted(() => ({
  post: vi.fn(),
}))

vi.mock('@/utils/request', () => ({
  default: { post },
}))

describe('expandUrl', () => {
  it('uses a long request timeout for large collections', async () => {
    post.mockResolvedValue({ type: 'collection', videos: [] })
    const { expandUrl } = await import('../../src/services/note')
    const url = 'https://space.bilibili.com/14229967/lists/1533671?type=season'

    await expandUrl(url)

    expect(post).toHaveBeenCalledWith('/expand', { url }, { timeout: 120_000 })
  })
})
