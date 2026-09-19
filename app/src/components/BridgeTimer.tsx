import { useEffect, useState } from 'react'

const START_SECONDS = 74 * 60 + 22 // 01:14:22

function format(totalSeconds: number) {
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
}

export function BridgeTimer({ causeAgreed }: { causeAgreed?: string }) {
  const [elapsed, setElapsed] = useState(START_SECONDS)

  useEffect(() => {
    const id = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-slate-300 bg-white/90 px-4 py-2 text-[12px] dark:border-slate-800 dark:bg-slate-950/90">
      <span className="h-2 w-2 animate-pulse-live rounded-full bg-red-500" />
      <span className="font-mono-tight text-base font-bold text-red-600 dark:text-red-400">{format(elapsed)}</span>
      <span className="text-slate-500">6 engineers on bridge</span>
      <span className="text-slate-400 dark:text-slate-600">·</span>
      <span className="text-slate-500">
        {causeAgreed ? 'Agreed cause: none · AI-proposed (not yet agreed):' : 'Agreed cause:'}{' '}
        <span className={causeAgreed ? 'text-sky-600 dark:text-sky-400' : 'text-slate-700 dark:text-slate-300'}>
          {causeAgreed ?? 'none'}
        </span>
      </span>
      <span className="text-slate-400 dark:text-slate-600">·</span>
      <span className="text-amber-600 dark:text-amber-400">Customer impact: ongoing</span>
    </div>
  )
}
