import type { ScenarioMeta } from '../lib/types'

export function IncidentHeader({
  meta,
  summary,
}: {
  meta: ScenarioMeta
  summary?: string
}) {
  return (
    <div className="rounded-lg border border-slate-300 dark:border-slate-700/60 bg-slate-100 dark:bg-slate-800/60 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-rose-100 dark:bg-rose-500/20 px-2 py-0.5 text-[11px] font-bold text-rose-700 dark:text-rose-300">
          P1
        </span>
        <span className="font-mono-tight text-[13px] font-medium text-slate-900 dark:text-slate-100">
          {meta.incidentNumber}
        </span>
        <span className="text-[13px] text-slate-600 dark:text-slate-300">{meta.title}</span>
        <span className="ml-auto flex flex-wrap gap-1">
          {meta.duplicateIncidents.map((d) => (
            <span
              key={d}
              title="Merged — describes the same event"
              className="font-mono-tight rounded border border-slate-300 dark:border-slate-600/60 px-1.5 py-0.5 text-[10px] text-slate-500 line-through decoration-slate-400 dark:decoration-slate-600"
            >
              {d}
            </span>
          ))}
        </span>
      </div>
      {summary && <p className="mt-2 text-[14px] leading-snug text-slate-900 dark:text-slate-100">{summary}</p>}
    </div>
  )
}
