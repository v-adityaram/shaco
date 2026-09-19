import { normaliseSource } from '../lib/sources'
import type { SourceSystem } from '../lib/types'

const STYLES: Record<SourceSystem, string> = {
  SONAR: 'text-teal-700 dark:text-teal-300 border-teal-400 dark:border-teal-500/50',
  HIPMON: 'text-rose-700 dark:text-rose-300 border-rose-400 dark:border-rose-500/50',
  Splunk: 'text-lime-700 dark:text-lime-300 border-lime-500 dark:border-lime-500/50',
  Kafka: 'text-violet-700 dark:text-violet-300 border-violet-400 dark:border-violet-500/50',
  Workato: 'text-sky-700 dark:text-sky-300 border-sky-400 dark:border-sky-500/50',
  Apigee: 'text-orange-700 dark:text-orange-300 border-orange-400 dark:border-orange-500/50',
  MFT: 'text-amber-700 dark:text-amber-300 border-amber-500 dark:border-amber-500/50',
  ServiceNow: 'text-emerald-700 dark:text-emerald-300 border-emerald-500 dark:border-emerald-500/50',
  Change: 'text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-400 dark:border-fuchsia-500/50',
}

export function SourceBadge({ source }: { source: string }) {
  const k = normaliseSource(source)
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${
        k ? STYLES[k] : 'border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-300'
      }`}
    >
      {k ? k.toUpperCase() : source}
    </span>
  )
}
