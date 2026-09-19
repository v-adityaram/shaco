import type { ScenarioBundle } from './types'

/** Canonical scenario order. Bundles are dropped in at app/src/data/<slug>/bundle.json. */
export const SCENARIO_SLUGS = [
  's1-large-mapping-heap',
  's2-pi7-listener-hang',
  's3-vendor-release',
  's4-stalled-exchange',
  's5-transco-cache',
] as const

export const SCENARIO_LABELS: Record<string, string> = {
  's1-large-mapping-heap': 'S1 · Large-mapping heap',
  's2-pi7-listener-hang': 'S2 · PI7 listener hang',
  's3-vendor-release': 'S3 · Vendor release',
  's4-stalled-exchange': 'S4 · Stalled exchange',
  's5-transco-cache': 'S5 · Shared cache',
}

const modules = import.meta.glob('../data/*/bundle.json', { eager: true }) as Record<
  string,
  { default: ScenarioBundle }
>

const bundles: Record<string, ScenarioBundle> = {}
for (const path in modules) {
  const slug = path.split('/').at(-2)!
  bundles[slug] = modules[path].default
}

function checkBundle(slug: string, b: ScenarioBundle) {
  const missing: string[] = []
  if (!b.meta) missing.push('meta')
  if (!b.alertRows) missing.push('alertRows')
  if (!b.dashboard) missing.push('dashboard')
  if (!b.diagnosis && b.meta?.mode !== 'ai-live') missing.push('diagnosis')
  if (!b.lateEvidence) missing.push('lateEvidence')
  if (missing.length) {
    console.error(`[cache] bundle "${slug}" is missing: ${missing.join(', ')} — screens will degrade`)
  }
}

for (const slug of SCENARIO_SLUGS) {
  if (!bundles[slug]) {
    console.error(`[cache] no bundle.json for scenario "${slug}" (expected app/src/data/${slug}/bundle.json)`)
  } else {
    checkBundle(slug, bundles[slug])
  }
}

/** Only scenarios that actually have a bundle, in canonical order. */
export const scenarioSlugs: string[] = SCENARIO_SLUGS.filter((s) => bundles[s])

export function getScenarioBundle(slug: string): ScenarioBundle {
  const bundle = bundles[slug]
  if (!bundle) throw new Error(`No cached bundle for scenario "${slug}"`)
  return bundle
}

export function getAllScenarios(): ScenarioBundle[] {
  return scenarioSlugs.map((s) => bundles[s])
}
