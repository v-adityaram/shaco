import { FactPanel } from '../components/PanelShell'
import type { BlastRadius as BlastRadiusT } from '../lib/types'

export function BlastRadius({ data }: { data: BlastRadiusT }) {
  return (
    <FactPanel title="Blast radius">
      <div className="grid grid-cols-2 gap-3 text-[12.5px]">
        <div className="rounded bg-slate-900/50 p-2.5">
          <div className="text-[10px] tracking-wide text-slate-500 uppercase">Orders stuck</div>
          <div className="mt-0.5 text-lg font-semibold text-slate-100">
            {data.orders_stuck.toLocaleString()}
          </div>
        </div>
        {data.value_at_risk_inr != null && (
          <div className="rounded bg-slate-900/50 p-2.5">
            <div className="text-[10px] tracking-wide text-slate-500 uppercase">Value at risk</div>
            <div className="mt-0.5 text-lg font-semibold text-slate-100">
              ₹{data.value_at_risk_inr.toLocaleString('en-IN')}
            </div>
          </div>
        )}
        <div className="col-span-2 rounded bg-slate-900/50 p-2.5">
          <div className="text-[10px] tracking-wide text-slate-500 uppercase">
            Channels affected
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {data.channels.map((c) => (
              <span key={c} className="rounded bg-slate-700/60 px-1.5 py-0.5 text-[11px]">
                {c}
              </span>
            ))}
          </div>
        </div>
        <div className="col-span-2 rounded bg-slate-900/50 p-2.5">
          <div className="text-[10px] tracking-wide text-slate-500 uppercase">
            Downstream degraded
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {data.downstream_degraded.map((c) => (
              <span key={c} className="rounded bg-slate-700/60 px-1.5 py-0.5 text-[11px]">
                {c}
              </span>
            ))}
          </div>
        </div>
        {data.partner_feed_impacted != null && (
          <div className="col-span-2 text-[11.5px] text-slate-400">
            Partner B2B feed impacted:{' '}
            <span className={data.partner_feed_impacted ? 'text-amber-300' : 'text-emerald-300'}>
              {data.partner_feed_impacted ? 'Yes' : 'No'}
            </span>
          </div>
        )}
      </div>
    </FactPanel>
  )
}
