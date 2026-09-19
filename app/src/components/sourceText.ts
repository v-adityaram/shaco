import { normaliseSource } from '../lib/sources'
import type { SourceSystem } from '../lib/types'

export const TEXT_ONLY: Record<SourceSystem, string> = {
  SONAR: 'text-teal-700 dark:text-teal-300',
  HIPMON: 'text-rose-700 dark:text-rose-300',
  Splunk: 'text-lime-700 dark:text-lime-300',
  Kafka: 'text-violet-700 dark:text-violet-300',
  Workato: 'text-sky-700 dark:text-sky-300',
  Apigee: 'text-orange-700 dark:text-orange-300',
  MFT: 'text-amber-700 dark:text-amber-300',
  ServiceNow: 'text-emerald-700 dark:text-emerald-300',
  Change: 'text-fuchsia-700 dark:text-fuchsia-300',
}

export function sourceTextClass(s: string) {
  const k = normaliseSource(s)
  return k ? TEXT_ONLY[k] : 'text-slate-500 dark:text-slate-400'
}
