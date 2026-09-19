import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PROMPTS_DIR = join(__dirname, '..', 'prompts')
const CACHE_DIR = join(__dirname, 'cache')
const ANALYST_SYSTEM = readFileSync(join(PROMPTS_DIR, 'analyst-system.md'), 'utf-8')
const LATE_EVIDENCE_INSTRUCTIONS = readFileSync(join(PROMPTS_DIR, 'late-evidence.md'), 'utf-8')

// Azure AI Foundry project (Responses API, OpenAI-compatible surface).
// FOUNDRY_ENDPOINT is the "…/openai/v1" base shown in the Foundry portal's
// "Call this model" panel; the model is a deployment name on that project,
// not a generic model id.
const FOUNDRY_ENDPOINT = process.env.FOUNDRY_ENDPOINT
const FOUNDRY_API_KEY = process.env.FOUNDRY_API_KEY
const MODEL = process.env.FOUNDRY_MODEL || 'gpt-5'
// Unset by default so gpt-5 reasons at its own depth. Set to low/medium in
// server/.env if live latency in the room matters more than depth.
const REASONING_EFFORT = process.env.FOUNDRY_REASONING_EFFORT || undefined
const REQUEST_TIMEOUT_MS = Number(process.env.FOUNDRY_TIMEOUT_MS || 240000)

const app = express()
app.use(express.json({ limit: '10mb' }))

function requireApiKey() {
  if (!FOUNDRY_ENDPOINT || !FOUNDRY_API_KEY) {
    throw new Error(
      'FOUNDRY_ENDPOINT and FOUNDRY_API_KEY are not both set in server/.env. Live diagnosis needs both.',
    )
  }
}

function extractOutputText(data) {
  if (typeof data.output_text === 'string' && data.output_text) return data.output_text
  const chunks = []
  for (const item of data.output || []) {
    for (const c of item.content || []) {
      if (c.type === 'output_text' && c.text) chunks.push(c.text)
    }
  }
  return chunks.join('')
}

function parseJson(text) {
  const cleaned = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '')
  return JSON.parse(cleaned)
}

async function callFoundry(instructions, input) {
  requireApiKey()
  const body = { model: MODEL, instructions, input, text: { verbosity: 'medium' } }
  if (REASONING_EFFORT) body.reasoning = { effort: REASONING_EFFORT }

  const resp = await fetch(`${FOUNDRY_ENDPOINT.replace(/\/$/, '')}/responses`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'api-key': FOUNDRY_API_KEY,
      authorization: `Bearer ${FOUNDRY_API_KEY}`,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  if (!resp.ok) {
    throw new Error(`Azure AI Foundry error ${resp.status}: ${await resp.text()}`)
  }
  const data = await resp.json()
  if (data.status === 'incomplete') {
    throw new Error(`model response incomplete (${data.incomplete_details?.reason || 'unknown'})`)
  }
  return parseJson(extractOutputText(data))
}

// ---------------------------------------------------------------------------
// Inputs. The model receives rule output and the records pulled around it,
// clearly separated. It is never asked to detect anything.
// ---------------------------------------------------------------------------

function buildInput(events) {
  const ruleHits = events.filter((e) => e.kind === 'rule_hit')
  const context = events.filter((e) => e.kind !== 'rule_hit')
  return (
    `rule_hits (already fired by existing rules/monitors -- ${ruleHits.length} events):\n` +
    `${JSON.stringify(ruleHits)}\n\n` +
    `context (records retrieved around the rule hits -- ${context.length} events):\n` +
    `${JSON.stringify(context)}`
  )
}

// ---------------------------------------------------------------------------
// Validation. Facts are assembled by code: the timeline is rebuilt from the
// evidence pack using only the event_ids the model chose, so a model can
// never invent or reword a timestamp, source or component.
// ---------------------------------------------------------------------------

function validate(diag, ids) {
  const errors = []
  if (!diag || typeof diag !== 'object') return ['output is not a JSON object']
  for (const k of ['incident_summary', 'timeline', 'hypotheses', 'ruled_out', 'checks', 'blast_radius', 'recovery', 'post_incident_note']) {
    if (diag[k] === undefined) errors.push(`missing key: ${k}`)
  }
  if (errors.length) return errors
  if (!Array.isArray(diag.hypotheses) || diag.hypotheses.length < 2 || diag.hypotheses.length > 4) {
    errors.push('hypotheses must contain 2 to 4 items')
  }
  for (const h of diag.hypotheses || []) {
    for (const side of ['supports', 'contradicts']) {
      if (!Array.isArray(h[side]) || h[side].length === 0) {
        errors.push(`hypothesis rank ${h.rank}: ${side} must be a non-empty array`)
        continue
      }
      for (const ev of h[side]) {
        if (!ids.has(ev.event_id)) errors.push(`hypothesis rank ${h.rank}: ${side} cites unknown event_id ${ev.event_id}`)
      }
    }
  }
  for (const t of diag.timeline || []) {
    if (!ids.has(t.event_id)) errors.push(`timeline cites unknown event_id ${t.event_id}`)
  }
  if (diag.recovery && diag.recovery.requires_approval !== true) errors.push('recovery.requires_approval must be true')
  return errors
}

function sanitise(diag, byId) {
  const warnings = []
  for (const h of diag.hypotheses) {
    for (const side of ['supports', 'contradicts']) {
      const before = h[side].length
      h[side] = h[side].filter((ev) => byId.has(ev.event_id))
      if (h[side].length !== before) warnings.push(`dropped ${before - h[side].length} uncitable ${side} item(s) on rank ${h.rank}`)
    }
    const both = h.supports.filter((a) => h.contradicts.some((b) => b.event_id === a.event_id)).map((a) => a.event_id)
    if (both.length) warnings.push(`rank ${h.rank} cites ${both.join(', ')} on both sides`)
  }
  diag.timeline = diag.timeline
    .filter((t) => byId.has(t.event_id))
    .map((t) => {
      const e = byId.get(t.event_id)
      return {
        event_id: e.event_id,
        ts: e.ts,
        source: e.source,
        component: e.component,
        description: e.description,
        is_first_symptom: Boolean(t.is_first_symptom),
      }
    })
    .sort((a, b) => a.ts.localeCompare(b.ts))
  // exactly one first symptom: keep the earliest flagged event
  const flagged = diag.timeline.filter((t) => t.is_first_symptom)
  if (flagged.length > 1) {
    for (const t of flagged.slice(1)) t.is_first_symptom = false
    warnings.push(`model marked ${flagged.length} first symptoms; kept the earliest`)
  }
  // grounding: blast_radius.exchanges_stuck must appear in some event, otherwise flag it
  const n = diag.blast_radius && diag.blast_radius.exchanges_stuck
  if (typeof n === 'number' && n > 0) {
    const forms = [String(n), n.toLocaleString('en-US')]
    const found = [...byId.values()].some((e) => forms.some((f) => e.description.includes(f)))
    if (!found) warnings.push(`exchanges_stuck=${n} does not appear in any evidence event`)
  }
  diag.recovery.requires_approval = true
  return warnings
}

async function analyse(instructions, input, events, label) {
  const byId = new Map(events.map((e) => [e.event_id, e]))
  const ids = new Set(byId.keys())
  let diag
  try {
    diag = await callFoundry(instructions, input)
  } catch (err) {
    if (!(err instanceof SyntaxError)) throw err
    console.warn(`[${label}] model returned invalid JSON (${err.message}); retrying once`)
    diag = await callFoundry(
      instructions,
      `${input}\n\nYour previous answer was not valid JSON (${err.message}). Return the complete answer again as strictly valid JSON only.`,
    )
  }
  let errors = validate(diag, ids)
  if (errors.length) {
    console.warn(`[${label}] first attempt failed validation: ${errors.slice(0, 5).join('; ')}`)
    diag = await callFoundry(
      instructions,
      `${input}\n\nYour previous answer failed validation with these errors -- fix them and return the complete JSON again:\n- ${errors.join('\n- ')}`,
    )
    errors = validate(diag, ids)
  }
  const fatal = errors.filter((e) => !e.includes('cites unknown event_id') && !e.includes('contradicts must be'))
  if (fatal.length) throw new Error(`model output failed validation: ${fatal.join('; ')}`)
  const warnings = sanitise(diag, byId)
  for (const h of diag.hypotheses) {
    if (h.contradicts.length === 0) warnings.push(`rank ${h.rank} has no contradicting evidence (model could not cite any)`)
  }
  return { diag, warnings }
}

// ---------------------------------------------------------------------------
// Disk cache of the last successful live run: a fallback, never the primary.
// ---------------------------------------------------------------------------

function cachePath(slug, kind) {
  return join(CACHE_DIR, `${String(slug).replace(/[^a-z0-9-]/gi, '')}.${kind}.json`)
}

function saveCache(slug, kind, payload) {
  mkdirSync(CACHE_DIR, { recursive: true })
  writeFileSync(cachePath(slug, kind), JSON.stringify({ cachedAt: new Date().toISOString(), payload }, null, 2))
}

function loadCache(slug, kind) {
  const p = cachePath(slug, kind)
  if (!existsSync(p)) return null
  try {
    return JSON.parse(readFileSync(p, 'utf-8'))
  } catch {
    return null
  }
}

async function respond(res, slug, kind, run) {
  const started = Date.now()
  try {
    const { payload, warnings } = await run()
    payload._meta = { source: 'live', model: MODEL, latencyMs: Date.now() - started, warnings }
    saveCache(slug, kind, payload)
    res.json(payload)
  } catch (err) {
    const cached = loadCache(slug, kind)
    if (cached) {
      console.warn(`[${slug}/${kind}] live call failed, replaying server cache: ${err}`)
      res.json({
        ...cached.payload,
        _meta: { source: 'server-cache', cachedAt: cached.cachedAt, warnings: [`live call failed: ${String(err)}`] },
      })
      return
    }
    res.status(502).json({ error: String(err) })
  }
}

app.post('/api/diagnose', (req, res) => {
  const { slug, events } = req.body || {}
  if (!slug || !Array.isArray(events)) {
    res.status(400).json({ error: 'body must be { slug, events[] }' })
    return
  }
  respond(res, slug, 'diagnosis', async () => {
    const { diag, warnings } = await analyse(ANALYST_SYSTEM, buildInput(events), events, `${slug}/diagnose`)
    return { payload: diag, warnings }
  })
})

app.post('/api/diagnose/late-evidence', (req, res) => {
  const { slug, events, lateEvent, previousDiagnosis } = req.body || {}
  if (!slug || !Array.isArray(events) || !lateEvent || !previousDiagnosis) {
    res.status(400).json({ error: 'body must be { slug, events[], lateEvent, previousDiagnosis }' })
    return
  }
  respond(res, slug, 'late', async () => {
    const all = [...events, lateEvent]
    const input =
      `${buildInput(all)}\n\nlate_event (arrived after your original diagnosis; event_id ${lateEvent.event_id}):\n` +
      `${JSON.stringify(lateEvent)}\n\nprevious_diagnosis:\n${JSON.stringify(previousDiagnosis)}`
    const { diag, warnings } = await analyse(
      `${ANALYST_SYSTEM}\n\n---\n\n${LATE_EVIDENCE_INSTRUCTIONS}`,
      input,
      all,
      `${slug}/late`,
    )
    const modelDiff = diag.diff || {}
    // Ranks and the new event are facts: derived by code, not restated by the model.
    diag.diff = {
      new_event: {
        event_id: lateEvent.event_id,
        ts: lateEvent.ts,
        source: lateEvent.source,
        component: lateEvent.component,
        description: lateEvent.description,
        is_first_symptom: false,
      },
      changed_summary: modelDiff.changed_summary || '',
      rank_before: previousDiagnosis.hypotheses.map((h) => ({ cause: h.cause, rank: h.rank })),
      rank_after: diag.hypotheses.map((h) => ({ cause: h.cause, rank: h.rank })),
      what_changed: Array.isArray(modelDiff.what_changed) ? modelDiff.what_changed : [],
    }
    return { payload: diag, warnings }
  })
})

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, liveEnabled: Boolean(FOUNDRY_ENDPOINT && FOUNDRY_API_KEY), model: MODEL })
})

const PORT = process.env.PORT || 8787
app.listen(PORT, () => {
  console.log(
    `Incident AI thin server listening on :${PORT} (live=${Boolean(FOUNDRY_ENDPOINT && FOUNDRY_API_KEY)}, model=${MODEL})`,
  )
})
