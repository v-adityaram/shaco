import { EvidenceColumns } from '../components/EvidenceColumns'
import { InferredPanel } from '../components/PanelShell'
import type { Hypothesis, NormalisedEvent } from '../lib/types'

const confidenceStyle: Record<Hypothesis['confidence'], string> = {
  High: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/40',
  Moderate: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/40',
  Low: 'bg-slate-200 dark:bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-500/40',
}

export function Hypotheses({
  hypotheses,
  eventsById,
}: {
  hypotheses: Hypothesis[]
  eventsById: Map<string, NormalisedEvent>
}) {
  return (
    <InferredPanel title="Candidate causes">
      <div className="space-y-4">
        {hypotheses
          .slice()
          .sort((a, b) => a.rank - b.rank)
          .map((h) => (
            <div
              key={h.rank}
              className="rounded-lg border border-indigo-300 dark:border-indigo-400/25 bg-slate-100 dark:bg-slate-900/40 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-[11px] font-bold text-indigo-700 dark:text-indigo-300">#{h.rank}</span>
                  <span className="text-[13.5px] font-medium text-slate-900 dark:text-slate-100">{h.cause}</span>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${confidenceStyle[h.confidence]}`}
                >
                  {h.confidence}
                </span>
              </div>
              <div className="mt-3">
                <EvidenceColumns
                  supports={h.supports}
                  contradicts={h.contradicts}
                  eventsById={eventsById}
                />
              </div>
              <div className="mt-3 border-t border-slate-200 dark:border-slate-700/50 pt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-600 dark:text-slate-300">What would change this: </span>
                {h.what_would_change_this}
              </div>
            </div>
          ))}
      </div>
    </InferredPanel>
  )
}
