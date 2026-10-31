#!/usr/bin/env node
/**
 * i18n contract gate (spec 017 ticket 005).
 *
 * TypeScript already guarantees that the en-US dictionary has every key the
 * zh-CN dictionary has (Dictionary = Record<MessageKey, string>). What it
 * cannot see:
 *   1. a placeholder typo — en has {second} where zh has {seconds}, so the
 *      UI prints the literal braces;
 *   2. a copy-paste translation — the en value is still the Chinese string;
 *   3. an empty value — the key exists but renders as nothing.
 * This script fails on all three.
 *
 * Run:  node scripts/i18n-contract.cjs
 */
const path = require('node:path')
const { pathToFileURL } = require('node:url')

const ROOT = path.resolve(__dirname, '..')
const STRINGS = path.join(ROOT, 'src', 'ember', 'i18n', 'strings.ts')
const CJK = /[\u3400-\u9fff\u3040-\u30ff]/
const PLACEHOLDER = /\{(\w+)\}/g

function placeholders(value) {
  const found = new Set()
  for (const match of String(value).matchAll(PLACEHOLDER)) found.add(match[1])
  return [...found].sort()
}

async function main() {
  // Node >= 22.6 strips TypeScript types on import; the dictionaries are plain
  // data, so no transform step is needed.
  const mod = await import(pathToFileURL(STRINGS).href)
  const zh = mod.dictionaries['zh-CN']
  const en = mod.dictionaries['en-US']
  const problems = []

  for (const key of Object.keys(zh)) {
    if (!(key in en)) {
      problems.push(`missing in en-US: ${key}`)
      continue
    }
    const zhValue = String(zh[key])
    const enValue = String(en[key])
    if (!zhValue.trim()) problems.push(`empty zh-CN value: ${key}`)
    if (!enValue.trim()) problems.push(`empty en-US value: ${key}`)
    const zhSlots = placeholders(zhValue).join(',')
    const enSlots = placeholders(enValue).join(',')
    if (zhSlots !== enSlots) {
      problems.push(`placeholder mismatch: ${key} (zh: {${zhSlots}} / en: {${enSlots}})`)
    }
    if (enValue === zhValue && CJK.test(zhValue)) {
      problems.push(`untranslated (en-US still holds the zh-CN string): ${key}`)
    }
  }
  for (const key of Object.keys(en)) {
    if (!(key in zh)) problems.push(`missing in zh-CN: ${key}`)
  }

  const total = Object.keys(zh).length
  if (problems.length) {
    console.error(`i18n contract FAILED — ${problems.length} problem(s) across ${total} keys`)
    for (const line of problems) console.error('  ' + line)
    process.exit(1)
  }
  console.log(`i18n contract OK — ${total} keys, zh-CN and en-US aligned`)
}

main().catch(error => {
  console.error('i18n contract could not run:', error && error.message ? error.message : error)
  process.exit(1)
})
