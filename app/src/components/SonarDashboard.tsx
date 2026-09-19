import type { ReactNode } from 'react'
import type { ExchangeRow, ExchangeStatus, KpiBlock, SonarDashboard as SonarDashboardT, TraceLevel } from '../lib/types'

export type TransitionPhase = 'idle' | 'freezing' | 'collapsing'

/* ------------------------------------------------------------------ formatting */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Kibana style "Sep 18, 2026 @ 10:06:14.123", rendered in UTC (the data is UTC). */
function fmtTs(ts: string) {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${MONTHS[d.getUTCMonth()]} ${p(d.getUTCDate())}, ${d.getUTCFullYear()} @ ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}.${p(d.getUTCMilliseconds(), 3)}`
}

function fmtDuration(ms: number) {
  if (ms < 1000) return `${ms.toFixed(2)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`
  if (ms < 3_600_000) return `${(ms / 60_000).toFixed(2)} min`
  return `${(ms / 3_600_000).toFixed(2)} h`
}

/* ------------------------------------------------------------------ chips */

const STATUS_CHIP: Record<ExchangeStatus, string> = {
  COMPLETE: 'bg-emerald-200 text-emerald-900 dark:bg-emerald-500/25 dark:text-emerald-200',
  'COMPLETE (F)': 'bg-emerald-200 text-emerald-900 dark:bg-emerald-500/25 dark:text-emerald-200',
  INPROGRESS: 'bg-orange-200 text-orange-900 dark:bg-orange-500/25 dark:text-orange-200',
  FAILED: 'bg-red-200 text-red-900 dark:bg-red-500/30 dark:text-red-200',
  WARNING: 'bg-yellow-200 text-yellow-900 dark:bg-yellow-500/25 dark:text-yellow-200',
  REPLAYED: 'bg-slate-200 text-slate-700 dark:bg-slate-500/30 dark:text-slate-200',
}

const LEVEL_CHIP: Record<TraceLevel, string> = {
  ERROR: 'bg-red-200 text-red-900 dark:bg-red-500/30 dark:text-red-200',
  INFO: 'border border-orange-400 text-orange-700 dark:text-orange-300',
  ENTRYINFO: 'bg-amber-100 text-amber-900 dark:bg-amber-700/30 dark:text-amber-200',
  EXITINFO: 'bg-emerald-200 text-emerald-900 dark:bg-emerald-500/25 dark:text-emerald-200',
  WARN: 'bg-yellow-200 text-yellow-900 dark:bg-yellow-500/25 dark:text-yellow-200',
}

function Chip({ cls, children }: { cls: string; children: ReactNode }) {
  return (
    <span className={`inline-block rounded-[3px] px-1.5 py-px text-[10px] font-semibold ${cls}`}>{children}</span>
  )
}

/* ------------------------------------------------------------------ KPI tiles */

type Tone = 'blue' | 'orange' | 'green' | 'yellow' | 'red' | 'grey' | 'teal'
const TONE: Record<Tone, string> = {
  blue: 'text-sky-600 dark:text-sky-400',
  orange: 'text-orange-500 dark:text-orange-400',
  green: 'text-emerald-600 dark:text-emerald-400',
  yellow: 'text-yellow-500 dark:text-yellow-300',
  red: 'text-red-600 dark:text-red-400',
  grey: 'text-slate-500 dark:text-slate-400',
  teal: 'text-teal-600 dark:text-teal-400',
}

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
    <div className="kb-panel kb-bd relative min-w-0 overflow-hidden rounded border px-2 pt-1.5 pb-1">
      <svg
        viewBox="0 0 100 30"
        preserveAspectRatio="none"
        className={`pointer-events-none absolute inset-x-0 bottom-0 h-3/5 w-full opacity-[0.13] ${TONE[tone]}`}
        aria-hidden
      >
        <path d={sparkPath(seed)} fill="currentColor" />
      </svg>
      <div className="kb-muted relative truncate text-[10px]">{label}</div>
      <div className={`relative truncate leading-tight font-bold ${TONE[tone]} ${String(value).length <= 6 ? 'text-[18px]' : String(value).length <= 8 ? 'text-[14px]' : 'text-[12px]'}`}>{value}</div>
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
    ['Duration Avg', k.durationAvg, 'blue'],
    ['Duration Max', k.durationMax, 'blue'],
  ]
  return (
    <div className="grid grid-cols-[repeat(9,minmax(78px,1fr))] gap-1.5 overflow-x-auto">
      {tiles.map(([label, value, tone]) => (
        <Tile key={label} label={label} value={value} tone={tone} seed={`${title}:${label}`} />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ table helpers */

const TYPE_ICON = { date: '◷', str: 't', num: '#' } as const
function Th({ icon, children, sort }: { icon: keyof typeof TYPE_ICON; children: ReactNode; sort?: boolean }) {
  return (
    <th>
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
    <section className="kb-panel kb-bd rounded border">
      <div className="kb-bd flex items-center gap-3 border-b px-3 py-1.5">
        {title && <span className="text-[12px] font-semibold">{title}</span>}
        <span className="kb-muted text-[11px]">{docs} documents</span>
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
    hl ? 'bg-sky-500/15' : r.isAnomalous ? 'bg-amber-500/[0.07]' : '',
    phase === 'collapsing' && r.isAnomalous ? 'animate-fly-down' : '',
  ].join(' ')
}

export function SonarDashboardView({ dashboard, phase }: { dashboard: SonarDashboardT; phase: TransitionPhase }) {
  const { exchangeKpis, halfflowKpis, exchangeRows, traceFocus } = dashboard
  return (
    <div className="space-y-2">
      <KpiRow title="Exchanges" k={exchangeKpis} />
      <KpiRow title="HalfFlows" k={halfflowKpis} />

      <Panel docs={exchangeKpis.exchanges.toLocaleString('en-US')}>
        <div className="overflow-x-auto">
          <table className="kb-table font-mono-tight w-full text-[11px]">
            <thead>
              <tr>
                <Th icon="date" sort>@timestamp</Th>
                <Th icon="str">exchange.status</Th>
                <Th icon="str">project</Th>
                <Th icon="str">exchange</Th>
                <Th icon="str">exchange.id</Th>
                <Th icon="num">halfflow.count</Th>
                <Th icon="str">halfflow.missing</Th>
                <Th icon="num">duration</Th>
                <Th icon="str">source</Th>
                <Th icon="str">destination</Th>
                <Th icon="str">object.id</Th>
                <Th icon="str">object.name</Th>
                <Th icon="str">event.code</Th>
                <Th icon="str">business.value</Th>
                <Th icon="str">framework.version</Th>
              </tr>
            </thead>
            <tbody>
              {exchangeRows.map((r, i) => (
                <tr key={`${r.exchangeId}-${i}`} className={rowClasses(r, phase)}>
                  <td className="kb-muted">{fmtTs(r.ts)}</td>
                  <td>
                    <Chip cls={STATUS_CHIP[r.status] ?? STATUS_CHIP.REPLAYED}>{r.status}</Chip>
                  </td>
                  <td>{r.project}</td>
                  <td>{r.exchange}</td>
                  <td>{r.exchangeId}</td>
                  <td className="text-right">{r.halfflowCount}</td>
                  <td>{r.halfflowMissing}</td>
                  <td className="text-right">{fmtDuration(r.durationMs)}</td>
                  <td>{r.source}</td>
                  <td>{r.destination}</td>
                  <td>{r.objectId}</td>
                  <td>{r.objectName}</td>
                  <td>{r.eventCode}</td>
                  <td>{r.businessValue}</td>
                  <td>{r.frameworkVersion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="kb-bd kb-muted flex items-center justify-between border-t px-3 py-1 text-[11px]">
          <span>Rows per page: 100 ▾</span>
          <span className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <span key={n} className={`rounded px-1.5 ${n === 1 ? 'kb-link bg-sky-500/15 font-semibold' : ''}`}>
                {n}
              </span>
            ))}
          </span>
        </div>
      </Panel>

      <Panel
        title="Traces"
        docs={traceFocus.rows.length}
        extra={
          <span className="font-mono-tight kb-muted truncate text-[10px]">
            exchange: <span className="rounded-[2px] bg-yellow-300 px-1 text-black">{traceFocus.exchange}</span>
          </span>
        }
      >
        <div className="max-h-72 overflow-auto">
          <table className="kb-table font-mono-tight w-full text-[11px]">
            <thead>
              <tr>
                <Th icon="date">@timestamp</Th>
                <Th icon="str">event.level</Th>
                <Th icon="str">exchange</Th>
                <Th icon="str">exchange.id</Th>
                <Th icon="str">halfflow</Th>
                <Th icon="str">halfflow.id</Th>
                <Th icon="str">application</Th>
                <Th icon="str">event.code</Th>
                <Th icon="str">event.reason</Th>
                <Th icon="str">message</Th>
                <Th icon="str">business.value</Th>
              </tr>
            </thead>
            <tbody>
              {traceFocus.rows.map((t, i) => (
                <tr key={i}>
                  <td className="kb-muted">{fmtTs(t.ts)}</td>
                  <td>
                    <Chip cls={LEVEL_CHIP[t.level] ?? LEVEL_CHIP.INFO}>{t.level}</Chip>
                  </td>
                  <td>
                    <Highlight text={t.exchange} term={traceFocus.exchange} />
                  </td>
                  <td>{t.exchangeId}</td>
                  <td>{t.halfflow}</td>
                  <td>{t.halfflowId}</td>
                  <td>{t.application}</td>
                  <td>{t.eventCode}</td>
                  <td>{t.eventReason}</td>
                  <td>{t.message}</td>
                  <td>{t.businessValue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
