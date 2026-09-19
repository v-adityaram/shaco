import { useEffect, useMemo, useRef, useState } from 'react'
import { ThemeToggle } from './components/ThemeToggle'
import { useTheme } from './hooks/useTheme'
import { SCENARIO_LABELS, getAllScenarios, getScenarioBundle, scenarioSlugs } from './lib/cache'
import { ensureDiagnosis } from './lib/liveCache'
import { AiView } from './screens/AiView'
import { AlertFloor } from './screens/AlertFloor'

type Phase = 'today' | 'freezing' | 'collapsing' | 'ai'

export default function App() {
  const [activeSlug, setActiveSlug] = useState(scenarioSlugs[0])
  const [phase, setPhase] = useState<Phase>('today')
  const timers = useRef<number[]>([])
  const { theme, toggleTheme } = useTheme()

  const bundles = useMemo(() => getAllScenarios(), [])
  const bundle = activeSlug ? getScenarioBundle(activeSlug) : undefined

  const incidentRuleIds = useMemo(
    () => new Set((bundle?.alertRows ?? []).filter((r) => !r.isNoise).map((r) => r.ruleId)),
    [bundle],
  )

  // ai-live scenarios have no cached diagnosis: start the call as soon as the scenario is shown,
  // so it is usually finished by the time "Run AI correlation" is clicked. Memoised per slug.
  useEffect(() => {
    if (bundle && bundle.meta.mode === 'ai-live') ensureDiagnosis(bundle.meta.slug, bundle.events)
  }, [bundle])

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
    setPhase((p) => (p === 'ai' ? 'ai' : 'today'))
  }

  function backToToday() {
    clearTimers()
    setPhase('today')
  }

  if (!bundle) {
    return (
      <div className="grid min-h-svh place-items-center bg-slate-100 p-6 text-slate-700 dark:bg-slate-950 dark:text-slate-300">
        <div className="max-w-md text-sm">
          No scenario bundles found. Expected <code>app/src/data/&lt;slug&gt;/bundle.json</code> for:{' '}
          {Object.keys(SCENARIO_LABELS).join(', ')}. See the console for details.
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-svh bg-slate-100 dark:bg-slate-950">
      {phase === 'ai' && (
        <div className="fixed top-3 right-3 z-50">
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      )}
      {phase !== 'ai' ? (
        <div className="h-svh">
          <AlertFloor
            meta={bundle.meta}
            rows={bundle.alertRows ?? []}
            dashboard={bundle.dashboard}
            rulesFired={bundle.rulesFired}
            rulesTotal={bundle.rulesTotal}
            incidentRuleIds={incidentRuleIds}
            transitionPhase={phase === 'today' ? 'idle' : phase === 'freezing' ? 'freezing' : 'collapsing'}
            onRunCorrelation={runCorrelation}
            controls={
              <>
                <select
                  value={activeSlug}
                  disabled={phase !== 'today'}
                  onChange={(e) => switchScenario(e.target.value)}
                  aria-label="Scenario"
                  className="h-7 rounded border border-slate-500 bg-slate-700 px-1.5 text-[11px] text-slate-100 disabled:opacity-50"
                >
                  {bundles.map((b) => (
                    <option key={b.meta.slug} value={b.meta.slug}>
                      {SCENARIO_LABELS[b.meta.slug] ?? b.meta.slug}
                    </option>
                  ))}
                </select>
                <span className="[&>button]:h-7 [&>button]:w-7 [&>button]:border-slate-500 [&>button]:bg-slate-700 [&>button]:text-slate-200">
                  <ThemeToggle theme={theme} onToggle={toggleTheme} />
                </span>
              </>
            }
          />
        </div>
      ) : (
        <div className="animate-card-in">
          <div className="mx-auto flex max-w-6xl justify-start px-4 pt-3">
            <button
              onClick={backToToday}
              className="text-[11px] text-slate-500 underline decoration-dotted hover:text-slate-800 dark:hover:text-slate-300"
            >
              ← back to Sonar dashboard
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
