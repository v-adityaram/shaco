import type { ReactNode } from 'react'
import type {
  ApplicationFailureRate,
  CriticalFlowRow,
  ExchangeRow,
  ExchangeStatus,
  KpiBlock,
  SonarDashboard as SonarDashboardT,
  TraceLevel,
  ZoneFailureRate,
} from '../lib/types'

export type TransitionPhase = 'idle' | 'freezing' | 'collapsing'

/* ------------------------------------------------------------------ formatting */

/** Kibana style "2026-09-18 @ 10:06:14.123", rendered in UTC (the data is UTC). */
function fmtTs(ts: string) {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} @ ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}.${p(d.getUTCMilliseconds(), 3)}`
}

function fmtDuration(ms: number) {
  if (ms < 1000) return `${ms.toFixed(2)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`
  if (ms < 3_600_000) return `${(ms / 60_000).toFixed(2)} min`
  return `${(ms / 3_600_000).toFixed(2)} h`
}

/* ------------------------------------------------------------------ palette (the real dashboard's tile/chip colours) */

const SONAR = {
  blue: '#6a6fd6',
  orange: '#ee8a45',
  green: '#4fb884',
  yellow: '#e9b33b',
  red: '#e05a75',
  grey: '#8b8f9a',
  teal: '#3fb1a6',
  sky: '#4a9fdc',
} as const
type Tone = keyof typeof SONAR

const STATUS_BG: Record<ExchangeStatus, string> = {
  COMPLETE: SONAR.green,
  'COMPLETE (F)': SONAR.green,
  INPROGRESS: SONAR.orange,
  FAILED: SONAR.red,
  WARNING: SONAR.yellow,
  REPLAYED: SONAR.grey,
}

const LEVEL_BG: Record<TraceLevel, string> = {
  ERROR: SONAR.red,
  INFO: SONAR.orange,
  ENTRYINFO: '#d9a066',
  EXITINFO: SONAR.green,
  WARN: SONAR.yellow,
}

function Chip({ bg, outline, children }: { bg: string; outline?: boolean; children: ReactNode }) {
  return (
    <span
      className="inline-block rounded-[3px] px-1.5 py-px text-[10px] leading-4 font-semibold whitespace-nowrap"
      style={outline ? { border: `1px solid ${bg}`, color: bg } : { background: bg, color: '#fff' }}
    >
      {children}
    </span>
  )
}

/* ------------------------------------------------------------------ KPI tiles */

/** Deterministic decorative sparkline (the dashboard's faint background trace; not data). */
function sparkPath(seed: string) {
  let h = 2166136261
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0
  let y = 0.55
  const pts: number[] = []
  for (let i = 0; i < 24; i++) {
    h = (Math.imul(h, 1664525) + 1013904223) >>> 0
    y = Math.min(0.85, Math.max(0.2, y + ((h % 1000) / 1000 - 0.5) * 0.3))
    pts.push(y)
  }
  const line = pts.map((v, i) => `${(i / 23) * 100},${(v * 30).toFixed(1)}`).join(' L')
  return `M0,30 L${line} L100,30 Z`
}

function Tile({ label, value, tone, seed }: { label: string; value: string | number; tone: Tone; seed: string }) {
  return (
    <div
      className="relative min-w-0 overflow-hidden rounded-[4px] px-2 pt-1.5 pb-1 text-white shadow-sm"
      style={{ background: SONAR[tone] }}
    >
      <svg
        viewBox="0 0 100 30"
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-3/5 w-full"
        aria-hidden
      >
        <path d={sparkPath(seed)} fill="#fff" fillOpacity="0.22" />
      </svg>
      <div className="relative truncate text-[10.5px] font-medium tracking-wide text-white/85">{label}</div>
      <div className="kpi-value relative leading-tight font-bold tabular-nums">{value}</div>
    </div>
  )
}

function KpiRow({ title, k }: { title: string; k: KpiBlock }) {
  const tiles: [string, string | number, Tone][] = [
    [title, k.exchanges, 'blue'],
    ['INPROGRESS', k.inprogress, 'orange'],
    ['COMPLETE', k.complete, 'green'],
    ['WARNING', k.warning, 'yellow'],
    ['FAILED', k.failed, 'red'],
    ['REPLAYED', k.replayed, 'grey'],
    ['Failures', `${(k.failurePct ?? 0).toFixed(2)}%`, 'teal'],
    ['Duration Avg', k.durationAvg, 'sky'],
    ['Duration Max', k.durationMax, 'sky'],
  ]
  return (
    <div className="grid grid-cols-9 gap-1.5">
      {tiles.map(([label, value, tone]) => (
        <Tile key={label} label={label} value={value} tone={tone} seed={`${title}:${label}`} />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ table helpers */

const TYPE_ICON = { date: '◷', str: 't', num: '#' } as const
function Th({
  icon,
  children,
  sort,
  className = '',
  w,
}: {
  icon: keyof typeof TYPE_ICON
  children: ReactNode
  sort?: boolean
  className?: string
  w?: string
}) {
  return (
    <th className={className} style={w ? { width: w } : undefined}>
      <span className="kb-muted mr-1 text-[9px]">{TYPE_ICON[icon]}</span>
      {children}
      {sort && <span className="kb-link ml-1">↓</span>}
    </th>
  )
}

function Highlight({ text, term }: { text: string; term: string }) {
  if (!term || !text.includes(term)) return <>{text}</>
  const parts = text.split(term)
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {i < parts.length - 1 && <mark className="rounded-[2px] bg-yellow-300 px-px text-black">{term}</mark>}
        </span>
      ))}
    </>
  )
}

function Panel({ title, docs, extra, children }: { title?: string; docs: number | string; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="kb-panel kb-bd overflow-hidden rounded-[4px] border shadow-sm">
      <div className="kb-bd flex min-w-0 items-center gap-3 border-b px-3 py-1.5">
        {title && <span className="text-[12px] font-semibold">{title}</span>}
        <span className="kb-muted text-[11px] whitespace-nowrap">{docs}</span>
        {extra}
      </div>
      {children}
    </section>
  )
}

/* ------------------------------------------------------------------ main */

function rowClasses(r: ExchangeRow, phase: TransitionPhase) {
  const hl = phase !== 'idle' && r.isAnomalous
  return [
    hl ? 'row-highlight' : r.isAnomalous ? 'row-anomalous' : '',
    phase === 'collapsing' && r.isAnomalous ? 'animate-fly-down' : '',
  ].join(' ')
}

// columns that only fit on wide screens; Kibana would scroll, we hide and note it in the footer
const LG = 'hidden xl:table-cell'
const XL = 'hidden 2xl:table-cell'
const XXL = 'hidden min-[1800px]:table-cell'

export function SonarDashboardView({
  dashboard,
  phase,
  docsLabel,
}: {
  dashboard: SonarDashboardT
  phase: TransitionPhase
  docsLabel?: string
}) {
  const { exchangeKpis, halfflowKpis, exchangeRows, traceFocus } = dashboard
  return (
    <div className="space-y-2">
      <KpiRow title="Exchanges" k={exchangeKpis} />
      <KpiRow title="HalfFlows" k={halfflowKpis} />

      <Panel docs={docsLabel ?? `${exchangeKpis.exchanges.toLocaleString('en-US')} documents`}>
        <table className="kb-table kb-table-wrap font-mono-tight w-full table-fixed text-[10.5px]">
          <thead>
            <tr>
              {/* percentage widths sum to 100 at every breakpoint (8 / 10 / 13 / 15 visible columns) */}
              <Th icon="date" sort className="w-[16%] xl:w-[14%] 2xl:w-[12%] min-[1800px]:w-[11%]">@timestamp</Th>
              <Th icon="str" className="w-[11%] xl:w-[10%] 2xl:w-[8%] min-[1800px]:w-[7%]">exchange.status</Th>
              <Th icon="str" className="w-[12%] xl:w-[10%] 2xl:w-[8%] min-[1800px]:w-[7%]">project</Th>
              <Th icon="str" className="w-[20%] xl:w-[17%] 2xl:w-[14%] min-[1800px]:w-[13%]">exchange</Th>
              <Th icon="str" className="w-[16%] xl:w-[14%] 2xl:w-[12%] min-[1800px]:w-[11%]">exchange.id</Th>
              <Th icon="num" className={`${LG} xl:w-[5%] 2xl:w-[4%] min-[1800px]:w-[4%]`}>halfflow.count</Th>
              <Th icon="str" className="w-[7%] xl:w-[6%] 2xl:w-[5%] min-[1800px]:w-[4%]">halfflow.missing</Th>
              <Th icon="num" className="w-[8%] xl:w-[7%] 2xl:w-[5%] min-[1800px]:w-[5%]">duration</Th>
              <Th icon="str" className="w-[10%] xl:w-[9%] 2xl:w-[8%] min-[1800px]:w-[7%]">source</Th>
              <Th icon="str" className={`${LG} xl:w-[8%] 2xl:w-[7%] min-[1800px]:w-[7%]`}>destination</Th>
              <Th icon="str" className={`${XL} 2xl:w-[6%] min-[1800px]:w-[6%]`}>object.id</Th>
              <Th icon="str" className={`${XL} 2xl:w-[6%] min-[1800px]:w-[6%]`}>object.name</Th>
              <Th icon="str" className={`${XL} 2xl:w-[5%] min-[1800px]:w-[5%]`}>event.code</Th>
              <Th icon="str" className={`${XXL} min-[1800px]:w-[4%]`}>business.value</Th>
              <Th icon="str" className={`${XXL} min-[1800px]:w-[3%]`}>framework</Th>
            </tr>
          </thead>
          <tbody>
            {exchangeRows.length === 0 && (
              <tr>
                <td colSpan={15} className="kb-muted py-6 text-center">No documents match the current filters.</td>
              </tr>
            )}
            {exchangeRows.map((r, i) => (
              <tr key={`${r.exchangeId}-${i}`} className={rowClasses(r, phase)}>
                <td className="kb-muted">{fmtTs(r.ts)}</td>
                <td>
                  <Chip bg={STATUS_BG[r.status] ?? SONAR.grey}>{r.status}</Chip>
                </td>
                <td>{r.project}</td>
                <td className="kb-link">{r.exchange}</td>
                <td>{r.exchangeId}</td>
                <td className={`${LG} text-right`}>{r.halfflowCount}</td>
                <td>{r.halfflowMissing}</td>
                <td className="text-right">{fmtDuration(r.durationMs)}</td>
                <td>{r.source}</td>
                <td className={LG}>{r.destination}</td>
                <td className={XL}>{r.objectId}</td>
                <td className={XL}>{r.objectName}</td>
                <td className={XL}>{r.eventCode}</td>
                <td className={XXL}>{r.businessValue}</td>
                <td className={XXL}>{r.frameworkVersion}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="kb-bd kb-muted flex items-center justify-between border-t px-3 py-1.5 text-[11px]">
          <span>Rows per page: 100 ▾</span>
          <span className="flex items-center gap-1">
            <span className="px-1">‹</span>
            {[1, 2, 3, 4, 5].map((n) => (
              <span key={n} className={`rounded px-1.5 ${n === 1 ? 'kb-link bg-sky-500/15 font-semibold' : ''}`}>
                {n}
              </span>
            ))}
            <span className="px-1">›</span>
          </span>
        </div>
      </Panel>

      <Panel
        title="Traces"
        docs={`${traceFocus.rows.length} documents`}
        extra={
          <span className="font-mono-tight kb-muted min-w-0 truncate text-[10px]">
            exchange: <span className="rounded-[2px] bg-yellow-300 px-1 text-black">{traceFocus.exchange}</span>
          </span>
        }
      >
        <table className="kb-table kb-table-wrap font-mono-tight w-full table-fixed text-[10.5px]">
          <thead>
            <tr>
              {/* 8 / 9 / 10 / 11 visible columns, widths sum to 100 at each breakpoint */}
              <Th icon="date" className="w-[15%] xl:w-[13%] 2xl:w-[12%] min-[1800px]:w-[11%]">@timestamp</Th>
              <Th icon="str" className="w-[9%] xl:w-[8%] 2xl:w-[7%] min-[1800px]:w-[7%]">event.level</Th>
              <Th icon="str" className="w-[17%] xl:w-[15%] 2xl:w-[13%] min-[1800px]:w-[12%]">exchange</Th>
              <Th icon="str" className="w-[13%] xl:w-[12%] 2xl:w-[11%] min-[1800px]:w-[10%]">exchange.id</Th>
              <Th icon="str" className="w-[17%] xl:w-[14%] 2xl:w-[13%] min-[1800px]:w-[12%]">halfflow</Th>
              <Th icon="str" className={`${LG} xl:w-[10%] 2xl:w-[9%] min-[1800px]:w-[8%]`}>halfflow.id</Th>
              <Th icon="str" className="w-[8%] xl:w-[7%] 2xl:w-[6%] min-[1800px]:w-[6%]">application</Th>
              <Th icon="str" className="w-[8%] xl:w-[7%] 2xl:w-[6%] min-[1800px]:w-[6%]">event.code</Th>
              <Th icon="str" className={`${XL} 2xl:w-[10%] min-[1800px]:w-[9%]`}>event.reason</Th>
              <Th icon="str" className="w-[13%] xl:w-[14%] 2xl:w-[13%] min-[1800px]:w-[14%]">message</Th>
              <Th icon="str" className={`${XXL} min-[1800px]:w-[5%]`}>business.value</Th>
            </tr>
          </thead>
          <tbody>
            {traceFocus.rows.length === 0 && (
              <tr>
                <td colSpan={11} className="kb-muted py-6 text-center">No trace events match the current filters.</td>
              </tr>
            )}
            {traceFocus.rows.map((t, i) => (
              <tr key={i}>
                <td className="kb-muted">{fmtTs(t.ts)}</td>
                <td>
                  <Chip bg={LEVEL_BG[t.level] ?? SONAR.orange} outline={t.level === 'INFO'}>
                    {t.level}
                  </Chip>
                </td>
                <td className="kb-link">
                  <Highlight text={t.exchange} term={traceFocus.exchange} />
                </td>
                <td>{t.exchangeId}</td>
                <td>{t.halfflow}</td>
                <td className={LG}>{t.halfflowId}</td>
                <td>{t.application}</td>
                <td>{t.eventCode}</td>
                <td className={XL}>{t.eventReason}</td>
                <td>{t.message}</td>
                <td className={XXL}>{t.businessValue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  )
}

/* ------------------------------------------------------------------ Global Overview
   ("Global Daily Flow Failure Report" in the real dashboard) -- a ranked
   failure-rate table plus zone/application health tiles, all derived from
   numbers already established on Screen 1 (see build_critical_flows() etc
   in scripts/build_alert_feed.py). */

/** Pale -> SONAR.red, non-linear so the top of the ranking pops the way the
 * real report's conditional-formatting gradient does. */
function failRateBg(pct: number) {
  const t = Math.min(1, Math.sqrt(Math.max(0, pct) / 100))
  const from = [253, 245, 246] // near-white with a faint red cast
  const to = [224, 90, 117] // SONAR.red
  const mix = from.map((c, i) => Math.round(c + (to[i] - c) * t))
  return `rgb(${mix.join(',')})`
}

function healthTone(pct: number): Tone {
  if (pct >= 8) return 'red'
  if (pct >= 3) return 'orange'
  return 'green'
}

function CriticalFlowsTable({ rows }: { rows: CriticalFlowRow[] }) {
  return (
    <table className="kb-table font-mono-tight w-full table-fixed text-[11px]">
      <thead>
        <tr>
          <Th icon="str" className="w-[46%]">Exchange</Th>
          <Th icon="num" className="w-[16%]">Total</Th>
          <Th icon="num" className="w-[16%]">Failed</Th>
          <Th icon="num" sort className="w-[22%]">Failed rate</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.exchange}>
            <td className="kb-link truncate">{r.exchange}</td>
            <td className="text-right tabular-nums">{r.total.toLocaleString('en-US')}</td>
            <td className="text-right tabular-nums">{r.failed.toLocaleString('en-US')}</td>
            <td className="p-0">
              <div
                className="px-2 py-1 text-right font-semibold text-black/80"
                style={{ background: failRateBg(r.failedRate) }}
              >
                {r.failedRate.toFixed(2)}%
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ZoneTiles({ rates }: { rates: ZoneFailureRate[] }) {
  const cols: [string, (r: ZoneFailureRate) => number][] = [
    ['current time range', (r) => r.currentPct],
    ['current time range - 1d', (r) => r.oneDayPct],
    ['current time range - 1w', (r) => r.oneWeekPct],
  ]
  return (
    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
      {rates.map((r) =>
        cols.map(([label, get]) => {
          const v = get(r)
          return (
            <div
              key={`${r.zone}-${label}`}
              className="rounded-[4px] px-3 py-2.5 text-white shadow-sm"
              style={{ background: SONAR[healthTone(v)] }}
            >
              <div className="text-[10.5px] font-medium tracking-wide text-white/85">
                {r.zone} - {label}
              </div>
              <div className="mt-1 text-[11px] font-medium text-white/90">Failure rate</div>
              <div className="text-xl leading-tight font-bold tabular-nums">{v.toFixed(2)}%</div>
            </div>
          )
        }),
      )}
    </div>
  )
}

function ApplicationTiles({ rates }: { rates: ApplicationFailureRate[] }) {
  return (
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
      {rates.map((a) => (
        <div
          key={a.application}
          className="rounded-[4px] px-3 py-2.5 text-white shadow-sm"
          style={{ background: SONAR[healthTone(a.pct)] }}
        >
          <div className="text-[10.5px] font-medium tracking-wide text-white/85">{a.application}</div>
          <div className="mt-1 text-[11px] font-medium text-white/90">Failure rate</div>
          <div className="text-xl leading-tight font-bold tabular-nums">{a.pct.toFixed(2)}%</div>
        </div>
      ))}
    </div>
  )
}

export function GlobalOverviewView({ dashboard }: { dashboard: SonarDashboardT }) {
  const { criticalFlows, failureRateByZone, failureRateByApplication } = dashboard
  return (
    <div className="space-y-3">
      <Panel title="Critical Flows" docs={`top ${criticalFlows.length} of the day's ranked flows`}>
        <CriticalFlowsTable rows={criticalFlows} />
      </Panel>
      <Panel title="Failure Rate by Zone" docs="">
        <div className="p-2">
          <ZoneTiles rates={failureRateByZone} />
        </div>
      </Panel>
      <Panel title="Failure Rate by Application" docs="">
        <div className="p-2">
          <ApplicationTiles rates={failureRateByApplication} />
        </div>
      </Panel>
    </div>
  )
}
