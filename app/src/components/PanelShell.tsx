export function FactPanel({
  title,
  children,
  className = '',
}: {
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-lg border border-slate-600/50 bg-slate-800/40 p-4 ${className}`}
    >
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-[13px] font-semibold tracking-wide text-slate-200 uppercase">
          {title}
        </h2>
        <span className="rounded-full border border-slate-500/40 px-1.5 py-0.5 text-[9px] font-medium text-slate-400">
          FACT
        </span>
      </div>
      {children}
    </section>
  )
}

export function InferredPanel({
  title,
  children,
  className = '',
}: {
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-lg border border-dashed border-indigo-400/40 bg-indigo-500/[0.06] p-4 ${className}`}
    >
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-[13px] font-semibold tracking-wide text-indigo-200 uppercase">
          {title}
        </h2>
        <span className="rounded-full border border-indigo-400/50 bg-indigo-500/10 px-1.5 py-0.5 text-[9px] font-medium text-indigo-300">
          INFERRED
        </span>
      </div>
      {children}
    </section>
  )
}
