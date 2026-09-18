import type { ScenarioBundle } from './types'

const modules = import.meta.glob('../data/*/bundle.json', { eager: true }) as Record<
  string,
  { default: ScenarioBundle }
>

const bundles: Record<string, ScenarioBundle> = {}
for (const path in modules) {
  const slug = path.split('/').at(-2)!
  bundles[slug] = modules[path].default
}

export const scenarioSlugs = Object.keys(bundles).sort()

export function getScenarioBundle(slug: string): ScenarioBundle {
  const bundle = bundles[slug]
  if (!bundle) throw new Error(`No cached bundle for scenario "${slug}"`)
  return bundle
}

export function getAllScenarios(): ScenarioBundle[] {
  return scenarioSlugs.map((s) => bundles[s])
}
