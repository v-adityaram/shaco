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
    <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 bg-slate-950/90 px-4 py-2 text-[12px]">
      <span className="h-2 w-2 animate-pulse-live rounded-full bg-red-500" />
      <span className="font-mono-tight text-base font-bold text-red-400">{format(elapsed)}</span>
      <span className="text-slate-500">6 engineers on bridge</span>
      <span className="text-slate-600">·</span>
      <span className="text-slate-500">
        Agreed cause:{' '}
        <span className={causeAgreed ? 'text-emerald-400' : 'text-slate-300'}>
          {causeAgreed ?? 'none'}
        </span>
      </span>
      <span className="text-slate-600">·</span>
      <span className="text-amber-400">Customer impact: ongoing</span>
    </div>
  )
}
