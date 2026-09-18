import { useMemo, useRef, useState } from 'react'
import { ThemeToggle } from './components/ThemeToggle'
import { useTheme } from './hooks/useTheme'
import { getAllScenarios, getScenarioBundle, scenarioSlugs } from './lib/cache'
import { AiView } from './screens/AiView'
import { AlertFloor } from './screens/AlertFloor'

type Phase = 'today' | 'freezing' | 'collapsing' | 'ai'

const SCENARIO_LABELS: Record<string, string> = {
  's1-memory-leak': 'S1 · Memory leak',
  's2-poison-message': 'S2 · Poison message',
  's3-config-change': 'S3 · Config change',
  's4-mft-truncation': 'S4 · MFT truncation',
  's5-oracle-saturation': 'S5 · Oracle saturation',
}

export default function App() {
  const [activeSlug, setActiveSlug] = useState(scenarioSlugs[0])
  const [phase, setPhase] = useState<Phase>('today')
  const timers = useRef<number[]>([])
  const { theme, toggleTheme } = useTheme()

  const bundles = useMemo(() => getAllScenarios(), [])
  const bundle = getScenarioBundle(activeSlug)

  const incidentRuleIds = useMemo(
    () => new Set(bundle.alertRows.filter((r) => !r.isNoise).map((r) => r.ruleId)),
    [bundle],
  )

  function clearTimers() {
    timers.current.forEach((t) => window.clearTimeout(t))
    timers.current = []
  }

  function runCorrelation() {
    if (phase === 'freezing' || phase === 'collapsing') {
      // second click: skip straight to the AI screen
      clearTimers()
      setPhase('ai')
      return
    }
    if (phase !== 'today') return
    setPhase('freezing')
    timers.current.push(
      window.setTimeout(() => setPhase('collapsing'), 1000),
      window.setTimeout(() => setPhase('ai'), 2600),
    )
  }

  function switchScenario(slug: string) {
    clearTimers()
    setActiveSlug(slug)
  }

  function backToToday() {
    clearTimers()
    setPhase('today')
  }

  return (
    <div className="min-h-svh bg-slate-100 dark:bg-slate-950">
      <div className="fixed top-3 right-3 z-50">
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </div>
      {phase !== 'ai' ? (
        <div className="h-svh">
          <AlertFloor
            meta={bundle.meta}
            rows={bundle.alertRows}
            rulesFired={bundle.rulesFired}
            rulesTotal={bundle.rulesTotal}
            incidentRuleIds={incidentRuleIds}
            transitionPhase={phase === 'today' ? 'idle' : phase === 'freezing' ? 'freezing' : 'collapsing'}
            onRunCorrelation={runCorrelation}
          />
        </div>
      ) : (
        <div className="animate-card-in">
          <div className="mx-auto flex max-w-6xl justify-start px-4 pt-3">
            <button
              onClick={backToToday}
              className="text-[11px] text-slate-500 underline decoration-dotted hover:text-slate-800 dark:hover:text-slate-300"
            >
              ← back to alert floor
            </button>
          </div>
          <AiView
            key={activeSlug}
            bundle={bundle}
            slugs={bundles.map((b) => b.meta.slug)}
            labels={SCENARIO_LABELS}
            activeSlug={activeSlug}
            onScenarioChange={switchScenario}
          />
        </div>
      )}
    </div>
  )
}
