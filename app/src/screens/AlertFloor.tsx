import { useState, type ReactNode } from 'react'
import { ALERT_GRID, ALERT_RULE_CELL, AlertRow } from '../components/AlertRow'
import { BridgeTimer } from '../components/BridgeTimer'
import { SonarDashboardView, type TransitionPhase } from '../components/SonarDashboard'
import type { AlertRow as AlertRowT, ScenarioMeta, SonarDashboard } from '../lib/types'

const CHANNELS = [
  { name: '#hip-esb', unread: 34 },
  { name: '#hip-mft', unread: 12 },
  { name: '#hip-azure-platform', unread: 27 },
  { name: '#hip-workato', unread: 9 },
  { name: '#hip-kafka', unread: 6 },
  { name: '#hip-apigee', unread: 4 },
]

/* ---- L1 runbook panel: per-scenario query / actions (static presentation data) ---- */

interface L1Case {
  query: string
  actions: { text: string; tone?: 'warn' }[]
  staleRef: string
}

const KB_REPLAY = 'KB0041802 · Replay failed exchange'
const KB_REPUSH = 'KB0049334 · Repush file from MFT'
const KB_LAG = 'KB0043377 · Kafka consumer lag — generic triage'

const L1_BY_SLUG: Record<string, L1Case> = {
  's1-large-mapping-heap': {
    query: 'ASN not integrated S4 INPROGRESS consumer lag',
    actions: [
      { text: 'Replay of stuck ASN exchanges (KB0041802) — re-queued, still INPROGRESS' },
      { text: 'Escalated to L2' },
    ],
    staleRef: 'KB0038219 · Restart EMEA_SAPS4_ASN_OUT_02_ESB (half-flow renamed, no longer resolves)',
  },
  's2-pi7-listener-hang': {
    query: 'no deliveries SAP to Manhattan replay',
    actions: [
      { text: 'Replay attempted (KB0041802) — no effect', tone: 'warn' },
      { text: 'Escalated to L2' },
    ],
    staleRef: 'KB0036950 · Restart AN_COMMON_PI7IDOCListner_01 (half-flow renamed, no longer resolves)',
  },
  's3-vendor-release': {
    query: 'IDoc out failed ConfigForDocSending',
    actions: [
      { text: 'Replay of 3 failed IDocs (KB0041802) — failed again, same error', tone: 'warn' },
      { text: 'Escalated to L2' },
    ],
    staleRef: 'KB0037715 · Restart EURO_COMMON_IDOC_SAPCE_01 (half-flow renamed, no longer resolves)',
  },
  's4-stalled-exchange': {
    query: 'file INPROGRESS database locked FKF not generated',
    actions: [
      { text: 'Checked SFG transfer (KB0049334) — status SUCCESS, nothing to repush' },
      { text: 'Escalated to L2' },
    ],
    staleRef: 'KB0035102 · Repush GLBL_OPSF_ANAPLAN_BPM_to_FM_01 (half-flow renamed, no longer resolves)',
  },
  's5-transco-cache': {
    query: 'Connection refused transco-cache TranscoInvoke',
    actions: [
      { text: 'Replay succeeded (x6, KB0041802) — failures recur on other half-flows', tone: 'warn' },
      { text: 'Escalated to L2' },
    ],
    staleRef: 'KB0034481 · Restart EMEA_SAPIT_SALESORDER_01_ESB (half-flow renamed, no longer resolves)',
  },
}

const L1_DEFAULT: L1Case = {
  query: 'exchange INPROGRESS failed replay',
  actions: [{ text: 'Replay attempted — no effect', tone: 'warn' }, { text: 'Escalated to L2' }],
  staleRef: 'KB0038219 · Restart legacy half-flow (renamed, no longer resolves)',
}

/* ---- small icons ---- */

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

function NavRail() {
  const item = 'grid h-9 w-9 place-items-center rounded kb-muted kb-hover'
  return (
    <div className="kb-panel kb-bd flex w-11 shrink-0 flex-col items-center gap-1 border-r py-2">
      <div className="mb-1 grid h-8 w-8 place-items-center rounded bg-pink-500 text-[13px] font-bold text-white" title="Kibana">
        K
      </div>
      <div className={item} title="Discover">
        <Icon d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM15.5 8.5l-2 5-5 2 2-5z" />
      </div>
      <div className={`${item} kb-link bg-sky-500/10`} title="Dashboards">
        <Icon d="M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z" />
      </div>
    </div>
  )
}

const FILTERS = ['Project', 'Exchange', 'Exchange.status', 'Level.status', 'Source', 'Destination', 'Object.name']
const TABS = ['… Levels', 'Full Levels', 'Mass Replays', 'Exchange Overview', 'Global Overview', 'Status Overview']

function KibanaChrome({ windowLabel }: { windowLabel: string }) {
  const btn = 'kb-bd rounded border px-2 py-0.5 text-[11px] kb-hover'
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[12px]">
          <span className="kb-link">Dashboards</span> <span className="kb-muted">/</span> <span className="font-semibold">Full Levels</span>
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <span className="kb-link mr-2 text-[11px]">Sonar Concepts</span>
          <span className="kb-link mr-2 text-[11px]">Sonar DataModel</span>
          <button className={btn}>Full screen</button>
          <button className={btn}>Reset</button>
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="kb-panel kb-bd kb-muted flex h-7 min-w-0 flex-1 items-center rounded border px-2 text-[11px]">
          <span className="truncate">Filter your data using KQL syntax</span>
        </div>
        <div className="kb-panel kb-bd flex h-7 items-center gap-2 rounded border px-2 text-[11px]">
          <span className="kb-muted">‹</span>
          <span className="kb-link whitespace-nowrap">{windowLabel}</span>
          <span className="kb-muted">›</span>
          <span className="kb-muted" title="Zoom out">⊖</span>
        </div>
        <button className="rounded bg-sky-600 px-3 py-1 text-[11px] font-medium text-white">↻ Refresh</button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <div key={f} className="kb-panel kb-bd flex h-7 items-center gap-2 rounded border px-2 text-[11px]">
            <span className="kb-muted">{f}</span>
            <span>Any</span>
            <span className="kb-muted text-[9px]">▾</span>
          </div>
        ))}
      </div>
      <div className="kb-bd flex items-end gap-4 overflow-x-auto border-b text-[12px] whitespace-nowrap">
        {TABS.map((t) => (
          <span
            key={t}
            className={
              t === 'Full Levels'
                ? 'kb-link -mb-px border-b-2 border-sky-500 pb-1 font-semibold'
                : 'kb-muted pb-1'
            }
          >
            {t}
          </span>
        ))}
        
      </div>
    </div>
  )
}

/* ---- screen ---- */

export function AlertFloor({
  meta,
  rows,
  dashboard,
  rulesFired,
  rulesTotal,
  incidentRuleIds,
  transitionPhase,
  onRunCorrelation,
  controls,
}: {
  meta: ScenarioMeta
  rows: AlertRowT[]
  dashboard: SonarDashboard | undefined
  rulesFired: number
  rulesTotal: number
  incidentRuleIds: Set<string>
  transitionPhase: TransitionPhase
  onRunCorrelation: () => void
  /** scenario switcher + theme toggle, rendered inside the incident bar so nothing overlaps */
  controls?: ReactNode
}) {
  const [showAllRules, setShowAllRules] = useState(false)
  const l1 = L1_BY_SLUG[meta.slug] ?? L1_DEFAULT
  const frozen = transitionPhase !== 'idle'
  const firedRuleIds = Array.from(new Set(rows.filter((r) => r.ruleId !== '—').map((r) => r.ruleId)))

  if (!dashboard) console.error(`[AlertFloor] bundle "${meta.slug}" has no dashboard block`)

  return (
    <div className="kb-page flex h-full flex-col text-[12px]">
      {/* Incident header bar */}
      <div className="flex min-w-0 items-center gap-2 bg-slate-800 py-1.5 pr-3 pl-4 text-slate-100">
        <span className="font-mono-tight shrink-0 rounded bg-red-600 px-2 py-0.5 text-[11px] font-bold text-white">
          {meta.incidentNumber}
        </span>
        <span className="shrink-0 text-[12px] font-semibold text-red-300">P1</span>
        <span className="min-w-0 truncate text-[12px]" title={meta.title}>
          {meta.title}
        </span>
        <span className="hidden shrink-0 text-[11px] text-slate-400 xl:inline">· Assigned: HIP Ops L1 · State: In Progress</span>
        <span className="ml-auto flex shrink-0 items-center gap-1">
          <span className="mr-1 hidden text-[10px] text-slate-400 lg:inline">duplicates — same event:</span>
          {meta.duplicateIncidents.map((d) => (
            <span
              key={d}
              title="Raised by a different rule for the same event"
              className="font-mono-tight rounded border border-slate-500 px-1.5 py-0.5 text-[10px] text-slate-300"
            >
              {d}
            </span>
          ))}
        </span>
        {controls && <span className="ml-2 flex shrink-0 items-center gap-2 border-l border-slate-600 pl-3">{controls}</span>}
      </div>

      <div className="flex min-h-0 flex-1">
        <NavRail />

        {/* Team channels */}
        <div className="kb-panel kb-bd w-32 shrink-0 border-r p-2">
          <div className="kb-muted mb-2 text-[10px] tracking-wide uppercase">Team channels</div>
          <ul className="space-y-0.5">
            {CHANNELS.map((c) => (
              <li key={c.name} className="kb-hover flex items-center justify-between rounded px-1.5 py-1 text-[11px]">
                <span className="truncate">{c.name}</span>
                <span className="ml-1 rounded-full bg-red-500/15 px-1.5 text-[9px] font-semibold text-red-600 dark:text-red-300">
                  {c.unread}
                </span>
              </li>
            ))}
          </ul>
          <div className="kb-muted mt-3 text-[10px] leading-tight">
            Nobody is wrong. Everybody is looking at their own hop.
          </div>
        </div>

        {/* Sonar dashboard */}
        <div className="min-w-0 flex-1 space-y-2 overflow-y-auto p-3">
          <KibanaChrome windowLabel={dashboard?.windowLabel ?? 'Last 24 hours'} />
          {dashboard ? (
            <SonarDashboardView dashboard={dashboard} phase={transitionPhase} />
          ) : (
            <div className="rounded border border-red-400 bg-red-500/10 p-3 text-[12px] text-red-700 dark:text-red-300">
              This scenario bundle has no <code>dashboard</code> block — the Sonar view cannot be rendered.
            </div>
          )}
        </div>

        {/* Right column: HIPMON stream + L1 panel */}
        <div className="kb-panel kb-bd flex w-[380px] shrink-0 flex-col border-l 2xl:w-[440px]">
          <div className="kb-bd flex items-center gap-2 border-b px-2 py-1.5">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${frozen ? 'bg-slate-400' : 'animate-pulse-live bg-red-500'}`} />
            <span className="text-[11px] font-semibold whitespace-nowrap">HIPMON stream</span>
            <span className="font-mono-tight kb-muted text-[10px] whitespace-nowrap">
              {rows.length} rows{frozen ? ' · frozen' : ''}
            </span>
            <button
              onClick={() => setShowAllRules((v) => !v)}
              className="kb-muted ml-auto text-[10px] whitespace-nowrap underline decoration-dotted hover:opacity-80"
            >
              {showAllRules ? 'Hide' : 'Show'} rules
            </button>
            <button
              onClick={onRunCorrelation}
              className="rounded bg-sky-600 px-2.5 py-1 text-[11px] font-semibold whitespace-nowrap text-white shadow hover:bg-sky-500"
            >
              Run AI correlation →
            </button>
          </div>

          {showAllRules && (
            <div className="kb-bd kb-panel2 max-h-32 shrink-0 overflow-y-auto border-b px-2 py-1.5 text-[10px]">
              <div className="kb-muted mb-1">
                {rulesTotal} rules configured · {rulesFired} fired in this window (highlighted) ·{' '}
                {rulesTotal - rulesFired} silent. Nothing suppressed; nothing hidden.
              </div>
              <div className="flex flex-wrap gap-1">
                {firedRuleIds.map((id) => (
                  <span key={id} className="font-mono-tight rounded bg-sky-500/15 px-1 text-sky-700 dark:text-sky-300">
                    {id}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
            <div>
              <div
                className={`font-mono-tight kb-muted kb-bd kb-panel2 sticky top-0 z-10 grid gap-1.5 border-b border-l-4 border-l-transparent px-2 py-0.5 text-[9px] uppercase ${ALERT_GRID}`}
              >
                <span>time</span>
                <span>source</span>
                <span className={ALERT_RULE_CELL}>rule</span>
                <span>component</span>
                <span>message</span>
                <span className="text-right">sev</span>
              </div>
              {rows.map((row, i) => {
                const isFiller = row.ruleId === '—'
                const isIncidentRow = incidentRuleIds.has(row.ruleId) && !row.isNoise && !isFiller
                return (
                  <AlertRow
                    key={`${row.ts}-${i}`}
                    row={row}
                    frozen={frozen}
                    highlighted={frozen && isIncidentRow}
                    dimmed={frozen && (row.isNoise || isFiller)}
                    flying={transitionPhase === 'collapsing' && isIncidentRow}
                  />
                )
              })}
            </div>
          </div>

          <div className="kb-bd kb-panel2 max-h-[42%] shrink-0 overflow-y-auto border-t p-2.5">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="kb-muted text-[10px] font-semibold tracking-wide uppercase">L1 panel</span>
              <span className="rounded bg-amber-500/15 px-1.5 py-px text-[9.5px] font-semibold text-amber-700 dark:text-amber-400">
                awaiting bridge
              </span>
            </div>
            <div className="kb-muted text-[10px]">
              Runbook search:{' '}
              <span className="font-mono-tight text-(--kb-text)" title={l1.query}>
                "{l1.query}"
              </span>
            </div>
            <ul className="mt-1 space-y-1">
              {[KB_REPLAY, KB_REPUSH, KB_LAG, l1.staleRef].map((r) => {
                const stale = r === l1.staleRef
                return (
                  <li
                    key={r}
                    title={stale ? `${r} — stale runbook` : r}
                    className={[
                      'kb-panel rounded border px-2 py-1 text-[10.5px]',
                      stale
                        ? 'line-clamp-2 border-amber-500/50 bg-amber-500/10 leading-snug text-amber-700 dark:text-amber-400'
                        : 'truncate'
                        + ' kb-bd kb-muted',
                    ].join(' ')}
                  >
                    {r}
                  </li>
                )
              })}
            </ul>
            <div className="mt-1 text-[10.5px] text-rose-600 dark:text-rose-400">
              None matching the cross-system symptom set
            </div>
            <ul className="mt-2 space-y-0.5 text-[10.5px] leading-snug">
              {l1.actions.map((a) => (
                <li key={a.text} className={a.tone === 'warn' ? 'text-amber-700 dark:text-amber-400' : ''}>
                  ✔ {a.text}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <BridgeTimer />
    </div>
  )
}
