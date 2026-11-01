import type { MessageKey } from '@/ember/i18n/strings'

export type TranscriberType = 'fast-whisper' | 'openai-asr'

export const DEFAULT_ONBOARDING_TRANSCRIBER: TranscriberType = 'fast-whisper'

export const ONBOARDING_TRANSCRIBERS: Array<{
  value: TranscriberType
  title: MessageKey
  description: MessageKey
}> = [
  {
    value: 'fast-whisper',
    title: 'onboarding.transcriber.local',
    description: 'onboarding.transcriber.localDesc',
  },
  {
    value: 'openai-asr',
    title: 'onboarding.transcriber.openai',
    description: 'onboarding.transcriber.openaiDesc',
  },
]

export type OnboardingTranscriberPayload =
  | { transcriber_type: 'fast-whisper'; whisper_model_size: 'tiny' }
  | { transcriber_type: 'openai-asr' }

/** Reject stale state before it can be sent to the backend. */
export const buildOnboardingTranscriberPayload = (
  value: string,
): OnboardingTranscriberPayload | null => {
  if (value === 'fast-whisper') {
    return { transcriber_type: value, whisper_model_size: 'tiny' }
  }
  if (value === 'openai-asr') {
    return { transcriber_type: value }
  }
  return null
}
