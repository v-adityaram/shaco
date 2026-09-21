export type SourceSystem =
  | 'SONAR'
  | 'HIPMON'
  | 'Splunk'
  | 'Kafka'
  | 'Workato'
  | 'Apigee'
  | 'MFT'
  | 'ServiceNow'
  | 'Change'

export interface NormalisedEvent {
  event_id: string
  ts: string
  source: SourceSystem
  component: string
  severity: 1 | 2 | 3 | 4
  description: string
  correlation_id: string | null
  raw_ref?: string
  /** 'rule_hit' = output of an existing detection rule; 'context' = retrieved record (change, ticket, metric...). */
  kind: 'rule_hit' | 'context'
  rule_id?: string
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
  business_flows: string[]
  exchanges_stuck: number
  zones: string[]
  downstream_degraded: string[]
  business_objects_at_risk?: string
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

export interface KpiBlock {
  exchanges: number
  inprogress: number
  complete: number
  warning: number
  failed: number
  replayed: number
  failurePct: number
  durationAvg: string
  durationMax: string
}

export type ExchangeStatus =
  | 'COMPLETE'
  | 'COMPLETE (F)'
  | 'INPROGRESS'
  | 'FAILED'
  | 'WARNING'
  | 'REPLAYED'

export interface ExchangeRow {
  ts: string
  status: ExchangeStatus
  project: string
  exchange: string
  exchangeId: string
  halfflowCount: number
  halfflowMissing: string
  durationMs: number
  source: string
  destination: string
  objectId: string
  objectName: string
  eventCode: string
  businessValue: string
  frameworkVersion: string
  isAnomalous?: boolean
}

export type TraceLevel = 'ERROR' | 'INFO' | 'ENTRYINFO' | 'EXITINFO' | 'WARN'

export interface TraceRow {
  ts: string
  level: TraceLevel
  exchange: string
  exchangeId: string
  halfflow: string
  halfflowId: string
  application: string
  eventCode: string
  eventReason: string
  message: string
  businessValue: string
}

export type Zone = 'AMER' | 'EMEA' | 'APAC'
export type FlowApplication = 'API' | 'ESB' | 'MFT' | 'Workato' | 'ETL'

/** One row of the real "Global Daily Flow Failure Report" -- ranked by failed rate,
 * a subset of the day's flows (the real dashboard is 132 pages deep; this is the top slice). */
export interface CriticalFlowRow {
  exchange: string
  zone: Zone
  total: number
  failed: number
  failedRate: number
}

export interface ZoneFailureRate {
  zone: Zone
  currentPct: number
  oneDayPct: number
  oneWeekPct: number
}

export interface ApplicationFailureRate {
  application: FlowApplication
  pct: number
}

export interface SonarDashboard {
  windowLabel: string
  exchangeKpis: KpiBlock
  halfflowKpis: KpiBlock
  exchangeRows: ExchangeRow[]
  traceFocus: { exchange: string; exchangeId: string; rows: TraceRow[] }
  criticalFlows: CriticalFlowRow[]
  failureRateByZone: ZoneFailureRate[]
  failureRateByApplication: ApplicationFailureRate[]
}

export interface ScenarioMeta {
  slug: string
  title: string
  incidentNumber: string
  duplicateIncidents: string[]
  faultOneLine: string
  /** curated = cached diagnosis shipped in the bundle; ai-live = diagnosis obtained from the live call only. */
  mode: 'curated' | 'ai-live'
}

export interface ScenarioBundle {
  meta: ScenarioMeta
  events: NormalisedEvent[]
  alertRows: AlertRow[]
  dashboard: SonarDashboard
  diagnosis: AiDiagnosis | null
  lateEvidence: {
    event: NormalisedEvent
    diff: LateEvidenceDiff | null
    diagnosisAfter: AiDiagnosis | null
  }
  rulesFired: number
  rulesTotal: number
  noiseRulesFired: number
}

export interface DiagnosisMeta {
  source: 'live' | 'server-cache'
  cachedAt?: string
  model?: string
  latencyMs?: number
  warnings?: string[]
}

/** Response of POST /api/diagnose. */
export type DiagnosisResult = AiDiagnosis & { _meta?: DiagnosisMeta }

/** Response of POST /api/diagnose/late-evidence. */
export type LateEvidenceResult = AiDiagnosis & { diff: LateEvidenceDiff; _meta?: DiagnosisMeta }
