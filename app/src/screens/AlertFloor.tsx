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

type FilterKey = 'project' | 'exchange' | 'status' | 'level' | 'source' | 'destination' | 'objectName'
export type Filters = Partial<Record<FilterKey, string>>

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'project', label: 'Project' },
  { key: 'exchange', label: 'Exchange' },
  { key: 'status', label: 'Exchange.status' },
  { key: 'level', label: 'Level.status' },
  { key: 'source', label: 'Source' },
  { key: 'destination', label: 'Destination' },
  { key: 'objectName', label: 'Object.name' },
]
const TABS = ['… Levels', 'Full Levels', 'Mass Replays', 'Exchange Overview', 'Global Overview', 'Status Overview']

function FilterPill({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  const active = value !== ''
  return (
    <label
      className={`kb-panel flex h-7 cursor-pointer items-center gap-1.5 rounded border px-2 text-[11px] ${
        active ? 'border-sky-500 bg-sky-500/10' : 'kb-bd kb-hover'
      }`}
    >
      <span className="kb-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className="max-w-[180px] cursor-pointer truncate bg-transparent pr-0.5 text-(--kb-text) outline-none"
      >
        <option value="">Any</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  )
}

function KibanaChrome({
  windowLabel,
  filters,
  options,
  onFilter,
  kql,
  onKql,
  onReset,
  onRefresh,
  refreshing,
  fullscreen,
  onFullscreen,
  tab,
  onTab,
}: {
  windowLabel: string
  filters: Filters
  options: Record<FilterKey, string[]>
  onFilter: (k: FilterKey, v: string) => void
  kql: string
  onKql: (v: string) => void
  onReset: () => void
  onRefresh: () => void
  refreshing: boolean
  fullscreen: boolean
  onFullscreen: () => void
  tab: string
  onTab: (t: string) => void
}) {
  const btn = 'kb-bd kb-hover rounded border px-2 py-0.5 text-[11px]'
  const dirty = kql !== '' || Object.values(filters).some(Boolean)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[12px]">
          <span className="kb-link">Dashboards</span> <span className="kb-muted">/</span> <span className="font-semibold">Full Levels</span>
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <a className="kb-link mr-2 text-[11px]" href="#sonar-concepts" onClick={(e) => e.preventDefault()}>
            Sonar Concepts
          </a>
          <a className="kb-link mr-2 text-[11px]" href="#sonar-datamodel" onClick={(e) => e.preventDefault()}>
            Sonar DataModel
          </a>
          <button className={`${btn} ${fullscreen ? 'kb-link border-sky-500 bg-sky-500/10' : ''}`} onClick={onFullscreen}>
            {fullscreen ? 'Exit full screen' : 'Full screen'}
          </button>
          <button className={`${btn} ${dirty ? '' : 'opacity-50'}`} onClick={onReset} disabled={!dirty}>
            Reset
          </button>
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="kb-panel kb-bd flex h-7 min-w-0 flex-1 items-center rounded border px-2 text-[11px] focus-within:border-sky-500">
          <span className="kb-muted mr-1.5">⌕</span>
          <input
            value={kql}
            onChange={(e) => onKql(e.target.value)}
            placeholder="Filter your data using KQL syntax"
            className="w-full bg-transparent text-(--kb-text) outline-none placeholder:text-(--kb-muted)"
          />
          {kql && (
            <button className="kb-muted ml-1 px-1 hover:opacity-70" onClick={() => onKql('')} title="Clear">
              ×
            </button>
          )}
        </div>
        <div className="kb-panel kb-bd flex h-7 items-center gap-2 rounded border px-2 text-[11px]">
          <span className="kb-muted">‹</span>
          <span className="kb-link whitespace-nowrap">{windowLabel}</span>
          <span className="kb-muted">›</span>
          <span className="kb-muted" title="Zoom out">⊖</span>
        </div>
        <button
          onClick={onRefresh}
          className="flex items-center gap-1 rounded bg-sky-600 px-3 py-1 text-[11px] font-medium text-white hover:bg-sky-500"
        >
          <span className={refreshing ? 'inline-block animate-spin' : ''}>↻</span> Refresh
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <FilterPill key={f.key} label={f.label} value={filters[f.key] ?? ''} options={options[f.key]} onChange={(v) => onFilter(f.key, v)} />
        ))}
      </div>
      <div className="kb-bd flex items-end gap-4 overflow-x-auto border-b text-[12px] whitespace-nowrap">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => onTab(t)}
            className={t === tab ? 'kb-link -mb-px border-b-2 border-sky-500 pb-1 font-semibold' : 'kb-muted pb-1 hover:text-(--kb-text)'}
          >
            {t}
          </button>
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
  const [filters, setFilters] = useState<Filters>({})
  const [kql, setKql] = useState('')
  const [tab, setTab] = useState('Full Levels')
  const [fullscreen, setFullscreen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const l1 = L1_BY_SLUG[meta.slug] ?? L1_DEFAULT
  const frozen = transitionPhase !== 'idle'
  const firedRuleIds = Array.from(new Set(rows.filter((r) => r.ruleId !== '—').map((r) => r.ruleId)))

  if (!dashboard) console.error(`[AlertFloor] bundle "${meta.slug}" has no dashboard block`)

  const uniq = (xs: string[]) => Array.from(new Set(xs.filter(Boolean))).sort()
  const exRows = dashboard?.exchangeRows ?? []
  const trRows = dashboard?.traceFocus.rows ?? []
  const options: Record<FilterKey, string[]> = {
    project: uniq(exRows.map((r) => r.project)),
    exchange: uniq(exRows.map((r) => r.exchange)),
    status: uniq(exRows.map((r) => r.status)),
    level: uniq(trRows.map((t) => t.level)),
    source: uniq(exRows.map((r) => r.source)),
    destination: uniq(exRows.map((r) => r.destination)),
    objectName: uniq(exRows.map((r) => r.objectName)),
  }
  const q = kql.trim().toLowerCase()
  const matchesKql = (r: object) => !q || Object.values(r).some((v) => String(v).toLowerCase().includes(q))
  const filteredExchanges = exRows.filter(
    (r) =>
      (!filters.project || r.project === filters.project) &&
      (!filters.exchange || r.exchange === filters.exchange) &&
      (!filters.status || r.status === filters.status) &&
      (!filters.source || r.source === filters.source) &&
      (!filters.destination || r.destination === filters.destination) &&
      (!filters.objectName || r.objectName === filters.objectName) &&
      matchesKql(r),
  )
  const filteredTraces = trRows.filter((t) => (!filters.level || t.level === filters.level) && matchesKql(t))
  const filtering = q !== '' || Object.values(filters).some(Boolean)
  const view = dashboard && {
    ...dashboard,
    exchangeRows: filteredExchanges,
    traceFocus: { ...dashboard.traceFocus, rows: filteredTraces },
  }

  function refresh() {
    setRefreshing(true)
    window.setTimeout(() => setRefreshing(false), 600)
  }
  function reset() {
    setFilters({})
    setKql('')
  }

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
        {!fullscreen && <NavRail />}

        {/* Team channels */}
        <div className={`kb-panel kb-bd w-32 shrink-0 border-r p-2 ${fullscreen ? 'hidden' : ''}`}>
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
          <KibanaChrome
            windowLabel={dashboard?.windowLabel ?? 'Last 24 hours'}
            filters={filters}
            options={options}
            onFilter={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
            kql={kql}
            onKql={setKql}
            onReset={reset}
            onRefresh={refresh}
            refreshing={refreshing}
            fullscreen={fullscreen}
            onFullscreen={() => setFullscreen((v) => !v)}
            tab={tab}
            onTab={setTab}
          />
          {tab !== 'Full Levels' ? (
            <div className="kb-panel kb-bd grid h-64 place-items-center rounded-[4px] border text-center shadow-sm">
              <div>
                <div className="text-[13px] font-semibold">{tab}</div>
                <div className="kb-muted mt-1 text-[11px]">
                  This view is not part of the POC.{' '}
                  <button className="kb-link underline decoration-dotted" onClick={() => setTab('Full Levels')}>
                    Back to Full Levels
                  </button>
                </div>
              </div>
            </div>
          ) : view ? (
            <SonarDashboardView
              dashboard={view}
              phase={transitionPhase}
              docsLabel={
                filtering
                  ? `${filteredExchanges.length} of ${view.exchangeKpis.exchanges.toLocaleString('en-US')} documents · filtered`
                  : undefined
              }
            />
          ) : (
            <div className="rounded border border-red-400 bg-red-500/10 p-3 text-[12px] text-red-700 dark:text-red-300">
              This scenario bundle has no <code>dashboard</code> block — the Sonar view cannot be rendered.
            </div>
          )}
        </div>

        {/* Right column: HIPMON stream + L1 panel */}
        <div className="kb-panel kb-bd flex w-[340px] shrink-0 flex-col border-l xl:w-[380px] 2xl:w-[440px]">
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
