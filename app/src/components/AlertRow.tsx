import type { AlertRow as AlertRowT } from '../lib/types'

const severityColor: Record<AlertRowT['severity'], string> = {
  P1: 'border-l-red-500 text-red-200',
  P2: 'border-l-orange-400 text-orange-200',
  P3: 'border-l-amber-400 text-amber-200/90',
  P4: 'border-l-slate-500 text-slate-400',
}

function toClock(ts: string) {
  const m = ts.match(/T(\d{2}:\d{2}:\d{2})/)
  return m ? m[1] : ts
}

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
      className={[
        'font-mono-tight grid grid-cols-[68px_60px_110px_150px_1fr_34px] items-center gap-2 border-l-4 px-2 py-[3px] text-[11px] leading-tight whitespace-nowrap',
        severityColor[row.severity],
        dimmed ? 'opacity-25' : '',
        highlighted ? 'bg-sky-500/10' : '',
        flying ? 'animate-fly-down' : '',
        frozen ? '' : '',
      ].join(' ')}
    >
      <span className="truncate text-slate-500">{toClock(row.ts)}</span>
      <span className="truncate text-slate-400">{row.source}</span>
      <span className="truncate text-slate-500">{row.ruleId}</span>
      <span className="truncate text-slate-300">{row.component}</span>
      <span className="truncate">
        {row.isFirstSymptom && (
          <span className="mr-1 rounded bg-sky-500/20 px-1 text-[9px] text-sky-300">FIRST</span>
        )}
        {row.message}
      </span>
      <span className="text-right font-semibold">{row.severity}</span>
    </div>
  )
}
