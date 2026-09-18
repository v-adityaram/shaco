export function ScenarioSwitcher({
  slugs,
  labels,
  active,
  onChange,
}: {
  slugs: string[]
  labels: Record<string, string>
  active: string
  onChange: (slug: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-1 rounded-lg border border-slate-300 dark:border-slate-700/60 bg-white dark:bg-slate-900/60 p-1">
      {slugs.map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={[
            'rounded px-2.5 py-1 text-[11px] font-medium transition',
            s === active
              ? 'bg-sky-600 text-slate-900 dark:text-white'
              : 'text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200',
          ].join(' ')}
        >
          {labels[s] ?? s}
        </button>
      ))}
    </div>
  )
}
