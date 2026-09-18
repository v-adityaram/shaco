# Incident Response AI — POC

Implementation of the plan in [`Incident Response AI — POC Implementation Plan.md`](./Incident%20Response%20AI%20%E2%80%94%20POC%20Implementation%20Plan.md).

AI-assisted incident diagnosis for a synthetic retail estate ("Meridian Retail"): one observed timeline, ranked candidate causes with evidence for and against, human-approved recovery — demonstrated against five incident scenarios.

## Layout

```
/data          generated per-scenario source files + normalised-events.json (git-ignored, regenerate with generator/generate.py)
/generator     generate.py + scenarios.py — the five scenario specs and the synthetic-data generator
/normaliser    normalise.py — parses the seven raw source formats into one normalised event list per scenario
/authoring     hand-authored diagnosis + late-evidence content per scenario (the prompt-iteration output — see below)
/scripts       build_alert_feed.py (Screen 1 rows from real data) + build_bundles.py (assembles app/src/data/<slug>/bundle.json, validates every citation resolves)
/prompts       analyst-system.md, late-evidence.md — the analyst prompt contract
/app           React + Tailwind frontend (Screen 1 "Today" alert floor, Screen 2 "With AI" diagnosis view); app/src/data/*/bundle.json is committed so the app runs without regenerating anything
/server        thin local Express server holding the Anthropic API key, for the one live-call scenario toggle
```

## Running it

```bash
# app/src/data/*/bundle.json is already committed, so this is enough to run the demo:
cd app
npm install
npm run dev

# Optional — enable the live-call toggle on one scenario
cd server
npm install
ANTHROPIC_API_KEY=... npm start
```

### Regenerating the data layer

```bash
python generator/generate.py          # 1. synthetic raw data, standard library only, deterministic
python normaliser/normalise.py        # 2. -> data/<slug>/normalised-events.json
python scripts/build_alert_feed.py    # 3. -> app/src/data/<slug>/alert-feed.json (Screen 1 rows)
python scripts/build_bundles.py       # 4. -> app/src/data/<slug>/bundle.json (fails if a citation in authoring/ doesn't resolve)
```

`authoring/<slug>.json` is where the actual diagnosis content lives — the hypotheses, evidence, checks, recovery proposal, and late-evidence diff, each citing real `event_id`s from that scenario's `normalised-events.json`. This is the one step in the pipeline the plan calls out as not mechanical (see its "Working with Claude Code" section): everything upstream (generator, normaliser) and downstream (`build_bundles.py`'s citation validator) is deterministic code, but the diagnosis reasoning itself was authored by hand per scenario, standing in for the live model call the `/server` + `prompts/` path makes when the live toggle is on.

## What is code vs. what is the model

Deterministic code parses the six/seven raw formats, normalises timestamps and severities, resolves service aliases, and threads correlation IDs. The model does one thing: takes the normalised event list plus change records and ticket text, and returns ranked hypotheses with supporting and contradicting evidence, check ordering, and a recovery proposal. See `prompts/analyst-system.md` for the exact contract.
