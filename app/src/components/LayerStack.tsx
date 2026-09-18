export function LayerStack() {
  return (
    <div className="w-56 rounded-lg border border-slate-700/60 bg-slate-900/70 p-2 text-[10px] leading-tight shadow-lg backdrop-blur-sm">
      <div className="rounded border border-sky-500/40 bg-sky-500/10 px-2 py-1.5 font-medium text-sky-300">
        AI correlation &amp; reasoning <span className="text-sky-400/70">(new)</span>
      </div>
      <div className="mt-1 rounded border border-slate-600/50 bg-slate-800/60 px-2 py-1.5 text-slate-300">
        ELK rules · Kafka · APIM · MFT
        <br />
        ServiceNow · change records
        <span className="block text-slate-500">unchanged</span>
      </div>
      <div className="mt-1 rounded border border-slate-700/50 bg-slate-800/30 px-2 py-1.5 text-slate-400">
        Production estate
        <span className="block text-slate-500">unchanged</span>
      </div>
    </div>
  )
}
