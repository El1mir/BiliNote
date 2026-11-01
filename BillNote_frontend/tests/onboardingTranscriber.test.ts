import { describe, expect, it } from 'vitest'

import { dictionaries } from '../src/ember/i18n/strings'
import {
  buildOnboardingTranscriberPayload,
  DEFAULT_ONBOARDING_TRANSCRIBER,
  ONBOARDING_TRANSCRIBERS,
} from '../src/ember/pages/onboardingTranscriber'

describe('onboarding transcriber contract', () => {
  it('exposes only the backend-supported engines and a legal default', () => {
    const availableTypes = ['fast-whisper', 'openai-asr']
    expect(ONBOARDING_TRANSCRIBERS.map(option => option.value)).toEqual(availableTypes)
    expect(availableTypes).toContain(DEFAULT_ONBOARDING_TRANSCRIBER)
  })

  it('builds the local Whisper payload with its model size', () => {
    expect(buildOnboardingTranscriberPayload('fast-whisper')).toEqual({
      transcriber_type: 'fast-whisper',
      whisper_model_size: 'tiny',
    })
  })

  it('does not send a Whisper model size for OpenAI-compatible ASR', () => {
    expect(buildOnboardingTranscriberPayload('openai-asr')).toEqual({
      transcriber_type: 'openai-asr',
    })
  })

  it.each(['groq', 'bcut', 'kuaishou', 'mlx-whisper', 'unknown'])(
    'rejects stale or unsupported value %s before building a request',
    value => {
      expect(buildOnboardingTranscriberPayload(value)).toBeNull()
    },
  )

  it('provides non-empty bilingual labels and invalid-value feedback', () => {
    const keys = [
      ...ONBOARDING_TRANSCRIBERS.flatMap(({ title, description }) => [title, description]),
      'onboarding.transcriber.openai',
      'onboarding.transcriber.openaiDesc',
      'onboarding.error.invalidTranscriber',
    ] as const

    for (const locale of ['zh-CN', 'en-US'] as const) {
      for (const key of keys) expect(dictionaries[locale][key].trim()).not.toBe('')
    }
  })
})
