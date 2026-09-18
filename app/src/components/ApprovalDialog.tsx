import { useEffect, useState } from 'react'

export interface ApprovalRecord {
  approver: string
  reason: string
  approvedAt: string
  evidenceCited: string
}

export function ApprovalDialog({
  proposal,
  onApprove,
  onClose,
}: {
  proposal: string
  onApprove: (record: ApprovalRecord) => void
  onClose: () => void
}) {
  const [approver, setApprover] = useState('')
  const [reason, setReason] = useState('')

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const canSubmit = approver.trim().length > 0 && reason.trim().length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-2xl">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Approve recovery action</h3>
        <p className="mt-2 rounded border border-dashed border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/5 px-3 py-2 text-[12px] text-amber-800/90 dark:text-amber-200/90">
          {proposal}
        </p>
        <label className="mt-4 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
          Approver name
          <input
            autoFocus
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
            placeholder="e.g. Priyanka Tota"
            className="mt-1 w-full rounded border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-950 px-2 py-1.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-sky-500"
          />
        </label>
        <label className="mt-3 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
          Reason for approval
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Offset and heap evidence confirm poison message; consumer group idle, safe to replay"
            rows={2}
            className="mt-1 w-full resize-none rounded border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-950 px-2 py-1.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-sky-500"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded px-3 py-1.5 text-[12px] text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            disabled={!canSubmit}
            onClick={() =>
              onApprove({
                approver: approver.trim(),
                reason: reason.trim(),
                approvedAt: new Date().toISOString(),
                evidenceCited: 'Top-ranked hypothesis, supporting evidence panel',
              })
            }
            className="rounded bg-sky-600 px-3 py-1.5 text-[12px] font-medium text-slate-900 dark:text-white disabled:cursor-not-allowed disabled:bg-slate-200 dark:disabled:bg-slate-700 disabled:text-slate-400 dark:disabled:text-slate-500"
          >
            Approve &amp; log
          </button>
        </div>
      </div>
    </div>
  )
}

export function ApprovalRecordCard({ record }: { record: ApprovalRecord }) {
  return (
    <div className="rounded border border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/5 px-3 py-2 text-[12px] text-emerald-800 dark:text-emerald-200">
      <div className="font-semibold">Action approved &amp; logged</div>
      <div className="mt-1 text-slate-600 dark:text-slate-300">
        <span className="text-slate-500">Who:</span> {record.approver} ·{' '}
        <span className="text-slate-500">When:</span>{' '}
        {new Date(record.approvedAt).toLocaleString()}
      </div>
      <div className="mt-0.5 text-slate-600 dark:text-slate-300">
        <span className="text-slate-500">Why:</span> {record.reason}
      </div>
      <div className="mt-0.5 text-slate-600 dark:text-slate-300">
        <span className="text-slate-500">On what evidence:</span> {record.evidenceCited}
      </div>
    </div>
  )
}
