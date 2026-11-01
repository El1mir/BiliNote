import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, RefreshCw, TriangleAlert } from 'lucide-react'
import {
  addModel,
  addProvider,
  getProviderList,
  testConnection,
  updateProviderById,
} from '@/services/model'
import { updateTranscriberConfig } from '@/services/transcriber'
import { Button } from '@/ember/ui/Button'
import { Card, CardBody } from '@/ember/ui/Card'
import { Field } from '@/ember/ui/Field'
import { Input } from '@/ember/ui/Input'
import { Spinner } from '@/ember/ui/Spinner'
import { LanguageSwitcher } from '@/ember/shell/LanguageSwitcher'
import { useI18n } from '@/ember/i18n/context'
import { ONBOARDING_STORAGE_KEY } from '@/ember/pages/onboardingStorage'
import {
  buildOnboardingTranscriberPayload,
  DEFAULT_ONBOARDING_TRANSCRIBER,
  ONBOARDING_TRANSCRIBERS,
  type TranscriberType,
} from '@/ember/pages/onboardingTranscriber'

/**
 * Desktop first-run setup.
 *
 * The guard lives in EmberApp: the web build never sees this page, because a
 * browser deployment is already configured by whoever installed it. On the
 * desktop build the app is useless until an LLM provider and a transcriber
 * exist, so those two are asked for up front rather than discovered later as a
 * failing task.
 */

const TOTAL_STEPS = 4

const apiBase = ((import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api').replace(/\/$/, '')

/** Deliberately not the shared axios client: startup must not stack error toasts. */
async function pingBackend(): Promise<boolean> {
  try {
    const response = await fetch(apiBase + '/sys_check')
    if (!response.ok) return false
    const payload = (await response.json().catch(() => null)) as { code?: number } | null
    return payload?.code === 0
  } catch {
    return false
  }
}

/** The backend rejects with { code, msg, data }, never an Error. */
function errorText(error: unknown): string {
  if (!error) return ''
  if (typeof error === 'string') return error
  const shaped = error as { msg?: string; message?: string }
  return shaped.msg || shaped.message || ''
}

/**
 * 结构化错误原因。
 *
 * 后端用 R.error(msg, code, data={reason}) 给出稳定标识，前端按 reason 判定；
 * 绝不能拿中文文案去 includes —— 那条文案一旦改写，判定会静默失效，而且英文
 * 界面里还会被迫保留一个「不许翻译」的键。
 */
function errorReason(error: unknown): string {
  const shaped = error as { data?: { reason?: string } | null } | null | undefined
  return shaped?.data?.reason || ''
}

const TRANSCRIBERS = ONBOARDING_TRANSCRIBERS

export function OnboardingPage() {
  const { t } = useI18n()
  const navigate = useNavigate()

  const [step, setStep] = useState(1)
  const [error, setError] = useState('')

  const [probing, setProbing] = useState(false)
  const [backendReady, setBackendReady] = useState<boolean | null>(null)

  const [providerName, setProviderName] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1')
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState('gpt-4o-mini')
  const [savingProvider, setSavingProvider] = useState(false)

  const [transcriberType, setTranscriberType] = useState<TranscriberType>(DEFAULT_ONBOARDING_TRANSCRIBER)
  const [savingTranscriber, setSavingTranscriber] = useState(false)

  const probe = useCallback(async () => {
    setProbing(true)
    const ready = await pingBackend()
    setBackendReady(ready)
    setProbing(false)
  }, [])

  useEffect(() => {
    void probe()
  }, [probe])

  const next = () => setStep(current => Math.min(TOTAL_STEPS, current + 1))
  const back = () => setStep(current => Math.max(1, current - 1))

  async function saveProvider() {
    setError('')
    const name = providerName.trim()
    if (!name || !modelName.trim()) {
      setError(t('onboarding.step2.missing'))
      return
    }
    setSavingProvider(true)
    try {
      let providerId: string | undefined
      try {
        const created = (await addProvider(
          { name, api_key: apiKey.trim(), base_url: baseUrl.trim(), type: 'custom', logo: 'custom' },
          { silent: true },
        )) as unknown as { data?: string } | string
        providerId =
          typeof created === 'string' ? created : (created?.data as string | undefined)
        if (!providerId) throw new Error(t('onboarding.error.noProviderId'))
      } catch (addError) {
        // The backend seeds providers with the same names; a duplicate name is
        // expected, so reuse the existing row instead of failing the step.
        if (errorReason(addError) !== 'provider_name_exists') throw addError
        const list = (await getProviderList({ silent: true })) || []
        const existing = list.find(item => item?.name === name)
        if (!existing?.id) throw new Error(t('onboarding.error.providerNotFound', { name }))
        providerId = existing.id
        await updateProviderById(
          { id: providerId, api_key: apiKey.trim(), base_url: baseUrl.trim(), enabled: 1 },
          { silent: true },
        )
      }

      try {
        await addModel({ provider_id: providerId, model_name: modelName.trim() }, { silent: true })
      } catch (modelError) {
        if (errorReason(modelError) !== 'model_name_exists') throw modelError
      }

      // A failing connectivity test is information, not a blocker: the user may
      // be behind a proxy or simply not have a key yet.
      try {
        await testConnection({ id: providerId, model: modelName.trim() }, { silent: true })
      } catch {
        /* reported on the settings page instead of blocking setup */
      }
      next()
    } catch (saveError) {
      setError(t('onboarding.error.save', { detail: errorText(saveError) || t('onboarding.error.unknown') }))
    } finally {
      setSavingProvider(false)
    }
  }

  async function saveTranscriber() {
    setError('')
    const payload = buildOnboardingTranscriberPayload(transcriberType)
    if (!payload) {
      setError(t('onboarding.error.unknown'))
      return
    }
    setSavingTranscriber(true)
    try {
      await updateTranscriberConfig(payload)
      next()
    } catch (saveError) {
      setError(t('onboarding.error.save', { detail: errorText(saveError) || t('onboarding.error.unknown') }))
    } finally {
      setSavingTranscriber(false)
    }
  }

  function finish() {
    try {
      window.localStorage.setItem(ONBOARDING_STORAGE_KEY, '1')
    } catch {
      /* storage disabled — the guard simply asks again next launch */
    }
    navigate('/', { replace: true })
  }

  return (
    <div className="min-h-dvh bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
        <header className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-surface bg-ember font-display text-subhead font-bold text-white">
              B
            </span>
            <div>
              <p className="ember-overline text-ink-mute">{t('onboarding.overline')}</p>
              <h1 className="font-display text-section leading-tight text-ink">{t('onboarding.title')}</h1>
            </div>
          </div>
          <LanguageSwitcher compact />
        </header>

        <ol className="flex items-center gap-2" aria-label={t('onboarding.stepLabel', { current: step, total: TOTAL_STEPS })}>
          {[1, 2, 3, 4].map(index => (
            <li key={index} className="flex flex-1 items-center gap-2">
              <span
                className={
                  index <= step
                    ? 'grid size-6 shrink-0 place-items-center rounded-full bg-ember text-caption font-semibold text-white'
                    : 'grid size-6 shrink-0 place-items-center rounded-full border border-line bg-canvas text-caption font-semibold text-ink-mute'
                }
              >
                {index < step ? <Check className="size-3.5" aria-hidden="true" /> : index}
              </span>
              {index < TOTAL_STEPS && (
                <span className={index < step ? 'h-px flex-1 bg-ember' : 'h-px flex-1 bg-line'} />
              )}
            </li>
          ))}
        </ol>

        <Card className="ember-enter">
          {step === 1 && (
            <CardBody className="flex flex-col gap-4">
              <StepHeading title={t('onboarding.step1.title')} description={t('onboarding.step1.description')} />
              {probing && (
                <p className="flex items-center gap-2 text-small text-ink-soft">
                  <Spinner className="size-4 text-ember" />
                  {t('onboarding.step1.checking')}
                </p>
              )}
              {!probing && backendReady === true && (
                <p className="rounded-field bg-ok/10 px-3 py-2 text-small text-ink">{t('onboarding.step1.ready')}</p>
              )}
              {!probing && backendReady === false && (
                <p className="flex items-start gap-2 rounded-field bg-danger/10 px-3 py-2 text-small text-ink">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
                  {t('onboarding.step1.notReady')}
                </p>
              )}
              <div className="flex items-center justify-between gap-2">
                <Button variant="ghost" size="sm" loading={probing} onClick={() => void probe()}>
                  <RefreshCw className="size-4" aria-hidden="true" />
                  {t('onboarding.step1.retry')}
                </Button>
                <Button variant="primary" disabled={backendReady !== true} onClick={next}>
                  {t('onboarding.next')}
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Button>
              </div>
            </CardBody>
          )}

          {step === 2 && (
            <CardBody className="flex flex-col gap-4">
              <StepHeading title={t('onboarding.step2.title')} description={t('onboarding.step2.description')} />
              <Field label={t('onboarding.step2.name')} htmlFor="onboarding-provider" hint={t('onboarding.step2.nameHint')}>
                <Input
                  id="onboarding-provider"
                  value={providerName}
                  onChange={event => setProviderName(event.target.value)}
                />
              </Field>
              <Field label={t('onboarding.step2.baseUrl')} htmlFor="onboarding-base-url">
                <Input
                  id="onboarding-base-url"
                  value={baseUrl}
                  onChange={event => setBaseUrl(event.target.value)}
                />
              </Field>
              <Field label={t('onboarding.step2.apiKey')} htmlFor="onboarding-api-key">
                <Input
                  id="onboarding-api-key"
                  type="password"
                  value={apiKey}
                  onChange={event => setApiKey(event.target.value)}
                />
              </Field>
              <Field label={t('onboarding.step2.model')} htmlFor="onboarding-model" hint={t('onboarding.step2.modelHint')}>
                <Input
                  id="onboarding-model"
                  value={modelName}
                  onChange={event => setModelName(event.target.value)}
                />
              </Field>
              <StepError message={error} />
              <StepFooter onBack={back}>
                <Button variant="primary" loading={savingProvider} onClick={() => void saveProvider()}>
                  {t('onboarding.saveAndNext')}
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Button>
              </StepFooter>
            </CardBody>
          )}

          {step === 3 && (
            <CardBody className="flex flex-col gap-4">
              <StepHeading title={t('onboarding.step3.title')} description={t('onboarding.step3.description')} />
              <div className="flex flex-col gap-2">
                {TRANSCRIBERS.map(option => {
                  const active = transcriberType === option.value
                  return (
                    <label
                      key={option.value}
                      className={
                        active
                          ? 'ember-press flex cursor-pointer gap-3 rounded-field border border-ember bg-ember-soft p-3'
                          : 'ember-press flex cursor-pointer gap-3 rounded-field border border-line p-3'
                      }
                    >
                      <input
                        type="radio"
                        name="onboarding-transcriber"
                        value={option.value}
                        checked={active}
                        onChange={event => {
                          const value = event.currentTarget.value
                          if (value === 'fast-whisper' || value === 'openai-asr') setTranscriberType(value)
                        }}
                        className="mt-1 accent-[var(--color-ember)]"
                      />
                      <span className="flex flex-col gap-0.5">
                        <span className="text-small font-semibold text-ink">{t(option.title)}</span>
                        <span className="text-caption text-ink-mute">{t(option.description)}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
              <StepError message={error} />
              <StepFooter onBack={back}>
                <Button variant="primary" loading={savingTranscriber} onClick={() => void saveTranscriber()}>
                  {t('onboarding.saveAndNext')}
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Button>
              </StepFooter>
            </CardBody>
          )}

          {step === 4 && (
            <CardBody className="flex flex-col gap-4">
              <StepHeading title={t('onboarding.step4.title')} description={t('onboarding.step4.description')} />
              <p className="rounded-field bg-surface px-3 py-2.5 text-caption text-ink-soft">
                {t('onboarding.step4.tip')}
              </p>
              <StepFooter onBack={back}>
                <Button variant="primary" onClick={finish}>
                  {t('onboarding.finish')}
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Button>
              </StepFooter>
            </CardBody>
          )}
        </Card>

        <p className="text-center text-caption text-ink-mute">{t('onboarding.footer')}</p>
      </div>
    </div>
  )
}

function StepHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="font-display text-subhead text-ink">{title}</h2>
      <p className="text-small text-ink-soft">{description}</p>
    </div>
  )
}

function StepError({ message }: { message: string }) {
  if (!message) return null
  return (
    <p className="flex items-start gap-2 rounded-field bg-danger/10 px-3 py-2 text-caption text-ink">
      <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-danger" aria-hidden="true" />
      {message}
    </p>
  )
}

function StepFooter({ onBack, children }: { onBack: () => void; children: React.ReactNode }) {
  const { t } = useI18n()
  return (
    <div className="flex items-center justify-between gap-2 pt-1">
      <Button variant="ghost" size="sm" onClick={onBack}>
        <ArrowLeft className="size-4" aria-hidden="true" />
        {t('onboarding.back')}
      </Button>
      {children}
    </div>
  )
}