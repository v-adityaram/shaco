import type { AiDiagnosis, NormalisedEvent } from './types'

/**
 * Live path: calls the thin local server (see /server) which holds the
 * Anthropic API key and forwards to the analyst prompt. Used only when the
 * "Run live" toggle is on for a scenario — every other path renders the
 * pre-computed cached bundle so the demo never depends on network/latency.
 */
export async function runLiveDiagnosis(events: NormalisedEvent[]): Promise<AiDiagnosis> {
  const res = await fetch('/api/diagnose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events }),
  })
  if (!res.ok) {
    throw new Error(`Live diagnosis call failed: ${res.status} ${await res.text()}`)
  }
  return res.json()
}

export async function runLiveLateEvidence(
  events: NormalisedEvent[],
  lateEvent: NormalisedEvent,
  previousDiagnosis: AiDiagnosis,
) {
  const res = await fetch('/api/diagnose/late-evidence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events, lateEvent, previousDiagnosis }),
  })
  if (!res.ok) {
    throw new Error(`Live late-evidence call failed: ${res.status} ${await res.text()}`)
  }
  return res.json()
}
