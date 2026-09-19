import type { AlertRow as AlertRowT } from '../lib/types'
import { sourceTextClass } from './sourceText'

const severityColor: Record<AlertRowT['severity'], string> = {
  P1: 'border-l-red-500 text-red-700 dark:text-red-200',
  P2: 'border-l-orange-500 text-orange-700 dark:text-orange-200',
  P3: 'border-l-amber-500 text-amber-700 dark:text-amber-200/90',
  P4: 'border-l-slate-400 dark:border-l-slate-500 text-slate-500 dark:text-slate-400',
}

function toClock(ts: string) {
  const m = ts.match(/T(\d{2}:\d{2}:\d{2})/)
  return m ? m[1] : ts
}

/** One HIPMON-stream row. Grid template is exported so the header row lines up.
 *  Every column is bounded so the stream always fits its column — no horizontal scroll. */
export const ALERT_GRID =
  'grid-cols-[52px_50px_minmax(0,1fr)_minmax(0,1.4fr)_20px] 2xl:grid-cols-[52px_52px_64px_minmax(0,1.1fr)_minmax(0,1.5fr)_20px]'
/** the rule column only fits on wide screens; the row tooltip and "Show rules" cover it elsewhere */
export const ALERT_RULE_CELL = 'hidden 2xl:block'

export function AlertRow({
  row,
  frozen,
  dimmed,
  highlighted,
  flying,
}: {
  row: AlertRowT
  frozen?: boolean
  dimmed?: boolean
  highlighted?: boolean
  flying?: boolean
}) {
  return (
    <div
      data-frozen={frozen ? '' : undefined}
      title={`${row.ruleId !== '—' ? row.ruleId + ' · ' : ''}${row.component} — ${row.message}`}
      className={[
        'font-mono-tight grid items-center gap-1.5 border-l-4 px-2 py-[3px] text-[11px] leading-tight whitespace-nowrap',
        ALERT_GRID,
        severityColor[row.severity],
        dimmed ? 'opacity-30' : '',
        highlighted ? 'bg-sky-500/10' : '',
        flying ? 'animate-fly-down' : '',
      ].join(' ')}
    >
      <span className="kb-muted truncate">{toClock(row.ts)}</span>
      <span className={`truncate ${sourceTextClass(row.source)}`}>{row.source}</span>
      <span className={`kb-muted truncate ${ALERT_RULE_CELL}`}>{row.ruleId}</span>
      <span className="truncate text-(--kb-text)">{row.component}</span>
      <span className="truncate">
        {row.isFirstSymptom && (
          <span className="mr-1 rounded bg-sky-500/20 px-1 text-[9px] text-sky-700 dark:text-sky-300">FIRST</span>
        )}
        {row.message}
      </span>
      <span className="text-right font-semibold">{row.severity}</span>
    </div>
  )
}
