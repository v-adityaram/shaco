import type { SourceSystem } from './types'

const ALL: SourceSystem[] = ['SONAR', 'HIPMON', 'Splunk', 'Kafka', 'Workato', 'Apigee', 'MFT', 'ServiceNow', 'Change']

/** Case-insensitive lookup: alert rows carry free-form source strings ('KAFKA', 'Splunk'...). */
export function normaliseSource(s: string): SourceSystem | null {
  const k = s.trim().toLowerCase()
  return ALL.find((x) => x.toLowerCase() === k) ?? null
}
