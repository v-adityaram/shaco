import { useState } from 'react'

const KEY = 'shaco-layerstack-open'

function readOpen() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

function Chevron({ down }: { down?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="12"
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={down ? 'M6 9l6 6 6-6' : 'M9 6l6 6-6 6'} />
    </svg>
  )
}

/** Where the AI sits relative to the existing rules. Starts minimised so it never covers the content;
 *  click the pill to expand, click the header to minimise again. The choice is remembered. */
export function LayerStack() {
  const [open, setOpen] = useState(readOpen)

  function set(v: boolean) {
    setOpen(v)
    try {
      localStorage.setItem(KEY, v ? '1' : '0')
    } catch {
      // storage unavailable: the toggle still works for this visit
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => set(true)}
        aria-expanded={false}
        aria-label="Show where the AI sits in the stack"
        className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-slate-300 bg-white/90 px-3 py-1.5 text-[11px] font-medium text-slate-600 shadow-md backdrop-blur-sm transition hover:bg-white hover:text-slate-900 dark:border-slate-700/60 dark:bg-slate-900/80 dark:text-slate-300 dark:hover:text-white"
      >
        Layers <Chevron />
      </button>
    )
  }

  return (
    <div className="pointer-events-auto w-56 rounded-lg border border-slate-300 bg-white/95 p-2 text-[10px] leading-tight shadow-lg backdrop-blur-sm dark:border-slate-700/60 dark:bg-slate-900/85">
      <button
        onClick={() => set(false)}
        aria-expanded
        aria-label="Minimise the layers card"
        className="mb-1.5 flex w-full items-center justify-between rounded px-1 py-0.5 text-[10px] font-semibold tracking-wide text-slate-500 uppercase hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
      >
        Where the AI sits <Chevron down />
      </button>
      <div className="rounded border border-sky-300 bg-sky-100 px-2 py-1.5 font-medium text-sky-700 dark:border-sky-500/40 dark:bg-sky-500/10 dark:text-sky-300">
        AI correlation &amp; reasoning <span className="text-sky-600/70 dark:text-sky-400/70">(new)</span>
      </div>
      <div className="mt-1 rounded border border-slate-200 bg-slate-100 px-2 py-1.5 text-slate-600 dark:border-slate-600/50 dark:bg-slate-800/60 dark:text-slate-300">
        HIPMON · Sonar · Splunk · Kafka
        <br />
        Workato · MFT · ServiceNow · CHG
        <span className="block text-slate-500">unchanged</span>
      </div>
      <div className="mt-1 rounded border border-slate-200 bg-slate-50 px-2 py-1.5 text-slate-500 dark:border-slate-700/50 dark:bg-slate-800/30 dark:text-slate-400">
        HIP production estate
        <span className="block text-slate-500">unchanged</span>
      </div>
    </div>
  )
}
