import type { EvidenceRef, NormalisedEvent } from '../lib/types'

function describeEvent(ev: EvidenceRef, eventsById: Map<string, NormalisedEvent>) {
  const src = eventsById.get(ev.event_id)
  return src ? `${src.source} · ${src.component}` : ev.event_id
}

export function EvidenceColumns({
  supports,
  contradicts,
  eventsById,
}: {
  supports: EvidenceRef[]
  contradicts: EvidenceRef[]
  eventsById: Map<string, NormalisedEvent>
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-emerald-400 uppercase">
          Supports
        </div>
        <ul className="space-y-1.5">
          {supports.map((s) => (
            <li
              key={s.event_id}
              className="rounded border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5 text-[12px] text-slate-300"
            >
              <div className="font-mono-tight text-[10px] text-emerald-400/80">
                {s.event_id} · {describeEvent(s, eventsById)}
              </div>
              {s.why}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-rose-400 uppercase">
          Contradicts
        </div>
        <ul className="space-y-1.5">
          {contradicts.map((c) => (
            <li
              key={c.event_id}
              className="rounded border border-rose-500/20 bg-rose-500/5 px-2 py-1.5 text-[12px] text-slate-300"
            >
              <div className="font-mono-tight text-[10px] text-rose-400/80">
                {c.event_id} · {describeEvent(c, eventsById)}
              </div>
              {c.why}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
