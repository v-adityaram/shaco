export function LayerStack() {
  return (
    <div className="w-56 rounded-lg border border-slate-300 dark:border-slate-700/60 bg-white/90 dark:bg-slate-900/70 p-2 text-[10px] leading-tight shadow-lg backdrop-blur-sm">
      <div className="rounded border border-sky-300 dark:border-sky-500/40 bg-sky-100 dark:bg-sky-500/10 px-2 py-1.5 font-medium text-sky-700 dark:text-sky-300">
        AI correlation &amp; reasoning <span className="text-sky-600/70 dark:text-sky-400/70">(new)</span>
      </div>
      <div className="mt-1 rounded border border-slate-200 dark:border-slate-600/50 bg-slate-100 dark:bg-slate-800/60 px-2 py-1.5 text-slate-600 dark:text-slate-300">
        HIPMON · Sonar · Splunk · Kafka
        <br />
        Workato · MFT · ServiceNow · CHG
        <span className="block text-slate-500">unchanged</span>
      </div>
      <div className="mt-1 rounded border border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/30 px-2 py-1.5 text-slate-500 dark:text-slate-400">
        HIP production estate
        <span className="block text-slate-500">unchanged</span>
      </div>
    </div>
  )
}
