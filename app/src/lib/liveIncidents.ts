import { useEffect, useMemo, useRef, useState } from 'react'
import type { NormalisedEvent } from './types'

export interface RawLiveIncident {
  number: string
  subject: string | null
  details: string | null
  it_organization: string | null
  zone: string | null
  service: string | null
  configuration_item: string | null
  priority: string | null
  parent_incident: string | null
  state: string | null
  assignment_group: string | null
  team: string | null
  close_code: string | null
  subclose_code: string | null
  close_notes: string | null
  reassignment_count: number | null
  reopen_count: number | null
  classification_keyword: string | null
  sub_classification: string | null
  environment: string | null
  opened_offset_sec: number
  updated_offset_sec: number | null
  resolved_offset_sec: number | null
}

export interface LiveWindow {
  source: string
  window_start_real: string
  window_end_real: string
  window_seconds: number
  redacted_fields: string[]
  incident_count: number
  incidents: RawLiveIncident[]
}

const API_BASE = `${(import.meta.env.BASE_URL || '/').replace(/\/$/, '')}/api`

export async function fetchLiveWindow(): Promise<LiveWindow> {
  const res = await fetch(`${API_BASE}/live-window`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`live window fetch failed: ${res.status} ${body.slice(0, 200)}`)
  }
  return res.json()
}

/** Splunk/ServiceNow "Details" fields carry raw HTML (tables, <b>, entities). */
export function stripHtml(html: string | null | undefined): string {
  if (!html) return ''
  return html
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<\/(td|tr|p|div)>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&#64;/g, '@')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const PRIORITY_SEVERITY: Record<string, 1 | 2 | 3 | 4> = {
  '1 - Major Incident': 1,
  '2 - Critical': 1,
  '3 - High': 2,
  '4 - Medium': 3,
  '5 - Normal': 4,
}

export function priorityLabel(priority: string | null): string {
  if (!priority) return 'P?'
  const n = priority.match(/^(\d)/)
  return n ? `P${n[1]}` : priority
}

function isRuleRaised(inc: RawLiveIncident): boolean {
  const kw = (inc.classification_keyword || '').toLowerCase()
  return (
    kw.includes('hipmon') ||
    inc.priority === '1 - Major Incident' ||
    inc.priority === '2 - Critical'
  )
}

/** Maps a redacted real incident (already "arrived" in the simulated clock) to the
 * same NormalisedEvent shape the analyst prompt and every panel already understand. */
export function toNormalisedEvent(inc: RawLiveIncident, anchorTs: Date): NormalisedEvent {
  const ts = new Date(anchorTs.getTime() + inc.opened_offset_sec * 1000).toISOString()
  const detail = stripHtml(inc.details)
  const description = [
    inc.subject,
    detail && detail !== inc.subject ? `— ${detail.slice(0, 320)}` : '',
    inc.close_notes ? `[close note: ${stripHtml(inc.close_notes).slice(0, 200)}]` : '',
  ]
    .filter(Boolean)
    .join(' ')

  return {
    event_id: inc.number,
    ts,
    source: 'ServiceNow',
    component: inc.configuration_item || inc.team || inc.assignment_group || 'HIP',
    severity: PRIORITY_SEVERITY[inc.priority || ''] ?? 3,
    description,
    correlation_id: inc.parent_incident || null,
    kind: isRuleRaised(inc) ? 'rule_hit' : 'context',
    rule_id: (inc.classification_keyword || '').toLowerCase().includes('hipmon') ? 'HIPMON-REAL' : undefined,
  }
}

/**
 * Drives a simulated "live" clock: playback starts at the moment this hook first
 * mounts and advances `speed`x faster than real time, replaying the real window's
 * relative timing (not the real June dates -- see extract_live_incidents.py).
 * Loops back to the start once the whole window has played out.
 */
export function useLivePlayback(windowSeconds: number, speed: number) {
  const [elapsedSimSec, setElapsedSimSec] = useState(0)
  const startedAtRef = useRef<number>(Date.now())

  useEffect(() => {
    startedAtRef.current = Date.now()
    const id = window.setInterval(() => {
      const realElapsedSec = (Date.now() - startedAtRef.current) / 1000
      setElapsedSimSec((realElapsedSec * speed) % Math.max(windowSeconds, 1))
    }, 500)
    return () => window.clearInterval(id)
  }, [windowSeconds, speed])

  return elapsedSimSec
}

export function useArrivedIncidents(win: LiveWindow | null, speed: number) {
  const elapsedSimSec = useLivePlayback(win?.window_seconds ?? 1, speed)
  const anchorTs = useMemo(() => new Date(), [win])

  const arrived = useMemo(() => {
    if (!win) return []
    return win.incidents.filter((i) => i.opened_offset_sec <= elapsedSimSec)
  }, [win, elapsedSimSec])

  return { arrived, elapsedSimSec, anchorTs }
}
