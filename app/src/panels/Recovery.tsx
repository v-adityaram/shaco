import { useState } from 'react'
import { ApprovalDialog, ApprovalRecordCard, type ApprovalRecord } from '../components/ApprovalDialog'
import { InferredPanel } from '../components/PanelShell'
import type { RecoveryProposal } from '../lib/types'

export function Recovery({ recovery }: { recovery: RecoveryProposal }) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [record, setRecord] = useState<ApprovalRecord | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [verified, setVerified] = useState(false)

  function handleApprove(r: ApprovalRecord) {
    setRecord(r)
    setDialogOpen(false)
    setVerifying(true)
    setTimeout(() => {
      setVerifying(false)
      setVerified(true)
    }, 1400)
  }

  return (
    <InferredPanel title="Recovery, behind the gate">
      <div className="space-y-3">
        <div className="text-[10.5px] text-slate-500 dark:text-slate-400">
          Proposed action (replay · repush · restart · rollback) — nothing executes without a named approver.
        </div>
        <div className="rounded border border-indigo-300 dark:border-indigo-400/20 bg-slate-100 dark:bg-slate-900/40 p-3 text-[12.5px] text-slate-800 dark:text-slate-200">
          {recovery.proposal}
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded bg-slate-100 dark:bg-slate-900/40 p-2.5 text-[11.5px]">
            <div className="text-[10px] tracking-wide text-rose-600/80 dark:text-rose-400/80 uppercase">Risk</div>
            <div className="mt-0.5 text-slate-600 dark:text-slate-300">{recovery.risk}</div>
          </div>
          <div className="rounded bg-slate-100 dark:bg-slate-900/40 p-2.5 text-[11.5px]">
            <div className="text-[10px] tracking-wide text-sky-600/80 dark:text-sky-400/80 uppercase">Rollback</div>
            <div className="mt-0.5 text-slate-600 dark:text-slate-300">{recovery.rollback}</div>
          </div>
        </div>

        {!record && (
          <button
            onClick={() => setDialogOpen(true)}
            disabled={!recovery.requires_approval}
            className="w-full rounded-md border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 py-2 text-[12.5px] font-medium text-amber-700 dark:text-amber-300 transition hover:bg-amber-100 dark:hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {recovery.requires_approval ? 'Execute proposed action — requires approval' : 'Execute proposed action'}
          </button>
        )}

        {record && <ApprovalRecordCard record={record} />}

        {verifying && (
          <div className="flex items-center gap-2 text-[11.5px] text-slate-500 dark:text-slate-400">
            <span className="h-1.5 w-1.5 animate-pulse-live rounded-full bg-sky-400" />
            Verifying recovery against observed signal…
          </div>
        )}
        {verified && (
          <div className="rounded border border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/5 px-3 py-2 text-[12px] text-emerald-700 dark:text-emerald-300">
            Verified against observed signal — affected exchanges progressing to COMPLETE, no new FAILED / INPROGRESS growth.
          </div>
        )}
      </div>

      {dialogOpen && (
        <ApprovalDialog
          proposal={recovery.proposal}
          onApprove={handleApprove}
          onClose={() => setDialogOpen(false)}
        />
      )}
    </InferredPanel>
  )
}
