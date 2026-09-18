export type SourceSystem =
  | 'ELK'
  | 'Kafka'
  | 'Apigee'
  | 'APIM'
  | 'MFT'
  | 'ServiceNow'
  | 'DevOps'

export interface NormalisedEvent {
  event_id: string
  ts: string
  source: SourceSystem
  component: string
  severity: 1 | 2 | 3 | 4
  description: string
  correlation_id: string | null
  raw_ref?: string
}

export interface AlertRow {
  ts: string
  source: string
  ruleId: string
  component: string
  message: string
  severity: 'P1' | 'P2' | 'P3' | 'P4'
  correlationId?: string | null
  isNoise?: boolean
  isFirstSymptom?: boolean
}

export interface EvidenceRef {
  event_id: string
  why: string
}

export interface Hypothesis {
  rank: number
  cause: string
  confidence: 'High' | 'Moderate' | 'Low'
  supports: EvidenceRef[]
  contradicts: EvidenceRef[]
  what_would_change_this: string
}

export interface RuledOutItem {
  candidate: string
  reason: string
}

export interface DiagnosticCheck {
  order: number
  action: string
  command: string
  if_result_a: string
  if_result_b: string
  effort: 'low' | 'medium' | 'high'
}

export interface BlastRadius {
  channels: string[]
  orders_stuck: number
  value_at_risk_inr?: number
  downstream_degraded: string[]
  partner_feed_impacted?: boolean
}

export interface RecoveryProposal {
  proposal: string
  risk: string
  rollback: string
  requires_approval: boolean
}

export interface TimelineItem {
  event_id: string
  ts: string
  source: SourceSystem
  component: string
  description: string
  is_first_symptom?: boolean
}

export interface AiDiagnosis {
  incident_summary: string
  timeline: TimelineItem[]
  hypotheses: Hypothesis[]
  ruled_out: RuledOutItem[]
  checks: DiagnosticCheck[]
  blast_radius: BlastRadius
  recovery: RecoveryProposal
  post_incident_note: string
}

export interface LateEvidenceDiff {
  new_event: TimelineItem
  changed_summary: string
  rank_before: { cause: string; rank: number }[]
  rank_after: { cause: string; rank: number }[]
  what_changed: string[]
}

export interface ScenarioMeta {
  slug: string
  title: string
  incidentNumber: string
  duplicateIncidents: string[]
  faultOneLine: string
}

export interface ScenarioBundle {
  meta: ScenarioMeta
  events: NormalisedEvent[]
  alertRows: AlertRow[]
  diagnosis: AiDiagnosis
  lateEvidence: {
    event: NormalisedEvent
    diff: LateEvidenceDiff
    diagnosisAfter: AiDiagnosis
  }
  rulesFired: number
  rulesTotal: number
}
