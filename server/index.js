import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PROMPTS_DIR = join(__dirname, '..', 'prompts')
const ANALYST_SYSTEM = readFileSync(join(PROMPTS_DIR, 'analyst-system.md'), 'utf-8')
const LATE_EVIDENCE_INSTRUCTIONS = readFileSync(join(PROMPTS_DIR, 'late-evidence.md'), 'utf-8')

// Azure AI Foundry project (Responses API, OpenAI-compatible surface).
// FOUNDRY_ENDPOINT is the "…/openai/v1" base shown in the Foundry portal's
// "Call this model" panel; the model is a deployment name on that project,
// not a generic model id.
const FOUNDRY_ENDPOINT = process.env.FOUNDRY_ENDPOINT
const FOUNDRY_API_KEY = process.env.FOUNDRY_API_KEY
const MODEL = process.env.FOUNDRY_MODEL || 'gpt-5'
// unset by default -- let gpt-5 reason at its own default depth. This is a
// one-shot analyst report shown live exactly once in the demo, not a
// latency-sensitive path, so there's no reason to trade accuracy for speed
// here the way the fast-path classification calls elsewhere do.
const REASONING_EFFORT = process.env.FOUNDRY_REASONING_EFFORT || undefined

const app = express()
app.use(express.json({ limit: '10mb' }))

function requireApiKey(res) {
  if (!FOUNDRY_ENDPOINT || !FOUNDRY_API_KEY) {
    res.status(500).json({
      error:
        'FOUNDRY_ENDPOINT and FOUNDRY_API_KEY are not both set. The live toggle needs both in the environment; every other scenario path uses the cached bundles and does not need this server.',
    })
    return false
  }
  return true
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

async function callFoundry(instructions, input) {
  const body = {
    model: MODEL,
    instructions,
    input,
    text: { verbosity: 'medium' },
  }
  if (REASONING_EFFORT) body.reasoning = { effort: REASONING_EFFORT }

  const resp = await fetch(`${FOUNDRY_ENDPOINT.replace(/\/$/, '')}/responses`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'api-key': FOUNDRY_API_KEY,
      authorization: `Bearer ${FOUNDRY_API_KEY}`,
    },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new Error(`Azure AI Foundry error ${resp.status}: ${await resp.text()}`)
  }
  const data = await resp.json()
  const text = extractOutputText(data)
  const cleaned = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '')
  return JSON.parse(cleaned)
}

app.post('/api/diagnose', async (req, res) => {
  if (!requireApiKey(res)) return
  try {
    const { events } = req.body
    const diagnosis = await callFoundry(
      ANALYST_SYSTEM,
      `normalised_events:\n${JSON.stringify(events, null, 2)}`,
    )
    res.json(diagnosis)
  } catch (err) {
    res.status(502).json({ error: String(err) })
  }
})

app.post('/api/diagnose/late-evidence', async (req, res) => {
  if (!requireApiKey(res)) return
  try {
    const { events, lateEvent, previousDiagnosis } = req.body
    const diagnosis = await callFoundry(
      ANALYST_SYSTEM + '\n\n---\n\n' + LATE_EVIDENCE_INSTRUCTIONS,
      `normalised_events:\n${JSON.stringify(events, null, 2)}\n\nlate_event:\n${JSON.stringify(
        lateEvent,
        null,
        2,
      )}\n\nprevious_diagnosis:\n${JSON.stringify(previousDiagnosis, null, 2)}`,
    )
    res.json(diagnosis)
  } catch (err) {
    res.status(502).json({ error: String(err) })
  }
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
