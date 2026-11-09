import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Field } from '../../src/ember/ui/Field'
import { Input } from '../../src/ember/ui/Input'
import { Select } from '../../src/ember/ui/Select'
import { nextFocusIndex, trapDecision, FOCUSABLE_SELECTOR } from '../../src/ember/lib/overlayFocus'

/**
 * spec 005 / UI 计划 W1（A1）：Field 的错误文案必须和控件绑在一起。
 *
 * 改之前 error 只是一个裸 <p>，控件既没有 aria-invalid 也没有 aria-describedby：
 * 读屏用户听到的是"输入框"，听不到"这个值不合法，原因是……"。全仓
 * aria-describedby 命中 0 次就是这条缺陷的直接证据。
 */

describe('Field', () => {
  it('links the error message to the control with aria-describedby and aria-invalid', () => {
    const html = renderToStaticMarkup(
      <Field label="视频链接" htmlFor="url" error="链接格式不对">
        <Input id="url" />
      </Field>,
    )

    expect(html).toContain('aria-invalid="true"')
    // 错误节点与控件的指向必须是同一个 id。
    const describedBy = /aria-describedby="([^"]+)"/.exec(html)?.[1]
    expect(describedBy).toBeTruthy()
    expect(html).toContain(`id="${describedBy}"`)
    expect(html).toContain('链接格式不对')
  })

  it('binds a hint too, but leaves aria-invalid off when there is no error', () => {
    const html = renderToStaticMarkup(
      <Field label="并发数" htmlFor="parallel" hint="1-8">
        <Input id="parallel" />
      </Field>,
    )

    const describedBy = /aria-describedby="([^"]+)"/.exec(html)?.[1]
    expect(describedBy).toBeTruthy()
    expect(html).toContain(`id="${describedBy}"`)
    expect(html).not.toContain('aria-invalid="true"')
  })

  it('applies the same wiring to a select', () => {
    const html = renderToStaticMarkup(
      <Field label="清晰度" htmlFor="quality" error="必填">
        <Select id="quality" options={[{ value: 'a', label: 'A' }]} />
      </Field>,
    )

    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('aria-describedby=')
  })

  it('generates an id for the control when htmlFor is omitted, so the label still points somewhere', () => {
    const html = renderToStaticMarkup(
      <Field label="备注">
        <Input />
      </Field>,
    )

    const htmlFor = /<label[^>]*for="([^"]+)"/.exec(html)?.[1]
    expect(htmlFor).toBeTruthy()
    expect(html).toContain(`id="${htmlFor}"`)
  })
})

describe('nextFocusIndex（焦点陷阱的回绕规则）', () => {
  it('moves forward and wraps at the end', () => {
    expect(nextFocusIndex(0, 3)).toBe(1)
    expect(nextFocusIndex(2, 3)).toBe(0)
  })

  it('moves backward and wraps at the start', () => {
    expect(nextFocusIndex(0, 3, { shift: true })).toBe(2)
    expect(nextFocusIndex(1, 3, { shift: true })).toBe(0)
  })

  it('enters the list when focus sits on the panel itself', () => {
    expect(nextFocusIndex(-1, 3)).toBe(0)
    expect(nextFocusIndex(-1, 3, { shift: true })).toBe(2)
  })

  it('reports no target for an empty panel', () => {
    expect(nextFocusIndex(-1, 0)).toBe(-1)
  })

  it('traps Tab at the last element and Shift+Tab at the first', () => {
    // 只有边界才拦截：中间位置交给浏览器默认行为。
    expect(trapDecision({ currentIndex: 2, count: 3, shift: false })).toEqual({
      prevent: true,
      focusIndex: 0,
    })
    expect(trapDecision({ currentIndex: 0, count: 3, shift: true })).toEqual({
      prevent: true,
      focusIndex: 2,
    })
    expect(trapDecision({ currentIndex: 1, count: 3, shift: false })).toEqual({
      prevent: false,
      focusIndex: 2,
    })
    expect(trapDecision({ currentIndex: 1, count: 3, shift: true })).toEqual({
      prevent: false,
      focusIndex: 0,
    })
  })

  it('does not trap when the panel has nothing focusable', () => {
    expect(trapDecision({ currentIndex: -1, count: 0, shift: false })).toEqual({
      prevent: false,
      focusIndex: -1,
    })
  })

  it('keeps the focusable selector free of disabled and hidden inputs', () => {
    expect(FOCUSABLE_SELECTOR).toContain('button:not([disabled])')
    expect(FOCUSABLE_SELECTOR).toContain('input:not([disabled])')
    expect(FOCUSABLE_SELECTOR).toContain('[tabindex]:not([tabindex="-1"])')
  })
})
