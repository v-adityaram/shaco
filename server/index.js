import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PROMPTS_DIR = join(__dirname, '..', 'prompts')
const ANALYST_SYSTEM = readFileSync(join(PROMPTS_DIR, 'analyst-system.md'), 'utf-8')
const LATE_EVIDENCE_INSTRUCTIONS = readFileSync(join(PROMPTS_DIR, 'late-evidence.md'), 'utf-8')

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY
const MODEL = process.env.ANTHROPIC_MODEL || 'claude-sonnet-5'

const app = express()
app.use(express.json({ limit: '10mb' }))

function requireApiKey(res) {
  if (!ANTHROPIC_API_KEY) {
    res.status(500).json({
      error:
        'ANTHROPIC_API_KEY is not set. The live toggle needs a real key in the environment; every other scenario path uses the cached bundles and does not need this server.',
    })
    return false
  }
  return true
}

async function callClaude(system, userContent) {
  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 4096,
      system,
      messages: [{ role: 'user', content: userContent }],
    }),
  })
  if (!resp.ok) {
    throw new Error(`Anthropic API error ${resp.status}: ${await resp.text()}`)
  }
  const data = await resp.json()
  const text = data.content?.map((b) => b.text ?? '').join('') ?? ''
  return JSON.parse(text)
}

app.post('/api/diagnose', async (req, res) => {
  if (!requireApiKey(res)) return
  try {
    const { events } = req.body
    const diagnosis = await callClaude(
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
    const diagnosis = await callClaude(
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
  res.json({ ok: true, liveEnabled: Boolean(ANTHROPIC_API_KEY), model: MODEL })
})

const PORT = process.env.PORT || 8787
app.listen(PORT, () => {
  console.log(`Incident AI thin server listening on :${PORT} (live=${Boolean(ANTHROPIC_API_KEY)})`)
})
