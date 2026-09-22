import { useEffect, useMemo, useRef, useState } from 'react'
import { Badges } from '../components/Badges'
import { fetchDiagnosis } from '../lib/ai'
import {
  fetchLiveWindow,
  priorityLabel,
  stripHtml,
  toNormalisedEvent,
  useArrivedIncidents,
  type LiveWindow,
  type RawLiveIncident,
} from '../lib/liveIncidents'
import type { DiagnosisMeta, DiagnosisResult, NormalisedEvent, ScenarioMeta } from '../lib/types'
import { BlastRadius } from '../panels/BlastRadius'
import { Checks } from '../panels/Checks'
import { Hypotheses } from '../panels/Hypotheses'
import { IncidentHeader } from '../panels/IncidentHeader'
import { Recovery } from '../panels/Recovery'
import { RuledOut } from '../panels/RuledOut'
import { Timeline } from '../panels/Timeline'

const SLUG = 'live-june-2026'
const SPEED = 240 // 48 simulated hours per 12 real minutes

const PRIORITY_STYLE: Record<string, string> = {
  P1: 'bg-rose-100 text-rose-700 border-rose-300 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/40',
  P2: 'bg-rose-100 text-rose-700 border-rose-300 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/40',
  P3: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/40',
  P4: 'bg-slate-200 text-slate-600 border-slate-300 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-500/40',
  P5: 'bg-slate-200 text-slate-600 border-slate-300 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-500/40',
}

function formatAgo(simSecondsAgo: number): string {
  if (simSecondsAgo < 60) return 'just now'
  const m = Math.floor(simSecondsAgo / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m ago`
}

/** How much the last AI call actually cost, in time and tokens -- from the server's _meta. */
function AiCallStats({ meta }: { meta?: DiagnosisMeta }) {
  if (!meta) return null
  const stat = (label: string, value: string) => (
    <div className="flex flex-col">
      <span className="text-[9.5px] tracking-wide text-slate-400 uppercase dark:text-slate-500">{label}</span>
      <span className="font-mono-tight text-[12px] text-slate-700 dark:text-slate-300">{value}</span>
    </div>
  )
  return (
    <div className="mb-2 rounded-md border border-slate-200 bg-white/60 p-2 dark:border-slate-700/60 dark:bg-slate-900/40">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase dark:text-slate-400">
          AI call
        </span>
        <span
          className={`text-[10px] ${meta.source === 'live' ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}
        >
          {meta.source === 'live' ? 'live' : 'fallback (server cache)'}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
        {stat('model', meta.model ?? '—')}
        {stat('time', meta.latencyMs != null ? `${(meta.latencyMs / 1000).toFixed(1)}s` : '—')}
        {stat('calls', meta.calls != null ? String(meta.calls) : '—')}
        {meta.usage ? (
          <>
            {stat('input tok', meta.usage.input_tokens.toLocaleString())}
            {stat('output tok', meta.usage.output_tokens.toLocaleString())}
            {stat('total tok', meta.usage.total_tokens.toLocaleString())}
          </>
        ) : (
          <div className="col-span-2 text-[10.5px] text-slate-400">token usage unavailable (fallback answer)</div>
        )}
      </div>
      {meta.usage && meta.usage.reasoning_tokens > 0 && (
        <div className="mt-1 text-[10px] text-slate-400 dark:text-slate-500">
          of which {meta.usage.reasoning_tokens.toLocaleString()} reasoning tokens
        </div>
      )}
      {meta.warnings && meta.warnings.length > 0 && (
        <div className="mt-1 text-[10px] text-amber-600 dark:text-amber-400">
          {meta.warnings.length} grounding warning{meta.warnings.length > 1 ? 's' : ''}
        </div>
      )}
    </div>
  )
}

function IncidentCard({
  inc,
  agoSec,
  isCluster,
  selected,
  onToggle,
}: {
  inc: RawLiveIncident
  agoSec: number
  isCluster: boolean
  selected: boolean
  onToggle: () => void
}) {
  const p = priorityLabel(inc.priority)
  const detail = stripHtml(inc.details)
  return (
    <label
      className={`animate-slide-in-row flex cursor-pointer gap-2.5 rounded-lg border p-3 text-[12.5px] transition ${
        selected
          ? 'border-sky-400 bg-sky-100 ring-1 ring-sky-400 dark:border-sky-400/70 dark:bg-sky-500/20'
          : isCluster
            ? 'border-sky-300 bg-sky-50 dark:border-sky-500/40 dark:bg-sky-500/10'
            : 'border-slate-200 bg-white dark:border-slate-700/60 dark:bg-slate-900/50'
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="mt-1 h-3.5 w-3.5 shrink-0 accent-sky-600"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${PRIORITY_STYLE[p] ?? PRIORITY_STYLE.P4}`}>
            {p}
          </span>
          <span className="font-mono-tight text-[11px] text-slate-500 dark:text-slate-400">{inc.number}</span>
          {inc.parent_incident && (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600 dark:bg-slate-700/60 dark:text-slate-300">
              dup of {inc.parent_incident}
            </span>
          )}
          <span className="ml-auto text-[10.5px] text-slate-400 dark:text-slate-500">{formatAgo(agoSec)}</span>
        </div>
        <div className="mt-1 font-medium text-slate-800 dark:text-slate-100">{inc.subject}</div>
        {detail && <div className="mt-0.5 line-clamp-2 text-slate-500 dark:text-slate-400">{detail}</div>}
        <div className="mt-1.5 flex flex-wrap gap-1 text-[10.5px] text-slate-500 dark:text-slate-400">
          {inc.team && <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{inc.team}</span>}
          {inc.configuration_item && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{inc.configuration_item}</span>
          )}
          {inc.classification_keyword && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{inc.classification_keyword}</span>
          )}
        </div>
      </div>
    </label>
  )
}

type DiagStatus = 'idle' | 'loading' | 'error' | 'done'

export function LiveFloor() {
  const [win, setWin] = useState<LiveWindow | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const [diagStatus, setDiagStatus] = useState<DiagStatus>('idle')
  const [diagResult, setDiagResult] = useState<DiagnosisResult | null>(null)
  const [diagError, setDiagError] = useState<string | null>(null)
  const [diagElapsed, setDiagElapsed] = useState(0)
  const [sentCount, setSentCount] = useState(0)
  const [sentWasHandpicked, setSentWasHandpicked] = useState(false)
  const elapsedTimer = useRef<number | null>(null)

  useEffect(() => {
    fetchLiveWindow().then(setWin, (err) => setLoadError(err instanceof Error ? err.message : String(err)))
  }, [])
  useEffect(() => () => {
    if (elapsedTimer.current) window.clearInterval(elapsedTimer.current)
  }, [])

  // Freeze the feed while a call is in flight -- otherwise incidents keep streaming
  // in underneath the analysis and shove already-visible/ticked cards out of view.
  const { arrived, elapsedSimSec, anchorTs } = useArrivedIncidents(win, SPEED, diagStatus === 'loading')

  // real duplicate clusters, as-linked in the source ServiceNow data itself
  const clusterIds = useMemo(() => {
    const parents = new Set(arrived.map((i) => i.parent_incident).filter(Boolean) as string[])
    const ids = new Set<string>()
    for (const i of arrived) {
      if (parents.has(i.number) || (i.parent_incident && parents.has(i.parent_incident))) ids.add(i.number)
      if (i.parent_incident) ids.add(i.parent_incident)
    }
    return ids
  }, [arrived])

  const events: NormalisedEvent[] = useMemo(
    () => arrived.map((i) => toNormalisedEvent(i, anchorTs)),
    [arrived, anchorTs],
  )
  const eventsById = useMemo(() => new Map(events.map((e) => [e.event_id, e])), [events])

  const rulesFired = new Set(arrived.map((i) => i.classification_keyword).filter(Boolean)).size

  const primaryCluster = arrived.find((i) => clusterIds.has(i.number))
  const meta: ScenarioMeta = {
    slug: SLUG,
    title: primaryCluster ? primaryCluster.subject || 'Live HIP incident' : 'Live HIP floor',
    incidentNumber: primaryCluster?.number || arrived[arrived.length - 1]?.number || '—',
    duplicateIncidents: [...clusterIds].filter((id) => id !== primaryCluster?.number),
    faultOneLine: 'Real incident, redacted, replayed live',
    mode: 'ai-live',
  }

  function toggleSelected(number: string) {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(number)) next.delete(number)
      else next.add(number)
      return next
    })
  }
  function selectAllArrived() {
    setSelected(new Set(arrived.map((i) => i.number)))
  }
  function selectCluster() {
    setSelected(new Set(clusterIds))
  }
  function clearSelection() {
    setSelected(new Set())
  }

  async function runLive() {
    const toSend = selected.size > 0 ? events.filter((e) => selected.has(e.event_id)) : events
    if (toSend.length === 0) return
    setDiagStatus('loading')
    setDiagError(null)
    setDiagElapsed(0)
    setSentCount(toSend.length)
    setSentWasHandpicked(selected.size > 0)
    elapsedTimer.current = window.setInterval(() => setDiagElapsed((s) => s + 1), 1000)
    try {
      const result = await fetchDiagnosis(SLUG, toSend)
      setDiagResult(result)
      setDiagStatus('done')
    } catch (err) {
      setDiagError(err instanceof Error ? err.message : String(err))
      setDiagStatus('error')
    } finally {
      if (elapsedTimer.current) {
        window.clearInterval(elapsedTimer.current)
        elapsedTimer.current = null
      }
    }
  }

  const selectedCount = selected.size
  const runLabel =
    diagStatus === 'loading'
      ? `Calling model live… ${diagElapsed}s`
      : diagStatus === 'error'
        ? 'Retry AI correlation →'
        : selectedCount > 0
          ? `Run AI correlation (${selectedCount} selected) →`
          : `Run AI correlation (all ${arrived.length} arrived) →`

  return (
    <div className="mx-auto max-w-6xl px-4 py-5 text-slate-800 dark:text-slate-200">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-full border border-rose-300 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
          <span className="h-1.5 w-1.5 animate-pulse-live rounded-full bg-rose-500" />
          LIVE
        </span>
        <span className="text-[12px] text-slate-500 dark:text-slate-400">
          Replaying a real 48h window of June 2026 HIP incidents (names redacted) at {SPEED}× — {arrived.length} of{' '}
          {win?.incident_count ?? '…'} arrived
        </span>
        <span className="font-mono-tight ml-auto text-[11px] text-slate-400 dark:text-slate-500">
          sim clock {Math.floor(elapsedSimSec / 3600)}h {Math.floor((elapsedSimSec % 3600) / 60)}m
        </span>
      </div>

      {loadError && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-[13px] text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
          Could not load the live window: {loadError}. Run{' '}
          <code className="font-mono-tight">python scripts/extract_live_incidents.py</code> and restart the server.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.1fr_1.4fr]">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700/60 dark:bg-slate-950/40">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="text-[12px] font-semibold tracking-wide text-slate-600 uppercase dark:text-slate-400">
              Incident feed
            </h2>
            <span className="text-[10.5px] text-slate-400 dark:text-slate-500">
              {selectedCount > 0 ? `${selectedCount} selected` : 'none selected — sends all arrived'}
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-1.5">
              <button
                onClick={selectAllArrived}
                disabled={arrived.length === 0}
                className="text-[10.5px] text-sky-700 underline decoration-dotted hover:text-sky-900 disabled:opacity-40 dark:text-sky-400 dark:hover:text-sky-200"
              >
                select all
              </button>
              <button
                onClick={selectCluster}
                disabled={clusterIds.size === 0}
                title="Select only the incidents linked to each other via Parent Incident in the real data"
                className="text-[10.5px] text-sky-700 underline decoration-dotted hover:text-sky-900 disabled:opacity-40 dark:text-sky-400 dark:hover:text-sky-200"
              >
                select linked cluster
              </button>
              <button
                onClick={clearSelection}
                disabled={selectedCount === 0}
                className="text-[10.5px] text-slate-500 underline decoration-dotted hover:text-slate-800 disabled:opacity-40 dark:hover:text-slate-300"
              >
                clear
              </button>
            </div>
          </div>
          <button
            onClick={runLive}
            disabled={arrived.length === 0 || diagStatus === 'loading'}
            className="mb-2 w-full rounded-md border border-sky-300 bg-sky-50 px-2.5 py-1.5 text-[11px] font-medium text-sky-700 transition hover:bg-sky-100 disabled:opacity-40 dark:border-sky-500/40 dark:bg-sky-500/10 dark:text-sky-300 dark:hover:bg-sky-500/20"
          >
            {runLabel}
          </button>
          {diagResult && <AiCallStats meta={diagResult._meta} />}
          <div className="max-h-[65vh] space-y-2 overflow-y-auto pr-1">
            {[...arrived].reverse().map((inc) => (
              <IncidentCard
                key={inc.number}
                inc={inc}
                agoSec={elapsedSimSec - inc.opened_offset_sec}
                isCluster={clusterIds.has(inc.number)}
                selected={selected.has(inc.number)}
                onToggle={() => toggleSelected(inc.number)}
              />
            ))}
            {arrived.length === 0 && !loadError && (
              <div className="p-6 text-center text-[12px] text-slate-400">Waiting for the first incident…</div>
            )}
          </div>
        </div>

        <div>
          {diagStatus === 'error' && (
            <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-[13px] text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
              Live call failed: {diagError}
            </div>
          )}
          {diagStatus !== 'done' && diagStatus !== 'error' && (
            <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-[12.5px] text-slate-400 dark:border-slate-700">
              {arrived.length === 0
                ? 'The AI correlation panel appears once real incidents start arriving.'
                : 'Tick the incidents you want analysed (or leave none ticked to send everything that has arrived), then click "Run AI correlation" — real ticket text, no synthetic logs behind it.'}
            </div>
          )}
          {diagStatus === 'done' && diagResult && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Badges rulesFired={rulesFired} rulesTotal={arrived.length} noiseRulesFired={0} />
              </div>
              <IncidentHeader meta={meta} summary={diagResult.incident_summary} />
              <Timeline items={diagResult.timeline} />
              <Hypotheses hypotheses={diagResult.hypotheses} eventsById={eventsById} />
              <RuledOut items={diagResult.ruled_out} />
              <Checks checks={diagResult.checks} />
              <BlastRadius data={diagResult.blast_radius} />
              <Recovery recovery={diagResult.recovery} />
              <div className="text-[10.5px] text-slate-400 dark:text-slate-500">
                Reasoning source: {diagResult._meta?.source ?? 'live'} · model {diagResult._meta?.model ?? '—'} · built from{' '}
                {sentCount} {sentWasHandpicked ? 'hand-selected' : 'arrived'}, real, redacted ServiceNow records — no
                synthetic telemetry.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
