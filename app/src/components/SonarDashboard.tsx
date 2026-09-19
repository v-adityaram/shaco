import type { ReactNode } from 'react'
import type { ExchangeRow, ExchangeStatus, KpiBlock, SonarDashboard as SonarDashboardT, TraceLevel } from '../lib/types'

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
        <span className="kb-muted text-[11px] whitespace-nowrap">{docs} documents</span>
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
const XL = 'hidden 2xl:table-cell'
const XXL = 'hidden min-[1800px]:table-cell'

export function SonarDashboardView({ dashboard, phase }: { dashboard: SonarDashboardT; phase: TransitionPhase }) {
  const { exchangeKpis, halfflowKpis, exchangeRows, traceFocus } = dashboard
  return (
    <div className="space-y-2">
      <KpiRow title="Exchanges" k={exchangeKpis} />
      <KpiRow title="HalfFlows" k={halfflowKpis} />

      <Panel docs={exchangeKpis.exchanges.toLocaleString('en-US')}>
        <table className="kb-table kb-table-wrap font-mono-tight w-full table-fixed text-[10.5px]">
          <thead>
            <tr>
              <Th icon="date" sort className="w-[118px] 2xl:w-[164px]">@timestamp</Th>
              <Th icon="str" w="92px">exchange.status</Th>
              <Th icon="str" w="9%">project</Th>
              <Th icon="str" w="16%">exchange</Th>
              <Th icon="str" className="w-[104px] 2xl:w-[170px]">exchange.id</Th>
              <Th icon="num" w="52px">halfflow.count</Th>
              <Th icon="str" w="60px">halfflow.missing</Th>
              <Th icon="num" w="66px">duration</Th>
              <Th icon="str">source</Th>
              <Th icon="str">destination</Th>
              <Th icon="str" className={XL}>object.id</Th>
              <Th icon="str" className={XL}>object.name</Th>
              <Th icon="str" className={XL} w="68px">event.code</Th>
              <Th icon="str" className={XXL}>business.value</Th>
              <Th icon="str" className={XXL} w="58px">framework</Th>
            </tr>
          </thead>
          <tbody>
            {exchangeRows.map((r, i) => (
              <tr key={`${r.exchangeId}-${i}`} className={rowClasses(r, phase)}>
                <td className="kb-muted">{fmtTs(r.ts)}</td>
                <td>
                  <Chip bg={STATUS_BG[r.status] ?? SONAR.grey}>{r.status}</Chip>
                </td>
                <td>{r.project}</td>
                <td className="kb-link">{r.exchange}</td>
                <td>{r.exchangeId}</td>
                <td className="text-right">{r.halfflowCount}</td>
                <td>{r.halfflowMissing}</td>
                <td className="text-right">{fmtDuration(r.durationMs)}</td>
                <td>{r.source}</td>
                <td>{r.destination}</td>
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
        docs={traceFocus.rows.length}
        extra={
          <span className="font-mono-tight kb-muted min-w-0 truncate text-[10px]">
            exchange: <span className="rounded-[2px] bg-yellow-300 px-1 text-black">{traceFocus.exchange}</span>
          </span>
        }
      >
        <table className="kb-table kb-table-wrap font-mono-tight w-full table-fixed text-[10.5px]">
          <thead>
            <tr>
              <Th icon="date" className="w-[118px] 2xl:w-[164px]">@timestamp</Th>
              <Th icon="str" w="78px">event.level</Th>
              <Th icon="str">exchange</Th>
              <Th icon="str">exchange.id</Th>
              <Th icon="str">halfflow</Th>
              <Th icon="str">halfflow.id</Th>
              <Th icon="str" w="70px">application</Th>
              <Th icon="str" w="70px">event.code</Th>
              <Th icon="str" className={XL}>event.reason</Th>
              <Th icon="str" w="20%">message</Th>
              <Th icon="str" className={XXL}>business.value</Th>
            </tr>
          </thead>
          <tbody>
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
                <td>{t.halfflowId}</td>
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
