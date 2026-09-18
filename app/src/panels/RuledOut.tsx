import { InferredPanel } from '../components/PanelShell'
import type { RuledOutItem } from '../lib/types'

export function RuledOut({ items }: { items: RuledOutItem[] }) {
  return (
    <InferredPanel title="Ruled out">
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-[12.5px]">
            <span className="mt-0.5 text-slate-600">✕</span>
            <div>
              <span className="text-slate-200 line-through decoration-slate-600">
                {item.candidate}
              </span>
              <div className="text-slate-400">{item.reason}</div>
            </div>
          </li>
        ))}
      </ul>
    </InferredPanel>
  )
}
