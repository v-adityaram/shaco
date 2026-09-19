export function Badges({
  rulesFired,
  rulesTotal,
  noiseRulesFired,
}: {
  rulesFired: number
  rulesTotal: number
  noiseRulesFired: number
}) {
  const pill =
    'rounded-full border border-slate-300 dark:border-slate-600/60 bg-slate-100 dark:bg-slate-800/60 px-2.5 py-1 text-slate-600 dark:text-slate-300'
  return (
    <div className="flex flex-wrap gap-2 text-[11px]">
      <span className={pill}>
        {rulesFired} of {rulesTotal} rules fired · all {rulesFired} consumed as evidence · 0 suppressed
      </span>
      <span className={pill}>{noiseRulesFired} alerts assessed as unrelated — see Ruled Out</span>
      <span className="px-1 py-1 text-slate-500">
        AI understands rule output; it does not replace or re-detect.
      </span>
    </div>
  )
}
