import { useEffect, useState } from 'react'

/** Honest loading / error card for a live call. No fake progress, no invented steps. */
export function DiagnosisPending({
  status,
  startedAt,
  error,
  headline,
  onRetry,
}: {
  status: 'loading' | 'error'
  startedAt?: number
  error?: string
  headline: string
  onRetry: () => void
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (status !== 'loading') return
    const id = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(id)
  }, [status])
  const secs = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : null

  if (status === 'error') {
    return (
      <div className="mt-4 rounded-lg border border-rose-300 dark:border-rose-500/40 bg-rose-50 dark:bg-rose-500/5 p-4">
        <div className="text-[13px] font-semibold text-rose-700 dark:text-rose-300">The live analysis call failed</div>
        <p className="font-mono-tight mt-1 text-[11.5px] break-words text-rose-800/90 dark:text-rose-200/90">{error}</p>
        <button
          onClick={onRetry}
          className="mt-3 rounded-md border border-rose-300 dark:border-rose-500/50 bg-white dark:bg-transparent px-3 py-1.5 text-[12px] font-medium text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-500/10"
        >
          Retry
        </button>
      </div>
    )
  }
  return (
    <div className="mt-4 flex items-center gap-3 rounded-lg border border-slate-300 dark:border-slate-700/60 bg-white dark:bg-slate-800/40 p-4">
      <span className="h-2 w-2 animate-pulse-live rounded-full bg-sky-500" />
      <div className="text-[13px] text-slate-700 dark:text-slate-200">
        {headline} {secs !== null && <span className="font-mono-tight text-slate-500">{secs}s</span>}
      </div>
    </div>
  )
}
