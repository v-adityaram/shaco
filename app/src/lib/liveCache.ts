import { useSyncExternalStore } from 'react'
import { fetchDiagnosis, fetchLateEvidence } from './ai'
import type { DiagnosisResult, LateEvidenceResult, NormalisedEvent } from './types'

/**
 * Module-level memo of live calls: one in-flight request per slug, results kept
 * so switching scenarios (or remounting the AI view) never re-calls the model.
 */
export type LiveEntry<T> =
  | { status: 'loading'; startedAt: number }
  | { status: 'done'; startedAt: number; result: T }
  | { status: 'error'; startedAt: number; error: string }

interface State {
  diag: Record<string, LiveEntry<DiagnosisResult>>
  late: Record<string, LiveEntry<LateEvidenceResult>>
}

let state: State = { diag: {}, late: {} }
const listeners = new Set<() => void>()

function set(next: State) {
  state = next
  listeners.forEach((l) => l())
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function ensureDiagnosis(slug: string, events: NormalisedEvent[], opts: { retry?: boolean } = {}) {
  const cur = state.diag[slug]
  if (cur && !(opts.retry && cur.status === 'error')) return
  const startedAt = Date.now()
  set({ ...state, diag: { ...state.diag, [slug]: { status: 'loading', startedAt } } })
  fetchDiagnosis(slug, events).then(
    (result) => set({ ...state, diag: { ...state.diag, [slug]: { status: 'done', startedAt, result } } }),
    (err) =>
      set({
        ...state,
        diag: {
          ...state.diag,
          [slug]: { status: 'error', startedAt, error: err instanceof Error ? err.message : String(err) },
        },
      }),
  )
}

export function ensureLate(
  slug: string,
  events: NormalisedEvent[],
  lateEvent: NormalisedEvent,
  previous: unknown,
  opts: { retry?: boolean } = {},
) {
  const cur = state.late[slug]
  if (cur && !(opts.retry && cur.status === 'error')) return
  const startedAt = Date.now()
  set({ ...state, late: { ...state.late, [slug]: { status: 'loading', startedAt } } })
  fetchLateEvidence(slug, events, lateEvent, previous).then(
    (result) => set({ ...state, late: { ...state.late, [slug]: { status: 'done', startedAt, result } } }),
    (err) =>
      set({
        ...state,
        late: {
          ...state.late,
          [slug]: { status: 'error', startedAt, error: err instanceof Error ? err.message : String(err) },
        },
      }),
  )
}

const snapshot = () => state

export function useLiveState() {
  return useSyncExternalStore(subscribe, snapshot)
}
