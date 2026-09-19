import { FactPanel } from '../components/PanelShell'
import type { BlastRadius as BlastRadiusT } from '../lib/types'

function Chips({ items }: { items: string[] }) {
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {items.map((c) => (
        <span key={c} className="rounded bg-slate-200 dark:bg-slate-700/60 px-1.5 py-0.5 text-[11px]">
          {c}
        </span>
      ))}
    </div>
  )
}

const label = 'text-[10px] tracking-wide text-slate-500 uppercase'
const cell = 'rounded bg-slate-100 dark:bg-slate-900/50 p-2.5'

export function BlastRadius({ data }: { data: BlastRadiusT }) {
  return (
    <FactPanel title="Blast radius">
      <div className="grid grid-cols-2 gap-3 text-[12.5px]">
        <div className={cell}>
          <div className={label}>Exchanges stuck / failed</div>
          <div className="mt-0.5 text-lg font-semibold text-slate-900 dark:text-slate-100">
            {(data.exchanges_stuck ?? 0).toLocaleString()}
          </div>
        </div>
        <div className={cell}>
          <div className={label}>Zones</div>
          <Chips items={data.zones ?? []} />
        </div>
        <div className={`col-span-2 ${cell}`}>
          <div className={label}>Business flows affected</div>
          <Chips items={data.business_flows ?? []} />
        </div>
        <div className={`col-span-2 ${cell}`}>
          <div className={label}>Downstream degraded</div>
          <Chips items={data.downstream_degraded ?? []} />
        </div>
        {data.business_objects_at_risk && (
          <div className={`col-span-2 ${cell}`}>
            <div className={label}>Business objects at risk</div>
            <div className="mt-1 text-[12px] text-slate-700 dark:text-slate-200">
              {data.business_objects_at_risk}
            </div>
          </div>
        )}
      </div>
    </FactPanel>
  )
}
