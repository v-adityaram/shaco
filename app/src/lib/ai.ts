import type { DiagnosisResult, LateEvidenceResult, NormalisedEvent } from './types'

/**
 * Live path: calls the thin local server (see /server, proxied by Vite to :8787).
 * Non-2xx responses carry { error: string }; that text is surfaced verbatim.
 */
// '/api' in dev; '/incident/api' when built with VITE_BASE=/incident/
const API_BASE = `${(import.meta.env.BASE_URL || '/').replace(/\/$/, '')}/api`

async function post<T>(url: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (err) {
    throw new Error(`Could not reach the analysis server (${err instanceof Error ? err.message : String(err)})`)
  }
  const text = await res.text()
  let json: unknown = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    // not JSON
  }
  if (!res.ok) {
    const msg =
      json && typeof json === 'object' && 'error' in json
        ? String((json as { error: unknown }).error)
        : text.slice(0, 300) || res.statusText
    throw new Error(`${res.status}: ${msg}`)
  }
  if (!json) throw new Error('Analysis server returned an empty response')
  return json as T
}

export function fetchDiagnosis(slug: string, events: NormalisedEvent[]): Promise<DiagnosisResult> {
  return post<DiagnosisResult>(`${API_BASE}/diagnose`, { slug, events })
}

export function fetchLateEvidence(
  slug: string,
  events: NormalisedEvent[],
  lateEvent: NormalisedEvent,
  previousDiagnosis: unknown,
): Promise<LateEvidenceResult> {
  return post<LateEvidenceResult>(`${API_BASE}/diagnose/late-evidence`, {
    slug,
    events,
    lateEvent,
    previousDiagnosis,
  })
}
