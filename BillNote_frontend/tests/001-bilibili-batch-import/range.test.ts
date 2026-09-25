import { describe, expect, it } from 'vitest'

import { parseRangeSelection } from '../../src/utils/range'

describe('parseRangeSelection', () => {
  it('空输入返回空数组', () => {
    expect(parseRangeSelection('', 10)).toEqual([])
    expect(parseRangeSelection('   ', 10)).toEqual([])
  })

  it('单个数字', () => {
    expect(parseRangeSelection('5', 10)).toEqual([5])
  })

  it('范围 x-x', () => {
    expect(parseRangeSelection('3-6', 10)).toEqual([3, 4, 5, 6])
  })

  it('倒序范围自动纠正', () => {
    expect(parseRangeSelection('6-3', 10)).toEqual([3, 4, 5, 6])
  })

  it('逗号分隔混合', () => {
    expect(parseRangeSelection('1,3-5,9', 10)).toEqual([1, 3, 4, 5, 9])
  })

  it('去重', () => {
    expect(parseRangeSelection('2,2,1-3', 10)).toEqual([1, 2, 3])
  })

  it('裁剪到 [1, max]', () => {
    expect(parseRangeSelection('0-3', 5)).toEqual([1, 2, 3])
    expect(parseRangeSelection('3-99', 5)).toEqual([3, 4, 5])
    expect(parseRangeSelection('99', 5)).toEqual([])
  })

  it('非法片段被忽略', () => {
    expect(parseRangeSelection('abc, 3, x-y, ,4', 10)).toEqual([3, 4])
  })

  it('max 非正返回空', () => {
    expect(parseRangeSelection('1-3', 0)).toEqual([])
    expect(parseRangeSelection('1-3', -1)).toEqual([])
  })

  it('单个数字越界', () => {
    expect(parseRangeSelection('3-3', 2)).toEqual([])
    expect(parseRangeSelection('2-2', 2)).toEqual([2])
  })
})
