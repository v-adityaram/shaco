import { InferredPanel } from '../components/PanelShell'
import type { DiagnosticCheck } from '../lib/types'

const effortStyle: Record<DiagnosticCheck['effort'], string> = {
  low: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  medium: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300',
  high: 'bg-rose-100 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300',
}

export function Checks({ checks }: { checks: DiagnosticCheck[] }) {
  return (
    <InferredPanel title="Diagnostic checks">
      <ol className="space-y-2.5">
        {checks
          .slice()
          .sort((a, b) => a.order - b.order)
          .map((c) => (
            <li key={c.order} className="rounded border border-indigo-300 dark:border-indigo-400/20 bg-slate-100 dark:bg-slate-900/40 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12.5px] font-medium text-slate-900 dark:text-slate-100">
                  {c.order}. {c.action}
                </span>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${effortStyle[c.effort]}`}
                >
                  {c.effort} effort
                </span>
              </div>
              <div className="font-mono-tight mt-1.5 rounded bg-slate-200/60 dark:bg-slate-950/60 px-2 py-1 text-[11px] text-slate-500 dark:text-slate-400">
                {c.command}
              </div>
              <div className="mt-1.5 grid grid-cols-1 gap-1 text-[11px] sm:grid-cols-2">
                <div className="text-slate-500 dark:text-slate-400">
                  <span className="text-emerald-600/80 dark:text-emerald-400/80">If A:</span> {c.if_result_a}
                </div>
                <div className="text-slate-500 dark:text-slate-400">
                  <span className="text-sky-600/80 dark:text-sky-400/80">If B:</span> {c.if_result_b}
                </div>
              </div>
            </li>
          ))}
      </ol>
    </InferredPanel>
  )
}
