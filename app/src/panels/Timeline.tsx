import { FactPanel } from '../components/PanelShell'
import { SourceBadge } from '../components/SourceBadge'
import type { NormalisedEvent, TimelineItem } from '../lib/types'

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
  eventsById,
}: {
  items: TimelineItem[]
  newEventId?: string
  eventsById?: Map<string, NormalisedEvent>
}) {
  return (
    <FactPanel title="Observed timeline" className="max-h-[520px] overflow-y-auto">
      <ol className="space-y-0">
        {items.map((item) => {
          const ev = eventsById?.get(item.event_id)
          const kind = ev?.kind
          const ruleId = ev?.rule_id
          return (
          <li
            key={item.event_id}
            title={`${item.ts} (UTC)`}
            className={[
              'relative border-l border-slate-300 dark:border-slate-700 py-2 pl-4',
              item.event_id === newEventId ? 'animate-slide-in-row rounded' : '',
            ].join(' ')}
          >
            <span className="absolute top-3 -left-[5px] h-2 w-2 rounded-full bg-slate-500" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono-tight text-[11px] text-slate-500 dark:text-slate-400">
                {toIST(item.ts)} <span className="text-[9px]">IST</span>
              </span>
              <SourceBadge source={item.source} />
              {kind === 'rule_hit' && (
                <span className="font-mono-tight rounded bg-slate-200 dark:bg-slate-700/60 px-1.5 py-0.5 text-[9px] text-slate-600 dark:text-slate-300">
                  RULE{ruleId ? ` · ${ruleId}` : ''}
                </span>
              )}
              {kind === 'context' && (
                <span className="rounded border border-slate-300 dark:border-slate-600 px-1.5 py-0.5 text-[9px] text-slate-500 dark:text-slate-400">
                  CONTEXT
                </span>
              )}
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
          )
        })}
      </ol>
    </FactPanel>
  )
}
