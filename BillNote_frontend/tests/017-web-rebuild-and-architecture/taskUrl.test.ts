import { describe, expect, it } from 'vitest'
import {
  normalizeTaskId,
  readTaskId,
  shouldProbeTask,
  taskSelectionStatus,
  writeTaskId,
} from '../../src/ember/lib/taskUrl'

/**
 * S2 状态可寻址：当前任务放进地址栏。
 *
 * 这些用例钉住的是「地址栏是唯一来源」这条规则本身 —— 读、写、以及地址栏里的
 * id 在内存里找不到时到底该等、该问、还是判失效。纯字符串与纯函数，两种 Router
 * （BrowserRouter 的 `?task=` 与 HashRouter 的 `#/?task=`）拿到的 search 串形状
 * 相同，所以这份实现与用例对两者都成立，浏览器侧再用真机深链各验一次。
 */

describe('taskUrl 读写', () => {
  it('从 search 串里读出 task 参数，兼容带不带前缀问号', () => {
    expect(readTaskId('?task=abc123')).toBe('abc123')
    expect(readTaskId('task=abc123')).toBe('abc123')
    expect(readTaskId('?foo=1&task=abc123&bar=2')).toBe('abc123')
  })

  it('没有 task、空值、纯空白一律当作未选中', () => {
    expect(readTaskId('')).toBeNull()
    expect(readTaskId('?')).toBeNull()
    expect(readTaskId('?task=')).toBeNull()
    expect(readTaskId('?task=%20%20')).toBeNull()
    expect(readTaskId('?other=1')).toBeNull()
    expect(normalizeTaskId('  ')).toBeNull()
    expect(normalizeTaskId(undefined)).toBeNull()
  })

  it('id 两端的空白会被裁掉，URL 编码能往返', () => {
    expect(readTaskId('?task=%20abc%20')).toBe('abc')
    expect(writeTaskId('', 'a b')).toBe('?task=a+b')
    expect(readTaskId(writeTaskId('', 'a b'))).toBe('a b')
  })

  it('写入时保留其它查询参数，顺序稳定', () => {
    expect(writeTaskId('?keep=1', 'tid')).toBe('?keep=1&task=tid')
    expect(writeTaskId('?task=old&keep=1', 'new')).toBe('?task=new&keep=1')
  })

  it('传 null / 空白表示取消选中，且把参数摘干净', () => {
    expect(writeTaskId('?task=tid', null)).toBe('')
    expect(writeTaskId('?task=tid&keep=1', '')).toBe('?keep=1')
    expect(writeTaskId('', null)).toBe('')
  })
})

describe('taskUrl 选中状态判定', () => {
  const base = { listLoading: false, knownIds: ['known-1'], probe: 'unprobed' as const }

  it('地址栏没有 id 就是未选中', () => {
    expect(taskSelectionStatus({ ...base, urlTaskId: null })).toBe('none')
    expect(taskSelectionStatus({ ...base, urlTaskId: '  ' })).toBe('none')
  })

  it('id 在列表里就是选中，与 probe 无关', () => {
    expect(taskSelectionStatus({ ...base, urlTaskId: 'known-1' })).toBe('selected')
    expect(taskSelectionStatus({ ...base, urlTaskId: 'known-1', probe: 'missing' })).toBe('selected')
  })

  it('列表还在加载时不下结论 —— 合法深链不能被误判成失效', () => {
    expect(taskSelectionStatus({ ...base, listLoading: true, urlTaskId: 'deep' })).toBe('waiting')
  })

  it('列表加载完仍没有、也没问过后端：先等这次单独查询', () => {
    expect(taskSelectionStatus({ ...base, urlTaskId: 'deep' })).toBe('waiting')
    expect(shouldProbeTask({ status: 'waiting', listLoading: false, probe: 'unprobed' })).toBe(true)
  })

  it('单独问过之后：查到就是选中，查不到才是失效', () => {
    expect(taskSelectionStatus({ ...base, urlTaskId: 'deep', probe: 'found' })).toBe('selected')
    expect(taskSelectionStatus({ ...base, urlTaskId: 'deep', probe: 'missing' })).toBe('missing')
  })

  it('加载中或已经有结论时都不再发起查询，避免死循环', () => {
    expect(shouldProbeTask({ status: 'waiting', listLoading: true, probe: 'unprobed' })).toBe(false)
    expect(shouldProbeTask({ status: 'waiting', listLoading: false, probe: 'found' })).toBe(false)
    expect(shouldProbeTask({ status: 'missing', listLoading: false, probe: 'unprobed' })).toBe(false)
    expect(shouldProbeTask({ status: 'selected', listLoading: false, probe: 'unprobed' })).toBe(false)
  })
})
