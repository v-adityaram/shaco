export function Badges({
  rulesFired,
  rulesTotal,
  ruledOutCount,
}: {
  rulesFired: number
  rulesTotal: number
  ruledOutCount: number
}) {
  return (
    <div className="flex flex-wrap gap-2 text-[11px]">
      <span className="rounded-full border border-slate-300 dark:border-slate-600/60 bg-slate-100 dark:bg-slate-800/60 px-2.5 py-1 text-slate-600 dark:text-slate-300">
        {rulesFired} of {rulesTotal} ELK rules fired · all {rulesFired} consumed as evidence · 0
        suppressed
      </span>
      <span className="rounded-full border border-slate-300 dark:border-slate-600/60 bg-slate-100 dark:bg-slate-800/60 px-2.5 py-1 text-slate-600 dark:text-slate-300">
        {ruledOutCount} alerts assessed as unrelated — see Ruled Out
      </span>
    </div>
  )
}
