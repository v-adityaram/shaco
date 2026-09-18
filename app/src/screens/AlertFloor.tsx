import { useState } from 'react'
import { AlertRow } from '../components/AlertRow'
import { BridgeTimer } from '../components/BridgeTimer'
import type { AlertRow as AlertRowT, ScenarioMeta } from '../lib/types'

const CHANNELS = [
  { name: '#ch-order-platform', unread: 23 },
  { name: '#ch-inventory', unread: 41 },
  { name: '#ch-integration', unread: 8 },
  { name: '#ch-channel-eng', unread: 17 },
  { name: '#ch-infra-dba', unread: 12 },
]

const RUNBOOK_CANDIDATES = [
  'RB-0442 · OOMKilled — generic pod restart',
  'RB-0198 · inv-resv-svc high memory (renamed 8mo ago, no longer resolves)',
  'RB-0511 · Kafka consumer lag — generic',
]

export function AlertFloor({
  meta,
  rows,
  rulesFired,
  rulesTotal,
  incidentRuleIds,
  transitionPhase,
  onRunCorrelation,
}: {
  meta: ScenarioMeta
  rows: AlertRowT[]
  rulesFired: number
  rulesTotal: number
  incidentRuleIds: Set<string>
  transitionPhase: 'idle' | 'freezing' | 'collapsing'
  onRunCorrelation: () => void
}) {
  const [showAllRules, setShowAllRules] = useState(false)

  return (
    <div className="flex h-full flex-col bg-black text-slate-300">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-950 px-4 py-2">
        <span className="rounded bg-red-600 px-2 py-0.5 font-mono-tight text-[11px] font-bold text-white">
          {meta.incidentNumber}
        </span>
        <span className="text-[12px] font-semibold text-red-400">P1</span>
        <span className="text-[12px] text-slate-300">{meta.title}</span>
        <span className="text-[11px] text-slate-500">
          · Assigned: L1 Command Centre · State: In Progress
        </span>
        <span className="ml-auto flex gap-1">
          {meta.duplicateIncidents.map((d) => (
            <span
              key={d}
              className="font-mono-tight rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-500"
              title="Describes the same event"
            >
              {d}
            </span>
          ))}
        </span>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* Left rail */}
        <div className="hidden w-44 shrink-0 border-r border-slate-800 bg-slate-950 p-2 md:block">
          <div className="mb-2 text-[10px] tracking-wide text-slate-600 uppercase">
            Team channels
          </div>
          <ul className="space-y-1">
            {CHANNELS.map((c) => (
              <li
                key={c.name}
                className="flex items-center justify-between rounded px-1.5 py-1 text-[11px] text-slate-400 hover:bg-slate-900"
              >
                <span className="truncate">{c.name}</span>
                <span className="ml-1 rounded-full bg-slate-800 px-1.5 text-[9px] text-slate-500">
                  {c.unread}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3 text-[10px] leading-tight text-slate-600">
            Nobody is wrong. Everybody is looking at their own hop.
          </div>
        </div>

        {/* Center feed */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5">
            <span className="font-mono-tight text-[10px] text-slate-600">
              {rows.length} alerts · 6 min window
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAllRules((v) => !v)}
                className="text-[10px] text-slate-500 underline decoration-dotted hover:text-slate-300"
              >
                {showAllRules ? 'Hide' : 'Show'} all firing rules
              </button>
              <button
                onClick={onRunCorrelation}
                className="rounded bg-sky-600 px-3 py-1 text-[11px] font-semibold text-white shadow-lg shadow-sky-900/40 hover:bg-sky-500"
              >
                Run AI correlation →
              </button>
            </div>
          </div>

          {showAllRules && (
            <div className="max-h-32 overflow-y-auto border-b border-slate-800 bg-slate-950 px-3 py-2 text-[10px] text-slate-500">
              412 rules configured · {rulesFired} fired in this window (highlighted) ·{' '}
              {rulesTotal - rulesFired} silent. Nothing suppressed; nothing hidden.
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
            {rows.map((row, i) => {
              const isFiller = row.ruleId === '—'
              const isIncidentRow = incidentRuleIds.has(row.ruleId) && !row.isNoise && !isFiller
              const dimmed = transitionPhase !== 'idle' && (row.isNoise || isFiller)
              const flying = transitionPhase === 'collapsing' && isIncidentRow
              return (
                <AlertRow
                  key={`${row.ts}-${i}`}
                  row={row}
                  highlighted={transitionPhase !== 'idle' && isIncidentRow}
                  dimmed={dimmed}
                  flying={flying}
                />
              )
            })}
          </div>
        </div>

        {/* Right rail */}
        <div className="hidden w-56 shrink-0 border-l border-slate-800 bg-slate-950 p-3 lg:block">
          <div className="mb-2 text-[10px] tracking-wide text-slate-600 uppercase">L1 panel</div>
          <div className="mb-3">
            <div className="text-[10px] text-slate-500">Runbook search: "OOMKilled inventory"</div>
            <ul className="mt-1 space-y-1">
              {RUNBOOK_CANDIDATES.map((r) => (
                <li
                  key={r}
                  className={[
                    'rounded border px-1.5 py-1 text-[10px]',
                    r.includes('renamed')
                      ? 'border-amber-700/50 bg-amber-900/10 text-amber-400'
                      : 'border-slate-800 text-slate-500',
                  ].join(' ')}
                >
                  {r}
                </li>
              ))}
            </ul>
            <div className="mt-1 text-[10px] text-rose-400">
              None matching the cross-system symptom set
            </div>
          </div>
          <ul className="space-y-1 text-[11px] text-slate-400">
            <li>✔ Action taken: restart pod (×2) — no effect</li>
            <li>✔ Action taken: escalate to L2</li>
            <li className="text-amber-400">State: awaiting bridge</li>
          </ul>
        </div>
      </div>

      <BridgeTimer />
    </div>
  )
}
