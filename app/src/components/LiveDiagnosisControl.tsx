export type DiagnosisSource = 'Cached' | 'Live' | 'Server cache'

type Status = 'idle' | 'loading' | 'error' | 'done'

const sourceStyle: Record<DiagnosisSource, string> = {
  Cached: 'border-slate-300 dark:border-slate-600/60 bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300',
  Live: 'border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  'Server cache': 'border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300',
}

export function SourceLabel({ source, model }: { source: DiagnosisSource; model?: string }) {
  return (
    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${sourceStyle[source]}`} title="Where the reasoning on screen came from">
      Reasoning: {source}
      {source === 'Live' && model ? ` · ${model}` : ''}
    </span>
  )
}

/** Live toggle for curated scenarios (ai-live scenarios only get the SourceLabel). */
export function LiveDiagnosisControl({
  status,
  elapsed,
  error,
  showingLive,
  disabled,
  onRunLive,
  onBackToCached,
}: {
  status: Status
  elapsed: number
  error: string | null
  showingLive: boolean
  disabled?: boolean
  onRunLive: () => void
  onBackToCached: () => void
}) {
  if (showingLive && status === 'done') {
    return (
      <button
        onClick={onBackToCached}
        disabled={disabled}
        className="text-[10.5px] text-slate-500 underline decoration-dotted hover:text-slate-800 disabled:opacity-40 dark:hover:text-slate-200"
      >
        back to cached
      </button>
    )
  }

  if (status === 'loading') {
    return (
      <div className="flex items-center gap-2 rounded-full border border-sky-300 dark:border-sky-500/40 bg-sky-50 dark:bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-700 dark:text-sky-300">
        <span className="h-1.5 w-1.5 animate-pulse-live rounded-full bg-sky-500" />
        Calling model live… {elapsed}s
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onRunLive}
        disabled={disabled}
        title={disabled ? 'Not available after late evidence has been injected' : 'Calls the model via the local server — can take 30–90s; replaces the cached diagnosis when it arrives'}
        className="rounded-full border border-sky-300 dark:border-sky-500/40 bg-sky-50 dark:bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-700 transition hover:bg-sky-100 disabled:opacity-40 dark:text-sky-300 dark:hover:bg-sky-500/20"
      >
        {status === 'error' ? 'Retry live →' : 'Run live →'}
      </button>
      {status === 'error' && error && (
        <span className="max-w-xs truncate text-[10.5px] text-rose-600 dark:text-rose-400" title={error}>
          {error}
        </span>
      )}
    </div>
  )
}
