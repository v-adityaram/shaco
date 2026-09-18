import { useEffect, useMemo, useRef, useState } from 'react'
import { Badges } from '../components/Badges'
import { BridgeTimer } from '../components/BridgeTimer'
import { LayerStack } from '../components/LayerStack'
import { LiveDiagnosisControl } from '../components/LiveDiagnosisControl'
import { ScenarioSwitcher } from '../components/ScenarioSwitcher'
import { runLiveDiagnosis } from '../lib/ai'
import { BlastRadius } from '../panels/BlastRadius'
import { Checks } from '../panels/Checks'
import { Hypotheses } from '../panels/Hypotheses'
import { IncidentHeader } from '../panels/IncidentHeader'
import { Recovery } from '../panels/Recovery'
import { RuledOut } from '../panels/RuledOut'
import { Timeline } from '../panels/Timeline'
import type { AiDiagnosis, NormalisedEvent, ScenarioBundle } from '../lib/types'

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
  const [lateInjected, setLateInjected] = useState(false)
  const [showDiff, setShowDiff] = useState(false)

  const [liveStatus, setLiveStatus] = useState<'idle' | 'loading' | 'error' | 'done'>('idle')
  const [liveDiagnosis, setLiveDiagnosis] = useState<AiDiagnosis | null>(null)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [liveElapsed, setLiveElapsed] = useState(0)
  const elapsedTimer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (elapsedTimer.current) window.clearInterval(elapsedTimer.current)
    }
  }, [])

  const diagnosis: AiDiagnosis =
    liveDiagnosis ?? (lateInjected ? bundle.lateEvidence.diagnosisAfter : bundle.diagnosis)

  const events: NormalisedEvent[] = useMemo(
    () => (lateInjected && !liveDiagnosis ? [...bundle.events, bundle.lateEvidence.event] : bundle.events),
    [bundle, lateInjected, liveDiagnosis],
  )
  const eventsById = useMemo(() => new Map(events.map((e) => [e.event_id, e])), [events])

  const topCause = diagnosis.hypotheses.find((h) => h.rank === 1)?.cause

  function injectLateEvidence() {
    setLateInjected(true)
    setShowDiff(true)
  }

  async function runLive() {
    setLiveStatus('loading')
    setLiveError(null)
    setLiveElapsed(0)
    elapsedTimer.current = window.setInterval(() => setLiveElapsed((s) => s + 1), 1000)
    try {
      const result = await runLiveDiagnosis(bundle.events)
      setLiveDiagnosis(result)
      setLiveStatus('done')
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : String(err))
      setLiveStatus('error')
    } finally {
      if (elapsedTimer.current) {
        window.clearInterval(elapsedTimer.current)
        elapsedTimer.current = null
      }
    }
  }

  function backToCached() {
    setLiveDiagnosis(null)
    setLiveStatus('idle')
    setLiveError(null)
  }

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
              ruledOutCount={diagnosis.ruled_out.length}
            />
            <LiveDiagnosisControl
              status={liveStatus}
              elapsed={liveElapsed}
              error={liveError}
              onRunLive={runLive}
              onBackToCached={backToCached}
            />
          </div>
          <ScenarioSwitcher
            slugs={slugs}
            labels={labels}
            active={activeSlug}
            onChange={onScenarioChange}
          />
        </div>

        <IncidentHeader meta={bundle.meta} summary={diagnosis.incident_summary} />

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Timeline
            items={diagnosis.timeline}
            newEventId={lateInjected ? bundle.lateEvidence.event.event_id : undefined}
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

        {showDiff && (
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
            <p className="text-[12.5px] text-emerald-900/90 dark:text-emerald-100/90">
              {bundle.lateEvidence.diff.changed_summary}
            </p>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <div className="text-[10px] text-slate-500 uppercase">Before</div>
                <ol className="mt-1 space-y-0.5 text-[12px] text-slate-500 dark:text-slate-400">
                  {bundle.lateEvidence.diff.rank_before.map((r) => (
                    <li key={r.rank}>
                      {r.rank}. {r.cause}
                    </li>
                  ))}
                </ol>
              </div>
              <div>
                <div className="text-[10px] text-emerald-600 dark:text-emerald-500 uppercase">After</div>
                <ol className="mt-1 space-y-0.5 text-[12px] text-emerald-800 dark:text-emerald-200">
                  {bundle.lateEvidence.diff.rank_after.map((r) => (
                    <li key={r.rank}>
                      {r.rank}. {r.cause}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
            <ul className="mt-2 list-inside list-disc space-y-1 text-[11.5px] text-slate-600 dark:text-slate-300">
              {bundle.lateEvidence.diff.what_changed.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-5 flex justify-center pb-8">
          <button
            disabled={lateInjected || Boolean(liveDiagnosis)}
            onClick={injectLateEvidence}
            title={liveDiagnosis ? 'Not available on a live result — go back to cached first' : undefined}
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
