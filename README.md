# Incident Response AI — POC

Implementation of the plan in [`Incident Response AI — POC Implementation Plan.md`](./Incident%20Response%20AI%20%E2%80%94%20POC%20Implementation%20Plan.md) (v2).

AI-assisted incident diagnosis for the HIP (Hybrid Integration Platform) ops estate: one observed timeline, ranked candidate causes with evidence for and against, human-approved recovery — demonstrated against five incident scenarios grounded in real June–August 2026 incident patterns. The 400+ existing rules (HIPMON, Sonar, Splunk, Kafka-lag, Workato, Apigee) are the sensors and keep firing; the AI never detects, it correlates, explains, ranks and proposes.

## Layout

```
/data          generated per-scenario raw files + normalised-events.json, anchors.json, evidence-pack.json (git-ignored, regenerate)
/naming.py     the HIP estate: projects, half-flows, processing groups, k8s/ELK aliases, owning teams, exchange catalogue
/generator     generate.py (deterministic raw data), scenarios.py (declarative scenario facts), anchors_spec.py (anchor selectors)
/normaliser    normalise.py + cmdb-aliases.json — parses the raw sources into one event list per scenario
/authoring     hand-authored diagnosis + late-evidence per scenario (ONLY s1 and s2 are curated; s3-s5 run AI-live)
/scripts       find_anchors.py, build_alert_feed.py, build_bundles.py (see below)
/prompts       analyst-system.md, late-evidence.md — the analyst prompt contract
/app           React + Tailwind frontend; app/src/data/<slug>/{alert-feed,bundle}.json are committed
/server        thin local server holding the model key for the live-call path
/Auto Alerts   raw ops exports — git-ignored, never committed, never copied into the repo
```

The five scenarios (all 2026-09-18 UTC):

| slug | fault | primary incident |
| --- | --- | --- |
| `s1-large-mapping-heap` | ASN mapping payloads 3x normal exhaust heap in processing group `opsfin-01-neo-odes-large` | INC10790101 |
| `s2-pi7-listener-hang` | `AN_COMMON_PI7IDOCListner` hangs; nothing enters the platform (no pile-up) | INC10790202 |
| `s3-vendor-release` | Workato platform push breaks `ConfigForDocSending` on every IDoc-out recipe; no HIP change record | INC10790303 |
| `s4-stalled-exchange` | file delivered by SFG SUCCESS, ESB half-flow 2 never starts; exchange stuck INPROGRESS 2/4 after patching | INC10790404 |
| `s5-transco-cache` | `hip-fwk-transco-cache` restart; identical `Connection refused …:8080` on 32 half-flows in 4 projects | INC10790505 |

## Running it

```bash
# app/src/data/*/bundle.json is committed, so this is enough to run the demo:
cd app
npm install
npm run dev
```

### Regenerating the data layer

Run in this order (each step reads the previous step's output; everything is standard-library Python and byte-deterministic):

```bash
python generator/generate.py          # 1. raw data -> data/<slug>/{sonar-exchanges.ndjson, kafka-lag.csv, splunk-hosts.ndjson,
                                      #    hipmon-alerts.json, workato-jobs.json, apigee-errors.json, mft-transfers.csv,
                                      #    servicenow-incidents.json, change-records.json, late-evidence.ndjson}
python normaliser/normalise.py        # 2. -> data/<slug>/normalised-events.json (+ late-event-normalised.json)
python scripts/find_anchors.py        # 3. -> data/<slug>/anchors.json (first symptom, contradictions, decisive evidence ids)
python scripts/build_alert_feed.py    # 4. -> app/src/data/<slug>/alert-feed.json  { alertRows, dashboard }
python scripts/build_bundles.py       # 5. -> app/src/data/<slug>/bundle.json (+ data/<slug>/evidence-pack.json)
python scripts/build_bundles.py --pack-only   # only the evidence pack (what the authoring step reads)
```

Notes on the data:

- **Sonar lines are a sampled log** (about one line per background exchange, full traces for focal exchanges); the true volumes are in the per-5-minute `GLBL_MSTR_VOLUME_CHK` records. Half-flow names, `exchange.id`s (24-digit and UUID), business ids and every ticket number are invented — no employee names, no real addresses.
- **`halfflow.missing`** shows the half-flow an exchange is *waiting at* (`2/4`); complete exchanges show `0/4`.
- **`mft-transfers.csv` is local time with no offset** (the FRHIPG* hosts run Europe/Paris, CEST = UTC+2). `normalise.py` converts it back to UTC. It also carries an `exchange_id` column so MFT rows thread with Sonar/HIPMON.
- **Each scenario carries a real, checkable planted contradiction** in the raw files (lower ASN inflow + zero lag elsewhere; green listener health check; still-succeeding `YHIPDELVRY07` IDocs + green RFC gateway; SFG SUCCESS + zero-failed hourly reports; Ready pod + succeeding replays), plus the two standing-noise Splunk host alerts.

### The normalised event contract

`NormalisedEvent = { event_id, ts, source, component, severity 1-4, description, correlation_id, kind: 'rule_hit'|'context', rule_id?, raw_ref }`.
`rule_hit` = something an existing rule/monitor already fired (HIPMON `[AUTO]`, Splunk threshold, Kafka-lag rule, breached Sonar hourly report, Workato job failure, Apigee 5xx rule, ServiceNow incidents). `context` = what an analyst pulls up around them. Absences (S2 zero inbound, S4 missing half-flow 2) are stated by explicit code-computed context events; S4's stall is context-only because no rule covers it.

### The evidence pack and the two run modes

`build_bundles.py` never hands the AI the full event list. `events` in a bundle is a deterministic, code-built **evidence pack** (~130–260 events): every distinct rule hit (identical repeats collapsed with a count and first/last time), all anchor events, computed absence/summary events, all change/MFT/ticket records, and a bounded sample of relevant context. The selection rules are in the `build_bundles.py` docstring; `data/<slug>/normalised-events.json` stays the source of truth.

- `authoring/<slug>.json` **exists** → `meta.mode = 'curated'`: hand-authored diagnosis and late-evidence diff, validated (every cited `event_id` must be in the pack, every hypothesis needs a non-empty `contradicts`, at least two hypotheses).
- **absent** → `meta.mode = 'ai-live'`: `diagnosis: null`, `lateEvidence: { event, diff: null, diagnosisAfter: null }`. Nothing is fabricated; the live model produces it at runtime. Currently only `s1` and `s2` are curated.

`rulesFired` = distinct rule ids among incident-related rule hits in the pack (ServiceNow record ids and the two standing-noise rules excluded); `noiseRulesFired` = 2; `rulesTotal` = 412.

## What is code vs. what is the model

Deterministic code parses the raw formats, normalises timestamps and severities, resolves service aliases (project ↔ half-flow ↔ Kubernetes deployment / ELK alias), threads exchange ids, computes counts and absences, and builds the evidence pack. The model does one thing: takes that pack and returns ranked hypotheses with supporting and contradicting evidence, check ordering, and a recovery proposal that stays behind a human approval gate. See `prompts/analyst-system.md` for the exact contract.
