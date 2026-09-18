# Incident Response AI — POC Implementation Plan

2026-09-18 · @Someone

## 1. Demo concept

**One line:** AI-assisted incident diagnosis — one timeline, ranked causes with evidence for and against, human-approved recovery.

**What we are actually demonstrating.** Not detection. Detection already works — the client has 400+ ELK rules and they fire correctly. What we are demonstrating is the compression of *diagnosis*: the 60–120 minutes between "alerts fired" and "we agree what broke."

**The narrative arc.** Three beats, one screen, no slides until the end:

1. **Today.** A dense alert floor — 147 alerts in 6 minutes from five systems, four duplicate ServiceNow incidents, an L1 with no runbook match, and a bridge-call timer running at 1h 14m with cause still "under investigation." Every rule worked. Nobody knows what happened.
2. **Click "Run AI correlation."** The alerts do not vanish — they *collapse* into one incident, each alert becoming a cited evidence item. The visual argument: rules are the input layer, not the casualty.
3. **With AI.** One observed timeline, two or three ranked candidate causes with evidence for *and against* each, ordered diagnostic checks, blast radius, and a recovery action locked behind an approval gate.

**The closer.** A "late MFT log arrives" button injects a delayed file, the timeline updates, and the cause ranking flips with a diff showing what changed. Thirty seconds, and it demonstrates the one thing a rule engine structurally cannot do.

**Positioning against the 400-rules objection.** Stated on screen and in the talk track:

> The 400 rules are the sensors. This is the analyst.

A persistent badge on the AI screen reads *"8 ELK rules fired — consumed as evidence, none suppressed."* Nothing is replaced. More rules make the case stronger, not weaker: more signal, same number of humans reading it.

**Two non-negotiables, visible in the UI.** Observed facts and inferred causes live in separate, differently-styled panels and are labelled as such. And no recovery action executes without an explicit human approval that is logged.

## 2. The fictional estate — Meridian Retail

A synthetic order-to-fulfilment estate. Big enough that "signals are spread across teams" is visibly true, and that a cross-system timeline is genuinely non-obvious rather than a two-hop toy.

### Topology

| Layer | Components |
| --- | --- |
| Channels | Web checkout, mobile app, store POS, partner B2B feed |
| Edge | Apigee (external APIs), Azure APIM (internal service-to-service) |
| Core services | `order-intake`, `order-orchestrator`, `inventory-reservation`, `pricing-svc`, `payment-adapter`, `fulfilment-dispatch` |
| Async | Kafka — topics `order.created`, `order.enriched`, `inventory.reserve.req`, `inventory.reserve.resp`, `fulfilment.dispatch`, plus `*.DLQ` |
| Data | Oracle OMS, Redis session cache, inventory Postgres |
| File transfer | MFT → WMS (hourly stock file), MFT → 3PL (dispatch manifest) |
| Ops tooling | ELK (412 detection rules), ServiceNow, Azure DevOps change records |

### Ownership split — why nobody sees the whole picture

Five notional teams, each with visibility into only its own hop. This is the structural reason the bridge call exists, and it should be visible in the UI as channel labels down the side of Screen 1.

- **Channel Engineering** — web, mobile, POS, Apigee
- **Order Platform** — `order-intake`, `order-orchestrator`, Kafka producer side
- **Inventory & Fulfilment** — `inventory-reservation`, `fulfilment-dispatch`, Postgres
- **Integration** — Azure APIM, MFT, partner B2B feed
- **Infra & DBA** — Oracle OMS, Redis, Kubernetes platform

### Conventions the generator must hold to

These are what the correlation step keys on, so they have to be right or the timeline silently breaks. This is also, not coincidentally, the readiness assessment a real deployment needs.

- **Correlation ID** — `mrd-<yyyymmdd>-<8 hex>`, propagated as `X-Correlation-Id` through gateway, service logs, Kafka headers and MFT manifest rows.
- **Timestamps** — all ISO-8601 with explicit offset, all UTC in the files, rendered in IST in the UI. One source (MFT) deliberately emits local time with no offset, as a realistic wrinkle the normaliser has to handle.
- **Service naming** — the CMDB name (`inventory-reservation`) differs from the Kubernetes deployment name (`inv-resv-svc`) and the ELK index alias (`app-invresv-*`). The normaliser holds the alias map. Worth calling out in the demo: this mismatch is the single most common reason correlation fails in real estates.
- **Severity** — ELK P1–P4, ServiceNow 1–5, Apigee HTTP status. Normalised to a common 1–4.

## 3. Incident catalogue — five scenarios

Five scenarios, not one. This is what proves the system is reasoning rather than returning a hardcoded answer, and someone in the room *will* ask. Scenarios 1 and 2 are the pair that does the heavy lifting: near-identical symptoms, different causes.

Each scenario carries a **planted contradiction** — a fact that argues against the correct cause. This is what populates the "evidence against" column and makes the output look like analysis rather than assertion.

---

### S1 — Memory leak in `inventory-reservation`

**Fault.** A slow heap leak in the reservation cache. Builds over \~90 minutes, GC thrash, then OOMKill and pod restart, repeating.

**Signal sequence**

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 08:40 | ELK | `ELK-R-0188` heap utilisation > 70% — P4, nobody looks |
| 09:25 | ELK | GC pause p99 climbing, 40ms → 900ms |
| 09:52 | ELK | `ELK-R-0217` OOMKilled, pod `inv-resv-svc-7d4f` restart 1 |
| 09:53 | Kafka | `inventory-reservation-cg` lag on `inventory.reserve.req` climbs past 12,000 |
| 09:58 | ELK | Restart 2, then 3 — crash loop |
| 10:02 | Azure APIM | 504 gateway timeouts on `/internal/inventory/reserve` |
| 10:04 | Apigee | 502 on `/v2/orders` — customer-visible |
| 10:06 | ServiceNow | INC0098451 auto-raised P1 |

**Planted contradiction.** The service handled 40% higher order volume last Tuesday without incident. Argues against "load-driven" and points at a leak that is time-based rather than volume-based.

**Expected AI output.** Ranked first: memory leak, supported by the linear pre-incident heap trend and the absence of any deploy. Ranked second: upstream retry storm inflating batch sizes, contradicted by flat producer rate on `order.enriched`.

---

### S2 — Poison message on `order.enriched`

**Fault.** One malformed partner B2B payload — a negative line quantity that fails deserialisation. Consumer crash-loops on the same offset.

**Why this scenario matters most.** From the Kafka and gateway side the symptoms are nearly identical to S1: lag climbs, pods restart, 504s, 502s. The distinguishing evidence is narrow and buried — heap is *flat*, the restart interval is suspiciously regular, and the consumer offset never advances. A human on a bridge call misreads this as S1 routinely. Demo the two back to back.

**Signal sequence**

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 11:14 | Partner feed | B2B batch `PB-4471` accepted, 1 of 380 lines malformed |
| 11:16 | ELK | Deserialisation exception, `order-orchestrator`, stack trace |
| 11:16 | ELK | Pod restart — then again at 11:19, 11:22, 11:25, exactly every 3 min |
| 11:20 | Kafka | Consumer offset on `order.enriched` static at 4,481,209 |
| 11:21 | Kafka | Lag climbing, DLQ depth still zero — no DLQ configured on this topic |
| 11:30 | Apigee | 502 on `/v2/orders` |
| 11:33 | ServiceNow | INC0098462 P1, plus INC0098463 and INC0098464 raised separately by the Kafka and gateway rules |

**Planted contradiction.** Heap and CPU are entirely normal, which argues against the resource-exhaustion reading that the restart pattern superficially suggests.

**Expected AI output.** Ranked first: poison message, supported by the static consumer offset, the metronomic restart interval and the deserialisation trace. Ranked second: memory pressure, explicitly ruled out on flat heap. The check ordered first is a single Kafka offset query — cheap, and decisive.

---

### S3 — Config change breaks internal auth

**Fault.** An Azure APIM policy deployed at 09:12 tightens JWT audience validation. Only `pricing-svc` sends the old audience claim. Orders reach pricing and stop.

**Signal sequence**

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 09:12 | Azure DevOps | Change CHG0044219 — APIM policy revision 47, deployed by release pipeline, no approval record |
| 09:14 | Azure APIM | 401s on `/internal/pricing/quote`, climbing |
| 09:15 | ELK | `order-orchestrator` timeout waiting on pricing, retry exhaustion |
| 09:18 | Kafka | `order.enriched` producer rate collapses to near zero |
| 09:21 | ELK | Order completion rate down 80% |
| 09:24 | Apigee | 504 on `/v2/orders/{id}/confirm` |
| 09:27 | ServiceNow | INC0098470 P1 |

**Planted contradiction.** Web and mobile checkout continue to work for cached-price items, so the failure looks partial and intermittent — which argues against a clean config break and sends humans hunting for a flaky dependency.

**Why this scenario earns its place.** No ELK rule points at the change record. The smoking gun lives in unstructured text in a different system. This is the clearest illustration of something rules structurally cannot reach.

---

### S4 — Silent MFT truncation

**Fault.** The hourly WMS stock file transfers "successfully" but is truncated at 60% — the source export job was killed mid-write. Inventory positions go stale. No error anywhere for three hours.

**Signal sequence**

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 06:00 | MFT | `stock_position_0600.csv` transferred, status SUCCESS, 4.1 MB (usual 6.8 MB) |
| 06:00 | MFT | Row count in trailer says 128,400; actual rows 77,032 — trailer never validated |
| 06:05–09:00 | — | Silence. Nothing fires. |
| 09:12 | ELK | First oversell — reservation confirmed against stock that does not exist |
| 09:40 | ELK | Oversell rate climbing, 14 orders |
| 10:15 | ServiceNow | INC0098480 raised manually by warehouse ops, not by a rule |

**Planted contradiction.** The MFT job reported SUCCESS and the ELK file-transfer rule passed, which argues strongly against the file being the problem. Everything says the transfer was fine.

**Why this scenario earns its place.** It tests reasoning *backwards* — from a late symptom to a silent, hours-earlier event that produced no alert at all. It also demonstrates the system reasoning about the absence of expected signal, which is the hardest thing to encode as a rule.

---

### S5 — Downstream saturation from an unrelated job

**Fault.** A month-end reporting job opens 180 connections against Oracle OMS. The connection pool is exhausted. Every service that touches OMS degrades simultaneously.

**Signal sequence**

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 22:00 | Azure DevOps | Scheduled job `fin-monthend-extract` starts — routine, runs every month |
| 22:08 | ELK | Oracle OMS connection pool at 100%, wait queue growing |
| 22:09 | ELK | Slow-query alerts across `order-intake`, `payment-adapter`, `fulfilment-dispatch` — 30+ distinct rules firing |
| 22:11 | Kafka | Lag on four topics simultaneously |
| 22:12 | Apigee + APIM | 5xx across nine endpoints |
| 22:14 | ServiceNow | Six P1/P2 incidents raised by six different rules |

**Planted contradiction.** This job has run on the same schedule for 14 months without incident, which argues hard against it — the real difference is that a recent index change made it slower and hold connections longer.

**Why this scenario earns its place.** It is the hardest noise-versus-cause separation. Thirty rules fire, all correctly, all describing symptoms. The cause is a system nobody has alerted on, running a job nobody considers risky. It is also the best demonstration that alert *volume* and diagnostic *clarity* are unrelated quantities.

## 4. Screen 1 — "Today"

The job of this screen is to make the room feel the problem in ten seconds without a word of explanation. It must look genuinely overwhelming, not cartoonishly so.

### Layout

**Header.** ServiceNow-style incident bar: `INC0098451 · P1 · Order flow degraded · Assigned: L1 Command Centre · State: In Progress`. Beside it, three more incident chips for the duplicates raised by other rules — with a small note that they describe the same event.

**Centre — the alert feed.** 147 alerts spanning 6 minutes, dense rows, newest first, continuously scrolling. Monospace, tight line height, severity colour on the left edge. Realistic rule names:

```
10:06:14  ELK     ELK-R-0217   inv-resv-svc   OOMKilled, restart 3     P1
10:06:11  APIGEE  APG-5XX-012  /v2/orders     502 rate 34% (2m)        P1
10:05:58  KAFKA   KFK-LAG-004  inventory-reservation-cg  lag 84,210    P2
10:05:41  APIM    AZ-GW-0091   /internal/inventory/reserve  504 x412   P2
10:05:33  ELK     ELK-R-0188   inv-resv-svc   heap 94%                 P3
```

**Left rail — team channels.** Five channels with unread badges: `#ch-order-platform (23)`, `#ch-inventory (41)`, `#ch-integration (8)`, `#ch-channel-eng (17)`, `#ch-infra-dba (12)`. Nobody is wrong; everybody is looking at their own hop.

**Right rail — the L1 panel.** What L1 can actually do, and where it stops:

- Runbook search: `OOMKilled inventory` → 3 candidate runbooks, none matching the cross-system symptom set
- Action taken: restart pod (twice) — no effect
- Action taken: escalate to L2
- State: awaiting bridge

**Footer — the bridge bar.** The most important element on the screen. A live timer counting up from `01:14:22`, and beside it: `6 engineers on bridge · Agreed cause: none · Customer impact: ongoing`. Leave this timer running through the entire demo, including the AI screens. It does more persuasive work than any slide.

### Details that make it feel real

These are worth the extra hour — they are what separate a demo from a mock-up.

- **Two pure-noise alerts.** An unrelated nightly batch job throwing warnings, interleaved with the real signal. The AI must later mark these explicitly as ruled out, and say why.
- **The buried first symptom.** The 08:40 P4 heap alert sits far down the scroll, visually indistinguishable from noise. It is the actual beginning of the story. When the AI surfaces it as event one, pause on it — that beat lands hard with anyone who has sat on a bridge call.
- **Four duplicate incidents.** Raised by four different rules for one event. Shows that rule coverage and incident clarity are different things.
- **A stale runbook.** One of the three candidates references a service name that was renamed 8 months ago. Small touch, universally recognised.

### Optional toggle: "Show all firing rules"

A control that expands a panel listing all 412 rules with the 8 that fired highlighted. Use it only if challenged on rule coverage — it makes the point that nothing is being hidden or suppressed, and that the AI's input is precisely this output.

## 5. The transition

This is the most important 4 seconds of the demo. It carries the layering argument without anyone having to make it verbally.

**Trigger.** A single prominent button on Screen 1: **Run AI correlation**.

**The animation, in order**

1. The 147 alert rows stop scrolling and freeze.
2. Rows belonging to this incident (the 8 rule hits plus their repeats) get a left-edge highlight. The two noise alerts get a dimmed treatment rather than disappearing.
3. The highlighted rows **fly downward and stack**, collapsing into a single incident card. Each row shrinks into a small evidence chip attached to that card rather than vanishing.
4. The card expands into the Screen 2 layout.
5. Palette shifts: alarm reds drain to a calm slate, with severity retained only as small accent marks.

**Total duration.** 2.5–4 seconds. Long enough to read, short enough not to feel like a screensaver. Give it a skip-on-second-click so you are not hostage to it in a live room.

**Why the rows must not disappear.** The entire objection you are answering is "we already have 400 rules." If alerts vanish, the animation says *replaced*. If they compress into evidence, it says *consumed*. Same data, opposite message. This is worth being fussy about.

**Persistent artefacts after the transition.** Three things stay on screen for the rest of the demo:

- Badge: `8 of 412 ELK rules fired · all 8 consumed as evidence · 0 suppressed`
- Badge: `2 alerts assessed as unrelated — see Ruled Out`
- The bridge timer, still counting up

**The layer diagram.** A small always-visible stack in the corner, three bands:

```
  ┌──────────────────────────────────────┐
  │  AI correlation & reasoning  (new)   │
  ├──────────────────────────────────────┤
  │  ELK rules · Kafka · APIM · MFT      │
  │  ServiceNow · change records         │  ← unchanged
  ├──────────────────────────────────────┤
  │  Production estate                   │  ← unchanged
  └──────────────────────────────────────┘
```

When the rules question comes up — and it will come up again — point at this rather than re-arguing it.

## 6. Screen 2 — "With AI"

Seven panels. The governing rule of the layout: **observed facts and inferred causes never share a panel, and are styled differently** — facts on a light surface with a solid border, inferences on a tinted surface with a dashed border and a small `INFERRED` tag. This is a stated client requirement, so make it impossible to miss.

### Panel A — Incident header

`INC0098451 · P1 · Order flow degraded` with the three duplicate incidents shown as merged chips. A one-sentence plain-English summary generated by the model: what broke, for whom, since when. This sentence is the single most quoted output of the whole system — it is what gets pasted into the bridge call.

### Panel B — Observed timeline (facts)

Vertical, earliest at top, each event carrying:

- Timestamp (IST display, UTC on hover)
- Source system badge — ELK / Kafka / Apigee / APIM / MFT / ServiceNow / DevOps
- The raw signal, and a link to the underlying record
- A `FIRST SYMPTOM` marker on the 08:40 heap alert

Every row is traceable to a source file. Nothing generated, nothing inferred. Say this out loud during the demo.

### Panel C — Candidate causes (inferred)

Two or three cards, ranked, each with:

- Cause statement in one line
- Confidence, as a band — `High` / `Moderate` / `Low` — not a false-precision percentage
- **Two columns side by side:** *Supports* and *Contradicts*. Both populated. A cause card with an empty Contradicts column looks like assertion and should be treated as a prompt failure.
- "What would change this" — the specific observation that would move it up or down

### Panel D — Ruled out

Short list of what was considered and dismissed, with the reason. The two noise alerts live here. So does the rejected alternative from the scenario spec. This panel buys more credibility per pixel than anything else on the screen, because it is what a good engineer does and a rule engine cannot.

### Panel E — Diagnostic checks

Ordered list, cheapest-and-most-decisive first. Each check carries: the command or query to run, the expected output if cause A is true, the expected output if cause B is true, and which hypothesis it settles. This is the runbook deliverable from the requirements, generated rather than maintained.

### Panel F — Blast radius

Channels affected, orders currently stuck, value at risk, downstream systems degraded, and whether the partner B2B feed is impacted. Populated from the observed data, not estimated by the model — keep it on the facts side of the line.

### Panel G — Recovery, behind the gate

Proposed action, stated plainly (`Replay 412 messages from offset 4,481,209 to DLQ, then resume consumer group`). A risk note. A rollback path. And the action button **disabled** until an approval dialogue is completed with an approver name and reason.

On approval: a logged action record appears — who, when, what, on what evidence — followed by a verification step that confirms recovery against observed signal. The approval record is one of the five required outputs; make it visible rather than implied.

### The closer — late evidence

A button labelled **Inject delayed MFT log**. On click:

1. The new event slots into the timeline at its true position, highlighted as newly arrived
2. Cause ranking re-computes — and in the scripted scenario, first and second swap
3. A diff panel appears: *what changed and why*, naming the specific evidence that moved

This is the strongest thirty seconds you have. Rehearse it until it is smooth, and do not explain it beforehand — let the ranking flip, then ask the room what that would have cost them on a bridge call.

### Scenario switcher

A discreet control, top right, to move between S1–S5. Run S1 then S2 back to back. Same symptom shape, different cause, different check ordered first. If anyone doubts the system is reasoning rather than looking up, that pair settles it in under two minutes.

## 7. Data generator

One Python script, `generate.py`, producing a folder per scenario. No dependencies beyond the standard library. Runs in seconds, regenerable, deterministic under a fixed seed so the demo never shifts under you.

```
/data
  /s1-memory-leak
    elk-logs.ndjson
    kafka-lag.csv
    apigee-errors.json
    apim-errors.json
    mft-transfers.csv
    servicenow-incidents.json
    change-records.json
    late-evidence.ndjson      ← withheld until the closer button
  /s2-poison-message
  /s3-config-change
  /s4-mft-truncation
  /s5-oracle-saturation
```

### Per-source formats

**`elk-logs.ndjson`** — one JSON object per line, ECS-ish field names so it reads as real to anyone who has used Kibana:

```json
{"@timestamp":"2026-09-18T09:52:14.221Z","log.level":"ERROR","service.name":"inventory-reservation","kubernetes.pod.name":"inv-resv-svc-7d4f-xk21","rule.id":"ELK-R-0217","rule.name":"Container OOMKilled","event.severity":1,"message":"Container killed: OOMKilled, restartCount=3","labels.correlation_id":"mrd-20260918-a41c9f02","container.memory.usage.pct":0.99}
```

**`kafka-lag.csv`** — 15-second buckets across the incident window, one row per consumer group per topic: `timestamp,consumer_group,topic,partition,current_offset,log_end_offset,lag`. In S2 the `current_offset` column must stay flat — this is the decisive evidence and it has to be visible in the raw data, not asserted.

**`apigee-errors.json`** and **`apim-errors.json`** — per-minute aggregates: endpoint, status code, count, p99 latency, and a sample of correlation IDs.

**`mft-transfers.csv`** — `transfer_id,filename,source,target,start_time,end_time,status,bytes,declared_rows,actual_rows`. Timestamps here deliberately lack a timezone offset, as a realistic normalisation wrinkle. In S4 `status` is SUCCESS while `declared_rows` and `actual_rows` disagree — the whole scenario turns on the generator being honest about this.

**`servicenow-incidents.json`** — number, opened\_at, short\_description, description, priority, assignment\_group, state, and a work\_notes array. Multiple incidents per scenario, deliberately overlapping.

**`change-records.json`** — change number, type (standard/normal/emergency), implemented\_at, component, description, implementer, approval state, rollback plan. S3's CHG0044219 is the smoking gun; include six unrelated changes in the same window as chaff so finding it is a real discrimination task.

### Generation rules

- **Correlation IDs must actually thread.** The same ID appears in the gateway record, the service log, the Kafka header field and the MFT manifest. If this is sloppy, the correlation step produces a plausible-looking timeline that falls apart the moment someone clicks through to a source record.
- **Include pre-incident baseline.** 60 minutes of normal traffic before onset in every file. Without it, trend-based reasoning has nothing to work with, and "heap climbed steadily" is unsupportable.
- **Plant the contradiction explicitly.** Each scenario's contradicting evidence must exist as a real record — last Tuesday's higher-volume run in S1, the flat heap series in S2, the working cached-price path in S3. Not narrated in a comment; present in the data.
- **Volume target.** Around 800–2,000 ELK lines per scenario. Enough to be unreadable by hand, which is the point, and small enough to pass to a model without truncation games.
- **Fixed seed.** Same output every run. A demo that shifts between rehearsal and delivery is a demo that fails in the room.

### One Claude Code prompt writes all of this

Hand it section 2 (the estate), section 3 (the five scenarios) and this section, and ask for the complete generator in one pass. Expect roughly an hour including a correction round, not a day. Then spot-check by hand: open `kafka-lag.csv` for S2 and confirm the offset really is flat, and open S4's MFT row and confirm the row counts really do disagree. Those two checks catch most generation errors.

## 8. The AI reasoning layer

### What is code and what is the model

Draw this line hard and be able to state it in one sentence, because you will be asked. If the model does the parsing too, the demo becomes unexplainable the moment someone asks what is real.

**Deterministic code does:**

- Parse the six file formats into one event list
- Normalise timestamps to UTC, resolve the MFT no-offset case
- Resolve service aliases via the CMDB map (`inv-resv-svc` → `inventory-reservation`)
- Normalise severity to a common 1–4 scale
- Thread correlation IDs, group events into incident candidates
- Sort chronologically

**The model does one thing:** takes the normalised event list plus change records plus ticket text, and returns hypotheses, evidence weighting, check ordering and a recovery proposal. Nothing else.

The line to say out loud: *facts are assembled by code and are traceable to source records; only the reasoning about those facts is done by the model.* That sentence is what makes the observed-versus-inferred separation credible rather than decorative.

### Prompt contract

System prompt, in substance:

> You are an incident analyst. You receive a normalised event list from a production estate, plus change records and ticket text. Produce a diagnosis.
>
> Rules you must follow:
>
> - Never state a cause as fact. Causes are hypotheses with confidence bands.
> - Every hypothesis must carry both supporting and contradicting evidence. If you cannot find contradicting evidence, say so explicitly rather than leaving it empty.
> - Every evidence item must cite an `event_id` from the input. Do not reference anything not in the input.
> - Produce at least two hypotheses, at most four.
> - Order diagnostic checks by decisiveness per unit of effort — cheapest decisive check first.
> - Recovery proposals are proposals. Never describe an action as taken.
> - Where events are absent that you would expect to be present, say so — absence is evidence.
> - Return only JSON matching the schema. No preamble, no markdown fences.

The absence clause matters more than it looks: it is what lets S4 work, and it is a genuinely model-shaped piece of reasoning.

### Output schema

```json
{
  "incident_summary": "one sentence, plain English",
  "timeline": [
    {"event_id":"e-0001","ts":"...","source":"ELK","component":"...",
     "description":"...","is_first_symptom":true}
  ],
  "hypotheses": [
    {"rank":1,"cause":"...","confidence":"High|Moderate|Low",
     "supports":[{"event_id":"e-0004","why":"..."}],
     "contradicts":[{"event_id":"e-0019","why":"..."}],
     "what_would_change_this":"..."}
  ],
  "ruled_out": [{"candidate":"...","reason":"..."}],
  "checks": [
    {"order":1,"action":"...","command":"...",
     "if_result_a":"supports hypothesis 1","if_result_b":"supports hypothesis 2",
     "effort":"low"}
  ],
  "blast_radius": {"channels":["..."],"orders_stuck":412,
                   "downstream_degraded":["..."]},
  "recovery": {"proposal":"...","risk":"...","rollback":"...",
               "requires_approval":true},
  "post_incident_note": "draft ServiceNow work note"
}
```

### Re-run on late evidence

Second call, same schema, with the original event list plus the late event and the previous output. Ask specifically for what changed and why. Render that as the diff panel. Do not try to compute the diff in code — the model explaining its own revision is more convincing and considerably less work.

### Validation before you trust it

Run all five scenarios and check three things by hand:

1. Every `event_id` cited actually exists in the input. A hallucinated citation in front of a client is unrecoverable, and a 20-line validator catches it.
2. Every hypothesis has a non-empty `contradicts` array.
3. S1 and S2 produce genuinely different first-ordered checks. If they do not, the prompt is pattern-matching on symptoms and needs the offset and heap evidence made more salient in the normalised event descriptions.

## 9. Architecture and stack

Deliberately boring. Every hour spent on infrastructure is an hour not spent on the reasoning layer, and the reasoning layer is the only part they have not seen before.

### Stack

- **Frontend:** single-page React app, Tailwind, one build artefact. No router, no state library, no component kit beyond what you need.
- **Data:** static JSON and CSV files, loaded at startup. No database, no API, no auth.
- **AI calls:** either a thin local server holding the API key, or pre-computed cached responses shipped as JSON. Build both paths — see caching below.
- **Normaliser:** plain TypeScript in the app, or a Python pre-pass that emits `normalised-events.json`. The Python pre-pass is simpler and easier to explain on screen.
- **Deployment:** runs locally. If it needs to be shared, it publishes as a self-contained page.

### Why no real infrastructure

Worth stating explicitly if asked, because it sounds like a shortcut and is not. A real Kafka cluster proves that Kafka works. Nobody in the room doubts that Kafka works. The question on the table is whether the reasoning is any good, and synthetic signals answer it exactly as well as real ones while costing three weeks less. If the POC lands and they want depth, a Docker Compose stack with genuine failure injection is the natural second step — and the generator scripts become the injection scripts, so nothing built here is wasted.

### File layout

```
/incident-ai-poc
  /data
    /s1-memory-leak ... /s5-oracle-saturation
    /cached                 pre-computed AI responses per scenario
  /generator
    generate.py
    scenarios.py            the five specs as data
  /normaliser
    normalise.py            → normalised-events.json per scenario
    cmdb-aliases.json
  /app
    /src
      App.tsx
      /screens  AlertFloor.tsx  AiView.tsx
      /panels   Timeline.tsx  Hypotheses.tsx  RuledOut.tsx
                Checks.tsx  BlastRadius.tsx  Recovery.tsx
      /components  AlertRow.tsx  EvidenceColumns.tsx
                   ApprovalDialog.tsx  LayerStack.tsx
      /lib      ai.ts  cache.ts  types.ts
  /prompts
    analyst-system.md
    late-evidence.md
```

### Caching, and why it is not optional

Pre-compute every scenario's AI response and ship it as JSON. Default the demo to cached. Keep a live toggle for one scenario so you can show it running for real when asked — and you will be asked.

This is not about hiding anything. A live call in a client room is a network dependency, a latency dependency and a non-determinism dependency stacked on top of each other, and if any one fails the room remembers the failure rather than the product. Show live once, deliberately, when you have chosen the moment.

### Visual design

Screen 1 and Screen 2 must feel like different worlds — that contrast is doing persuasive work.

- **Screen 1:** dense, monospace, high-alarm reds and ambers on near-black, tight spacing, information without hierarchy. Deliberately hard to read.
- **Screen 2:** generous spacing, clear type hierarchy, calm slate palette, colour reserved for the fact/inference distinction and severity accents.
- **Fact surfaces:** light background, solid border.
- **Inference surfaces:** tinted background, dashed border, `INFERRED` tag.
- One accent colour only. Resist the urge to make Screen 2 colourful — its credibility comes from looking restrained.

## 10. Three-day build order

The sequencing principle: **the reasoning layer must work before any pixel is styled.** If the prompt is not producing clean output by the end of Day 1, cut to three scenarios rather than compressing Day 2. A beautiful screen wrapped around weak reasoning fails in a way that a plain screen wrapped around good reasoning does not.

### Day 1 — data and reasoning

**09:00–10:30 · Scenario specs as data.** Turn section 3 into `scenarios.py` — each scenario a structured object: components, event sequence with offsets, planted contradiction, expected top hypothesis. Do this by hand or with light assistance; it is the source of truth for everything downstream and worth being precise about.

**10:30–12:30 · Generator.** One Claude Code prompt:

> Read scenarios.py and the estate topology. Write generate.py producing, per scenario, seven files in the formats specified: ELK NDJSON, Kafka lag CSV, Apigee and APIM JSON aggregates, MFT CSV, ServiceNow JSON, change records JSON, plus a withheld late-evidence file. Standard library only, fixed seed. Correlation IDs must thread across files. Include 60 minutes of pre-incident baseline in every file.

Then spot-check by hand: S2's offset column flat, S4's row counts disagreeing.

**12:30–14:00 · Normaliser.** `normalise.py` — parse all seven formats into one sorted event list with stable `event_id`s, resolve aliases, handle the MFT no-offset timestamps, normalise severity. Emits `normalised-events.json` per scenario. Straightforward code; let Claude Code write it in one pass.

**14:00–18:00 · The prompt. This is the POC.** Everything else is packaging. Write the analyst system prompt, run it against S1, read the output properly, and iterate. Then S2 — and specifically check that it does not simply repeat the S1 diagnosis. Then S3, S4, S5.

Expect 6–10 iterations. The failure modes you are correcting for, in the order they usually appear: empty `contradicts` arrays; hypotheses stated with unearned certainty; checks ordered by thoroughness rather than decisiveness; citations to `event_id`s that do not exist; and S2 being diagnosed as S1.

**End-of-day gate.** Five valid JSON outputs, all citations resolving, S1 and S2 genuinely differing. If you are not here, cut scenarios — do not push into Day 2.

### Day 2 — the application

**09:00–11:00 · Screen 1.** Alert floor, 147 rows, team channels, L1 panel, bridge timer, four duplicate incidents. Density is the whole point; do not tidy it.

**11:00–13:00 · Screen 2 skeleton.** Seven panels, real data, minimal styling. Get the fact/inference separation structurally right before making anything look good.

**14:00–15:30 · Evidence columns and approval gate.** The Supports/Contradicts side-by-side layout, the Ruled Out panel, the approval dialogue with approver name and reason, and the logged action record.

**15:30–17:00 · The transition.** Collapse animation, palette shift, the persistent badges, the layer stack. Budget properly for this — it carries the central argument and animation always takes longer than estimated.

**17:00–18:30 · Late-evidence closer.** Inject button, timeline update, ranking flip, diff panel.

**End-of-day gate.** Full path clickable on S1 with no dead ends.

### Day 3 — hardening and rehearsal

**09:00–11:00 · All five scenarios wired.** Scenario switcher, cached responses for all five, live toggle on one. Verify each end to end.

**11:00–13:00 · Visual pass.** Type hierarchy, spacing, the two-worlds contrast between Screen 1 and Screen 2. First time all day you are allowed to care how it looks.

**14:00–15:00 · Break it deliberately.** Click things in the wrong order. Double-click the transition. Switch scenarios mid-animation. Approve twice. Fix what breaks — this hour reliably finds three things.

**15:00–16:00 · Closing deck, 5 slides.** Current-state timeline versus this. What is deterministic versus what the model does. The layer diagram. What a real deployment needs. Suggested next step.

**16:00–18:00 · Rehearse three times.** Out loud, timed, standing up. The third run is where the talk track actually settles. Rehearse the objection answers separately — particularly the rules one, since it has already been raised and will be raised again.

### Working with Claude Code

- Give it this whole document as context at the start of each session.
- One session per component: generator, normaliser, Screen 1, Screen 2, transition. Don't interleave.
- Let it write the generator and normaliser almost unsupervised — they are mechanical.
- Do **not** delegate the prompt iteration. That is the product, and it needs your judgement about what reads as credible to an ops audience.
- Build the normaliser as plain code even if it is tempting to let the model handle parsing. The explainability of that boundary is worth more than the hour it saves.

## 11. Demo run sheet — 12 minutes

No slides until minute 10. Open on Screen 1, already scrolling, before anyone has settled.

**0:00 — Silence, 10 seconds.** Let them look at the alert floor. Do not narrate. Then: *"This is 147 alerts in six minutes. Every single one is correct. Four separate P1 incidents were raised. Nobody in this picture knows what broke."*

**0:30 — The L1 dead end.** Walk the right rail. Runbook searched, three candidates, none matching, one referencing a service renamed eight months ago. Pod restarted twice, no effect. Escalated. Point at the bridge timer: *"One hour fourteen minutes. Six engineers. No agreed cause."*

**1:30 — Name the gap.** *"Detection took ninety seconds. Diagnosis is still running. That gap is what we built for."*

**2:00 — Click Run AI correlation.** Say nothing over the animation. When it settles: *"Nothing was suppressed. All eight rule hits are in there as evidence."* Point at the badge.

**2:30 — The timeline.** Scroll to the top and stop on the 08:40 heap alert: *"This fired seventy minutes before anyone noticed. It was a P4. It is the first symptom."* Then: *"Every row here traces to a source record. This panel contains no inference at all."*

**4:00 — The causes.** Read the top hypothesis, then move straight to its Contradicts column: *"This is the part that matters. It argues against itself. The service handled higher volume last Tuesday — so this is time-based, not load-based."*

**5:00 — Ruled out.** *"Two of those 147 alerts were unrelated. Here they are, and here is why."* Short beat, disproportionate credibility.

**5:30 — Checks.** *"Ordered by decisiveness, not thoroughness. The first one is a single query and it settles between the top two causes."*

**6:00 — Approval gate.** Show the recovery proposal, then the disabled button. Complete the dialogue. Show the logged record: *"Nothing executes without a named human. That record is the audit trail."*

**7:00 — Switch to S2.** *"Different incident. Watch the symptoms."* Lag climbing, pods restarting, 502s — visually near-identical to S1. *"A bridge call would call this a memory leak. Here is what the system says."* Show the flat heap, the static offset, the three-minute restart metronome. *"Different cause, different first check."* This is your proof of reasoning; give it the full 90 seconds.

**8:30 — The closer.** No setup. Click **Inject delayed MFT log**. Let the ranking flip. Then: *"A log file arrived twenty minutes late. The diagnosis changed, and it says what changed and why. How long would that have taken on the call?"*

**9:30 — Stop clicking.** Five slides: current versus new timeline; deterministic versus model; the layer diagram; what a real deployment needs; suggested next step.

**11:00 — Questions.**

### Objection handling

**"We already have 400 rules."** Agree, immediately and without qualification. *"You do, and they all fired correctly — that is the first screen. The rules are the sensors. This is the analyst. Rule count going up makes this more valuable, not less: more signal, same number of people reading it."* Then point at the layer diagram. Then ask the question that settles it: *"On your last cross-system P1, how long between first alert and agreed cause?"*

**"Can we trust the AI?"** *"You are not asked to. It cannot execute anything. It proposes, cites its evidence, shows what argues against its own conclusion, and a named human approves. The facts panel is assembled by code and traceable to source records."*

**"This is synthetic data."** *"It is, deliberately. Real infrastructure would prove Kafka works, which nobody doubts. What is on trial is the reasoning, and synthetic signals test that exactly as well. Give us a real past P1 — the alert list and the timeline someone wrote afterwards — and we will run it against that."* This is the strongest close available to you. Offer it unprompted if the room is warm.

**"What about our 400 rules' maintenance burden?"** Do not oversell. This does not reduce rule count. It changes what happens after they fire.

**"How long to make it real?"** Be honest about the dependency: correlation IDs, timestamp consistency, CMDB accuracy. Those determine the timeline, and that assessment is week one of any real engagement, not an afterthought.

## 12. Risks, cut lines, and what comes after

### Risks in the build

| Risk | Mitigation |
| --- | --- |
| Prompt iteration overruns Day 1 | Hard gate at end of Day 1. Cut to three scenarios rather than compressing Day 2. |
| Transition animation eats Day 2 | Timebox to 90 minutes. A simple fade that works beats a stack animation that does not. |
| S1 and S2 produce the same diagnosis | Caught by the Day 1 validation. Fix by making the offset and heap series more salient in the normalised event text, not by hinting the answer in the prompt. |
| Live call fails in the room | Cached by default, live on one scenario only, chosen by you. |
| Hallucinated event citations | 20-line validator over every cached response. Run it before the demo, not after. |

### Cut lines, in order

If time runs short, cut in this sequence. Everything above a cut stays.

1. S5 (Oracle saturation) — the most complex to generate, and S1/S2 already carry the reasoning proof
2. S4 (MFT truncation) — though it is the most distinctive scenario, so cut it reluctantly
3. Blast radius panel
4. The collapse animation, down to a crossfade
5. The live API toggle

**Never cut:** S1 and S2 as a pair, the Contradicts column, the Ruled Out panel, the approval gate, the late-evidence closer. Those five carry the entire argument.

### Honest limitations to state rather than hide

Saying these unprompted is worth more than being caught on them.

- The output quality depends on correlation ID discipline, timestamp consistency and CMDB accuracy. Where those are weak, the timeline degrades — and in most real estates at least one is weak.
- This does not reduce the number of rules or their maintenance burden.
- Novel failure modes with no precedent in the signal data will produce weaker hypotheses. The system reasons from evidence; thin evidence gives thin answers.
- The L1 role changes from "check and escalate" to "verify and approve." That is an organisational conversation, not just a tooling one, and it is better raised by you than discovered by them.

### What a real deployment needs

Worth having ready on a slide, because someone will ask.

1. **Signal readiness assessment** — correlation ID coverage, timestamp consistency, CMDB-to-runtime name mapping. One to two weeks, and genuinely the make-or-break.
2. **Read-only connectors** — ELK, Kafka metrics, gateway logs, MFT, ServiceNow, change management. Read-only throughout the first phase.
3. **Retrospective validation** — run against 20–30 historical P1s and compare the generated diagnosis to what the team concluded at the time. This is the only credible accuracy measure, and it is available without touching production.
4. **Shadow mode** — runs alongside live incidents, produces output, changes nothing. Builds trust and produces real accuracy data.
5. **Approval workflow integration** — ServiceNow approval records, RBAC on who can approve what.
6. **Feedback loop** — the post-incident learning step from the original requirements, closing back into hypothesis quality.

### The strongest next step to propose

Ask for one real past P1: the alert list, the eventual timeline, and the post-incident report. Run the system against it and compare. It costs them nothing, requires no access to production, and it converts the entire conversation from "does this work" to "how well does it work on ours." Offer this at the end of the demo while the room is still warm.
