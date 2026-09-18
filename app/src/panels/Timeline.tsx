import { FactPanel } from '../components/PanelShell'
import type { TimelineItem } from '../lib/types'

const sourceColor: Record<string, string> = {
  ELK: 'text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/40',
  Kafka: 'text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-500/40',
  Apigee: 'text-sky-700 dark:text-sky-300 border-sky-300 dark:border-sky-500/40',
  APIM: 'text-cyan-700 dark:text-cyan-300 border-cyan-300 dark:border-cyan-500/40',
  MFT: 'text-lime-700 dark:text-lime-300 border-lime-300 dark:border-lime-500/40',
  ServiceNow: 'text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-500/40',
  DevOps: 'text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-500/40',
}

function toIST(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts
  }
}

export function Timeline({
  items,
  newEventId,
}: {
  items: TimelineItem[]
  newEventId?: string
}) {
  return (
    <FactPanel title="Observed timeline" className="max-h-[520px] overflow-y-auto">
      <ol className="space-y-0">
        {items.map((item) => (
          <li
            key={item.event_id}
            title={item.ts}
            className={[
              'relative border-l border-slate-300 dark:border-slate-700 py-2 pl-4',
              item.event_id === newEventId ? 'animate-slide-in-row rounded' : '',
            ].join(' ')}
          >
            <span className="absolute top-3 -left-[5px] h-2 w-2 rounded-full bg-slate-500" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono-tight text-[11px] text-slate-500 dark:text-slate-400">{toIST(item.ts)}</span>
              <span
                className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${
                  sourceColor[item.source] ?? 'text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600'
                }`}
              >
                {item.source}
              </span>
              <span className="text-[11px] text-slate-500">{item.component}</span>
              {item.is_first_symptom && (
                <span className="rounded bg-sky-100 dark:bg-sky-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-sky-700 dark:text-sky-300">
                  FIRST SYMPTOM
                </span>
              )}
              {item.event_id === newEventId && (
                <span className="rounded bg-emerald-100 dark:bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-700 dark:text-emerald-300">
                  NEWLY ARRIVED
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[12.5px] text-slate-600 dark:text-slate-300">{item.description}</div>
            <div className="font-mono-tight text-[10px] text-slate-500 dark:text-slate-600">{item.event_id}</div>
          </li>
        ))}
      </ol>
    </FactPanel>
  )
}
