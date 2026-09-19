import { useEffect, useMemo, useState } from 'react'
import { Badges } from '../components/Badges'
import { BridgeTimer } from '../components/BridgeTimer'
import { DiagnosisPending } from '../components/DiagnosisPending'
import { LayerStack } from '../components/LayerStack'
import {
  LiveDiagnosisControl,
  SourceLabel,
  type DiagnosisSource,
} from '../components/LiveDiagnosisControl'
import { ScenarioSwitcher } from '../components/ScenarioSwitcher'
import { ensureDiagnosis, ensureLate, useLiveState } from '../lib/liveCache'
import { BlastRadius } from '../panels/BlastRadius'
import { Checks } from '../panels/Checks'
import { Hypotheses } from '../panels/Hypotheses'
import { IncidentHeader } from '../panels/IncidentHeader'
import { Recovery } from '../panels/Recovery'
import { RuledOut } from '../panels/RuledOut'
import { Timeline } from '../panels/Timeline'
import type {
  AiDiagnosis,
  DiagnosisMeta,
  LateEvidenceDiff,
  NormalisedEvent,
  ScenarioBundle,
} from '../lib/types'

/** Strip the server's _meta (and any diff) before sending a diagnosis back as `previousDiagnosis`. */
function plainDiagnosis(d: AiDiagnosis): AiDiagnosis {
  const copy = { ...(d as AiDiagnosis & { _meta?: unknown; diff?: unknown }) }
  delete copy._meta
  delete copy.diff
  return copy
}

function sourceOf(meta: DiagnosisMeta | undefined): DiagnosisSource {
  return meta?.source === 'server-cache' ? 'Server cache' : 'Live'
}

export function AiView({
  bundle,
  slugs,
  labels,
  activeSlug,
  onScenarioChange,
}: {
  bundle: ScenarioBundle
  slugs: string[]
  labels: Record<string, string>
  activeSlug: string
  onScenarioChange: (slug: string) => void
}) {
  const slug = bundle.meta.slug
  const isAiLive = bundle.meta.mode === 'ai-live'
  const live = useLiveState()
  const diagEntry = live.diag[slug]
  const lateEntry = live.late[slug]

  const [showLive, setShowLive] = useState(false) // curated scenarios: swap cached -> live result
  const [lateInjected, setLateInjected] = useState(false)
  const [showDiff, setShowDiff] = useState(true)
  const [showProvenance, setShowProvenance] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  // elapsed-seconds counter for the small "calling model live" pill
  useEffect(() => {
    if (diagEntry?.status !== 'loading') return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [diagEntry?.status])
  const liveElapsed = diagEntry?.status === 'loading' ? Math.max(0, Math.floor((now - diagEntry.startedAt) / 1000)) : 0

  // A curated bundle without a cached diagnosis (should not happen) falls back to the live call.
  const needsLiveOnly = isAiLive || !bundle.diagnosis
  useEffect(() => {
    if (needsLiveOnly) ensureDiagnosis(slug, bundle.events)
  }, [needsLiveOnly, slug, bundle.events])

  const liveResult = diagEntry?.status === 'done' ? diagEntry.result : null
  const useLive = liveResult !== null && (needsLiveOnly || showLive)
  const baseDiagnosis: AiDiagnosis | null = useLive ? liveResult : bundle.diagnosis

  // ---- late evidence ----
  const cachedLateOk = Boolean(bundle.lateEvidence?.diagnosisAfter && bundle.lateEvidence?.diff)
  const lateViaLive = lateInjected && (useLive || !cachedLateOk)
  const lateResult = lateViaLive && lateEntry?.status === 'done' ? lateEntry.result : null
  const lateDiagnosis: AiDiagnosis | null = !lateInjected
    ? null
    : lateViaLive
      ? lateResult
      : (bundle.lateEvidence.diagnosisAfter ?? null)
  const lateDiff: LateEvidenceDiff | null = !lateInjected
    ? null
    : lateViaLive
      ? (lateResult?.diff ?? null)
      : (bundle.lateEvidence.diff ?? null)

  const diagnosis = lateDiagnosis ?? baseDiagnosis
  const shownMeta =
    (lateViaLive && lateResult ? lateResult._meta : undefined) ?? (useLive ? liveResult?._meta : undefined)
  const source: DiagnosisSource = useLive ? sourceOf(shownMeta) : 'Cached'

  const events: NormalisedEvent[] = useMemo(
    () => (lateInjected ? [...bundle.events, bundle.lateEvidence.event] : bundle.events),
    [bundle, lateInjected],
  )
  const eventsById = useMemo(() => new Map(events.map((e) => [e.event_id, e])), [events])

  const ruleHits = bundle.events.filter((e) => e.kind === 'rule_hit').length
  const contextRecs = bundle.events.filter((e) => e.kind === 'context').length

  const topCause = diagnosis?.hypotheses.find((h) => h.rank === 1)?.cause

  function runLive() {
    setShowLive(true)
    ensureDiagnosis(slug, bundle.events, { retry: true })
  }

  function injectLateEvidence() {
    setLateInjected(true)
    setShowDiff(true)
    if ((useLive || !cachedLateOk) && baseDiagnosis) {
      ensureLate(slug, bundle.events, bundle.lateEvidence.event, plainDiagnosis(baseDiagnosis))
    }
  }

  function retryLate() {
    if (baseDiagnosis) {
      ensureLate(slug, bundle.events, bundle.lateEvidence.event, plainDiagnosis(baseDiagnosis), { retry: true })
    }
  }

  const liveStatus = diagEntry?.status ?? 'idle'
  const lateLoading = lateViaLive && lateEntry?.status === 'loading'
  const lateError = lateViaLive && lateEntry?.status === 'error' ? lateEntry.error : null

  return (
    <div className="relative min-h-full bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-200">
      <div className="pointer-events-none fixed top-16 right-3 z-40">
        <LayerStack />
      </div>

      <div className="mx-auto max-w-6xl px-4 py-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badges
              rulesFired={bundle.rulesFired}
              rulesTotal={bundle.rulesTotal}
              noiseRulesFired={bundle.noiseRulesFired}
            />
          </div>
          <ScenarioSwitcher slugs={slugs} labels={labels} active={activeSlug} onChange={onScenarioChange} />
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          {diagnosis && <SourceLabel source={source} model={shownMeta?.model} />}
          {!isAiLive && (
            <LiveDiagnosisControl
              status={liveStatus}
              elapsed={liveElapsed}
              error={diagEntry?.status === 'error' ? diagEntry.error : null}
              showingLive={useLive}
              disabled={lateInjected}
              onRunLive={runLive}
              onBackToCached={() => setShowLive(false)}
            />
          )}
          <button
            onClick={() => setShowProvenance((v) => !v)}
            className="text-[11px] text-slate-500 underline decoration-dotted hover:text-slate-800 dark:hover:text-slate-200"
          >
            How this was produced
          </button>
        </div>

        {showProvenance && (
          <p className="mb-3 rounded border border-slate-300 dark:border-slate-700/60 bg-white dark:bg-slate-800/40 px-3 py-2 text-[11.5px] text-slate-600 dark:text-slate-300">
            <strong>Facts:</strong> assembled by code from rule hits + records (traceable to source).{' '}
            <strong>Reasoning:</strong> model output — source: {diagnosis ? source : 'pending'}. The rules
            detected; the AI only correlates, explains, ranks and proposes.
          </p>
        )}

        {source === 'Server cache' && (
          <div className="mb-3 rounded border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-[12px] text-amber-800 dark:text-amber-200">
            Replayed from last successful live run
            {shownMeta?.cachedAt ? ` (${new Date(shownMeta.cachedAt).toLocaleString()})` : ''} — live call failed.
          </div>
        )}
        {shownMeta?.warnings && shownMeta.warnings.length > 0 && (
          <ul className="mb-3 list-inside list-disc text-[11px] text-amber-700 dark:text-amber-300">
            {shownMeta.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}

        <IncidentHeader meta={bundle.meta} summary={diagnosis?.incident_summary} />

        {!diagnosis && diagEntry?.status !== 'error' && (
          <DiagnosisPending
            status="loading"
            startedAt={diagEntry?.status === 'loading' ? diagEntry.startedAt : undefined}
            headline={`AI is reading ${ruleHits} rule hits and ${contextRecs} context records…`}
            onRetry={() => undefined}
          />
        )}
        {!diagnosis && diagEntry?.status === 'error' && (
          <DiagnosisPending
            status="error"
            error={diagEntry.error}
            headline=""
            onRetry={() => ensureDiagnosis(slug, bundle.events, { retry: true })}
          />
        )}

        {diagnosis && (
          <>
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Timeline
                items={diagnosis.timeline}
                eventsById={eventsById}
                newEventId={lateDiagnosis ? bundle.lateEvidence.event.event_id : undefined}
              />
              <div className="space-y-4">
                <Hypotheses hypotheses={diagnosis.hypotheses} eventsById={eventsById} />
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <RuledOut items={diagnosis.ruled_out} />
              <Checks checks={diagnosis.checks} />
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <BlastRadius data={diagnosis.blast_radius} />
              <Recovery recovery={diagnosis.recovery} />
            </div>
          </>
        )}

        {lateLoading && (
          <DiagnosisPending
            status="loading"
            startedAt={lateEntry?.status === 'loading' ? lateEntry.startedAt : undefined}
            headline="AI is re-reading the evidence with the late record…"
            onRetry={() => undefined}
          />
        )}
        {lateError && (
          <DiagnosisPending status="error" error={lateError} headline="" onRetry={retryLate} />
        )}

        {showDiff && lateDiff && (
          <div className="mt-4 rounded-lg border border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/5 p-4">
            <div className="mb-2 flex items-center gap-2">
              <h2 className="text-[13px] font-semibold tracking-wide text-emerald-700 dark:text-emerald-300 uppercase">
                What changed
              </h2>
              <button
                onClick={() => setShowDiff(false)}
                className="ml-auto text-[11px] text-slate-500 hover:text-slate-800 dark:hover:text-slate-300"
              >
                dismiss
              </button>
            </div>
            <p className="text-[12.5px] text-emerald-900/90 dark:text-emerald-100/90">{lateDiff.changed_summary}</p>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <div className="text-[10px] text-slate-500 uppercase">Before</div>
                <ol className="mt-1 space-y-0.5 text-[12px] text-slate-500 dark:text-slate-400">
                  {lateDiff.rank_before.map((r) => (
                    <li key={r.rank}>
                      {r.rank}. {r.cause}
                    </li>
                  ))}
                </ol>
              </div>
              <div>
                <div className="text-[10px] text-emerald-600 dark:text-emerald-500 uppercase">After</div>
                <ol className="mt-1 space-y-0.5 text-[12px] text-emerald-800 dark:text-emerald-200">
                  {lateDiff.rank_after.map((r) => (
                    <li key={r.rank}>
                      {r.rank}. {r.cause}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
            <ul className="mt-2 list-inside list-disc space-y-1 text-[11.5px] text-slate-600 dark:text-slate-300">
              {lateDiff.what_changed.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-5 flex justify-center pb-8">
          <button
            disabled={lateInjected || !baseDiagnosis}
            onClick={injectLateEvidence}
            title={!baseDiagnosis ? 'Waiting for the diagnosis' : undefined}
            className="rounded-md border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 px-4 py-2 text-[12.5px] font-medium text-amber-700 dark:text-amber-300 transition hover:bg-amber-100 dark:hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {lateInjected ? 'Late evidence injected' : 'Inject late evidence →'}
          </button>
        </div>
      </div>

      <BridgeTimer causeAgreed={topCause} />
    </div>
  )
}
