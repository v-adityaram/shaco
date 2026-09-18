type Status = 'idle' | 'loading' | 'error' | 'done'

export function LiveDiagnosisControl({
  status,
  elapsed,
  error,
  onRunLive,
  onBackToCached,
}: {
  status: Status
  elapsed: number
  error: string | null
  onRunLive: () => void
  onBackToCached: () => void
}) {
  if (status === 'done') {
    return (
      <div className="flex items-center gap-2 rounded-full border border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        LIVE · gpt-5
        <button
          onClick={onBackToCached}
          className="ml-1 text-[10px] text-emerald-600/80 underline decoration-dotted hover:text-emerald-800 dark:text-emerald-400/80 dark:hover:text-emerald-200"
        >
          back to cached
        </button>
      </div>
    )
  }

  if (status === 'loading') {
    return (
      <div className="flex items-center gap-2 rounded-full border border-sky-300 dark:border-sky-500/40 bg-sky-50 dark:bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-700 dark:text-sky-300">
        <span className="h-1.5 w-1.5 animate-pulse-live rounded-full bg-sky-500" />
        Calling gpt-5 live… {elapsed}s
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onRunLive}
        title="Calls the real model via the thin local server — can take 30–90s"
        className="rounded-full border border-sky-300 dark:border-sky-500/40 bg-sky-50 dark:bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-700 transition hover:bg-sky-100 dark:text-sky-300 dark:hover:bg-sky-500/20"
      >
        Run live (gpt-5) →
      </button>
      {status === 'error' && error && (
        <span className="max-w-xs truncate text-[10.5px] text-rose-600 dark:text-rose-400" title={error}>
          {error}
        </span>
      )}
    </div>
  )
}
