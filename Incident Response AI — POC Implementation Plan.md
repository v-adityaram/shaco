# Incident Response AI — POC Implementation Plan

2026-09-18 · v2 — rebuilt on real HIP Ops data (June–August 2026 incident inflow, live Sonar "Full Levels" dashboard)

## 0. What changed in v2, and why

v1 demonstrated the idea on an invented retail estate ("Meridian Retail": order-intake, Apigee, APIM, Kafka topics named `order.*`). It worked as a story but a reviewer from the client's HIP Ops team would spot within thirty seconds that nothing on screen looked like *their* floor. v2 replaces the invented estate with the real one, using three inputs:

1. **Three months of real incident inflow** (June, July, August 2026 — 3,118 incidents) exported from ServiceNow, plus the monthly analysis tabs (classification, close codes, by-team, by-day, one-year trend).
2. **Screenshots of the live Sonar "Full Levels" Kibana dashboard** (exchange KPI tiles, exchange table, traces table) captured 2026-09-18.
3. **The v1 plan**, whose narrative, screens, cut lines and run sheet are unchanged in structure. What changes is the vocabulary, the estate, the five scenarios, and the look of Screen 1.

Nothing about the argument changes: rules are the sensors, this is the analyst, facts and inferences never share a panel, nothing executes without a named approver. What changes is that every alert, exchange name, error string, host and recovery step on screen is a shape the audience has seen before.

**Privacy rule for the build.** The raw exports contain employee names and ticket text. They stay in `/Auto Alerts/` (git-ignored) and are never copied into the repo. The generator reproduces *patterns* (error strings, naming conventions, distributions) with invented ticket numbers, exchange ids and business objects.

### 0.0 The governing principle: the AI sits on top of the rules — it understands, it does not detect

The client already runs 400+ monitoring rules (HIPMON, Sonar, Splunk, ELK) and they work. Nothing in this POC re-detects, re-thresholds or replaces them. Concretely:

- **Input to the AI is rule output.** Every alert a rule already fired (`kind: rule_hit`, with its `rule_id`) plus the records an analyst would pull up around those alerts (`kind: context` — exchange logs, host metrics, lag samples, transfer records, change and vendor records, counts and baselines computed by code). The AI is never asked to find anomalies in raw streams.
- **Where no rule fired, that is a finding.** S4's stalled exchange has no rule; the AI's job is to notice the *absence* in the context and say no rule covers it.
- **Counts are code, not model.** "N of 412 rules fired" and "2 unrelated" come from the evidence pack, not from the AI.
- **Only a showcase subset is hand-authored.** S1 and S2 (the never-cut pair) ship a cached diagnosis as showcase and fallback. **S3, S4, S5 have no cached answer at all — their diagnosis comes only from a live AI call**, and a successful live run is saved on the server as the fallback for the next failure. Nothing is fabricated to fill a gap.

### 0.1 What the real data says (this is the calibration for everything below)

| Fact | Value | What it means for the demo |
| --- | --- | --- |
| Incidents, Jun / Jul / Aug 2026 | 1,194 / 1,036 / 888 | Screen 1 density is realistic, not dramatised |
| Auto-logged (HIPMON, Splunk, Workato) | 1,272 of 3,118 (41%) | The alert layer already works; volume is not the problem |
| `[AUTO]` HIPMON incidents | 868, across 190 distinct half-flows | Every alert names a project, a half-flow and an error code |
| Incidents with a parent/child link | 390 (12.5%); 82–171 child incidents per month | Duplicate incidents for one event are routine, not an edge case |
| Median open-to-resolve | 6.6 h auto-raised, 13.8 h user-raised (p90 ≈ 90 h) | The diagnosis gap is measured in hours, not minutes |
| Closed with a *Replay* sub-code | 534 of 2,110 classified closes (25%); "Alerting" 45% | Recovery is overwhelmingly "replay the failed exchange" — the approval gate must gate replay |
| Platform-class alerts | 406 (13%): swap space 181, FS usage 128, CPU 85 | The standing noise floor — Linux host alerts on MFT and ETL hosts, mostly non-prod |
| Environment / zone | PRD 82%; EMEA 59%, AMER 25%, APAC 16% | Demo runs on EMEA PRD |
| Owning team (real "Team" field) | ESB 35%, MFT 19%, Azure 19%, ETL 10%, Apigee 5%, Workato 3%, Kafka 2% | This is the true ownership split — replaces the invented five teams |
| Recurring subjects | Top 20 subjects = 20% of all incidents; 1,475 distinct subject prefixes | A long tail plus a fat head of repeats |
| Opened hour (UTC) | No quiet hours; peak 08:00 | Incidents arrive around the clock, so first-responders are often asleep |
| One-year trend | Transactions 0.8–1.4 B/month, ≈0.25–0.45 incidents per million | Incident rate is tiny relative to volume — the cost is diagnosis time, not frequency |

**The five most useful real patterns, and where they land in the scenarios below:**

- Consumer lag on a Confluent processing group with hundreds of thousands of exchanges stuck `INPROGRESS`, cured by moving a heavy half-flow to a larger processing group (June 4–5) → **S1**
- SAP → warehouse deliveries stop because the PI7 IDoc listener node hangs; replay does nothing; restarting the node fixes it (June 2) → **S2**
- A vendor (Workato) platform push breaks every IDoc outbound flow to the SAP hubs with `Failed to fetch ConfigForDocSending`; rollback via emergency change (June 9, July 20) → **S3**
- A file exchange stalls `INPROGRESS` after an EMEA patching window; nothing ever turns `FAILED`; a downstream database locks hours later (June 10, June 15) → **S4**
- 30+ unrelated half-flows fail with `Connection refused: hip-fwk-transco-cache…:8080` while each replay succeeds (July 28, August 8, August 17) → **S5**

## 1. Demo concept

**One line:** AI-assisted incident diagnosis for the HIP integration platform — one timeline, ranked causes with evidence for and against, human-approved recovery.

**What we are actually demonstrating.** Not detection. HIPMON, Sonar, Splunk and the ELK rules (400+) already detect correctly. What we are demonstrating is the compression of *diagnosis*: the hours between "alerts fired" and "we agree what broke".

**The narrative arc.** Three beats, one screen, no slides until the end:

1. **Today.** The Sonar "Full Levels" dashboard as the L1 sees it — 975,099 exchanges in 24 h, 22,260 failed, a wall of `INPROGRESS`, a HIPMON alert stream beside it, four duplicate ServiceNow incidents, an L1 whose runbook search returns generic matches, and a bridge timer already past an hour. Every alert is correct. Nobody knows what happened.
2. **Click "Run AI correlation".** The alerts do not vanish — they collapse into one incident, each alert becoming a cited evidence item. Rules are the input layer, not the casualty.
3. **With AI.** One observed timeline, two or three ranked candidate causes with evidence for *and against*, ordered diagnostic checks, blast radius, and a recovery action (usually a replay or a listener restart) locked behind an approval gate.

**The closer.** A late-evidence button injects a delayed log; the timeline updates, confidence moves or a rival is closed out, and a diff says what changed and which evidence did it. Thirty seconds, and the one thing a rule engine structurally cannot do.

**Positioning against the 400-rules objection.** Stated on screen and in the talk track:

> The 400 rules are the sensors. This is the analyst.

A persistent badge on the AI screen reads *"N of 412 rules fired — consumed as evidence, none suppressed."* Real-data support for the line: 868 HIPMON auto-incidents in three months, 12.5% of incidents already linked as duplicates of a parent, and the median auto-raised incident still takes 6.6 hours to resolve. More rules do not shorten that; correlation does.

**Two non-negotiables, visible in the UI.** Observed facts and inferred causes live in separate, differently-styled panels and are labelled as such. And no recovery action executes without an explicit human approval that is logged.

## 2. The estate — HIP (Hybrid Integration Platform)

A real-shaped integration estate. Sources and targets are business systems; HIP moves *exchanges* between them. This is the vocabulary the Sonar dashboard and every alert already use.

### Exchange model (the unit everything keys on)

- An **exchange** is one business transaction end to end (e.g. `GLBL_SAPS4HANA_SAPS4HANA_ASN_INT`, one delivery, one file). It has an `exchange.id` (18–24 digits, or a UUID for framework-native flows) that threads through every log line.
- An exchange is a chain of **half-flows** (`…_01_ESB`, `…_02_MFT`, `…_02_API`). The dashboard shows `halfflow.count` and `halfflow.missing` as `2/4` — two of four half-flows seen. **An exchange stuck at `2/4` is the signature of a silent stall.**
- Exchange status: `COMPLETE`, `COMPLETE (F)` (completed after a failure), `INPROGRESS`, `WARNING`, `FAILED`, `REPLAYED`.
- Trace event levels: `ENTRYINFO`, `EXITINFO`, `INFO`, `ERROR`. Event codes follow `IFP_PUB001`, `IFP_RTG001`, `IFP_MAP001`; HIPMON alert codes are `GEN01`, `IVK003`, `TEC01`, `MAP002`, `COM01`, `RTG003`, `PRC003` and their `ETP_*` twins.

### Topology

| Layer | Components |
| --- | --- |
| Business systems | SAP S/4 (NEO), SAP ECC hubs CE / UK / IT / NE (via PI7), Manhattan WMS (MANH/MAWM), Salesforce, Anaplan / Futurmaster, 3PL partners, GCP consumers |
| Integration core | ESB (TIBCO BW half-flows on Kubernetes, namespace `hip-cloud-esb`), Workato recipes, Apigee APIs, framework services incl. `hip-fwk-transco-cache` |
| Async | Confluent Kafka — one topic per processing group, e.g. `emea.it4it.fwk-message.process-int-opsfin-01-neo-odes-large.v1`; processing groups `opsfin-01-neo-odes-large`, `opsfin-01-quick`, `…-default` |
| File transfer | MFT on Sterling File Gateway (SFG); hosts `FRHIPG{PR,PP,QA}MFTSI0{1,2}`, `SGLORHIP{P,Q}MFTSI{1,2}`, `USAMRHIP{D,Q}FTSI01` |
| Batch / ETL | Control-M jobs, ETL hosts `SGLORHIP{P,Q}ETLPC1` |
| Monitoring | **Sonar** (Kibana dashboards over exchange/half-flow logs), **HIPMON** (rule engine raising `[AUTO]` incidents), **Splunk** (Linux host alerts), ELK (400+ rules) |
| Ops tooling | ServiceNow (incidents, parent/child links, close codes), change records, vendor tickets |

### Ownership — why nobody sees the whole picture

Taken from the real `Team` field, not invented. Each team sees its own hop.

- **ESB** — half-flow logic, mapping, processing groups (35% of incidents)
- **MFT** — Sterling File Gateway, file connectors, MFT hosts (19%)
- **Azure / Platform** — Kubernetes, `hip-cloud-esb`, cache and framework pods (19%)
- **Workato** — recipes, HTTP/RFC connectors, vendor liaison (3%)
- **Kafka / Confluent** — brokers, topics, consumer groups (2%)
- Also present in the data and shown as smaller channels: **Apigee**, **ETL/Control-M**, **SDM/Lead**

Responders are tiered L1 → L2 → L3 (HIP Ops), with L3 = the vendor or the platform team.

### Conventions the generator must hold to

These are what correlation keys on, so they have to be right or the timeline silently breaks.

- **Correlation ID** — the `exchange.id`. Threads through Sonar half-flow logs, HIPMON alert bodies, ServiceNow descriptions and MFT transfer rows. Some flows use 24-digit ids (`yyyymmddHHMMSS` + 10 digits); framework-native ones use UUIDs. Both must occur.
- **Timestamps** — ISO-8601 UTC in the files, rendered in IST in the UI. One source (MFT / SFG) deliberately emits local time with no offset.
- **Service naming** — three names for one thing: the ServiceNow CI / project name (`HIPEMEA`, `KEPLER_NEXTGEN`), the half-flow name (`EMEA_KEPLERNG_SALESORDER_OUT_02_ESB`), and the Kubernetes deployment / ELK alias (`hip-kepler-ng-out`). The normaliser holds the alias map. This mismatch is the most common reason correlation fails in real estates.
- **Severity** — HIPMON priority (mostly `3 - High`), ServiceNow 1–5, HTTP status. Normalised to a common 1–4.
- **Alert subject format** — `[AUTO]|<PROJECT>|<HALFFLOW>|<CODE>|<ETP_CODE>` for HIPMON, `[SONAR-OPS][PRD]…` for Sonar reports, `CAPLINERR00x-Linux Host - <HOST> …` for Splunk. Reproduced verbatim in style.

## 3. Incident catalogue — five scenarios

Five scenarios, each grounded in a real June–August incident family, each carrying a **planted contradiction** that populates the "evidence against" column. S1 and S2 are the pair that does the heavy lifting: the same business symptom — *"deliveries / ASNs are not reaching the warehouse or S4"* — with different causes and a different first check. All times are 2026-09-18 UTC. **S1 and S2 are the curated showcase pair; S3, S4 and S5 are AI-live only** (see §0.0).

---

### S1 — Large-mapping half-flow exhausts its processing group

**Real basis.** June 4–5: ASN half-flow moved into `opsfin-01-neo-odes-large`, heap exhausted, 45k+ exchanges `INPROGRESS`, shuttles arrived without ASN in S4.

**Fault.** After a large STO batch, the ASN mapping half-flow `GLBL_SAPS4HANA_SAPS4HANA_ASN_INT` produces payloads roughly 3× normal size. Heap in the `opsfin-01-neo-odes-large` processing group climbs steadily, GC thrashes, pods are OOMKilled and restart, throughput collapses and the topic backs up.

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 05:10 | Splunk | heap > 70% on `hip-esb-odes-large` pods — P4, nobody looks (**first symptom**) |
| 05:55 | Kafka | lag on `…process-int-opsfin-01-neo-odes-large.v1` starts to climb |
| 06:20 | Sonar | `GLBL_SAPS4HANA_SAPS4HANA_ASN_INT` exchanges sit `INPROGRESS` at half-flow 2/4, durations 1 → 9 min |
| 06:35 | Splunk | OOMKilled, pod restart 1; restart 2 at 06:52 |
| 07:05 | HIPMON | Consumer Lag alert, P3 |
| 07:30 | Sonar | `GLBL_MSTR_HLTH_CHK` reports 45,000+ `InProgress` |
| 08:10 | ServiceNow | User incident: "No ASN integrated in S4 — trucks waiting"; three HIPMON auto duplicates |

**Planted contradiction.** Message inflow on the ASN flow is *lower* than last Thursday, and lag on every other processing group is zero. Argues against broker trouble and against load — and points at payload size, not volume.

**Expected AI output.** First: heap exhaustion from oversized payloads in the large group, supported by the linear pre-incident heap trend, OOM restarts, and the average message-size series. Second: Kafka broker / cluster degradation, contradicted by zero lag on all other groups. First check: heap and average payload size for the group (`kubectl top` / Sonar message-size panel). Recovery: move the half-flow to the larger group and repush stuck exchanges from S4.

---

### S2 — PI7 IDoc listener hangs (the look-alike of S1)

**Real basis.** June 2: no deliveries from SAP to Manhattan since 13:30, warehouse blocked, replay did nothing, restarting `AN_COMMON_PI7IDOCListner` fixed it.

**Fault.** The listener node that receives IDocs from SAP PI7 stops consuming while its JVM stays up. No new exchanges are created. Replays have nothing to replay against.

**Why this scenario matters most.** For the warehouse the symptom is identical to S1: deliveries not arriving, tickets, HIPMON alerts. The distinguishing evidence is narrow and buried: **there is no pile-up.** No `INPROGRESS` growth, consumer lag is zero, heap is flat — because nothing is entering the platform. A bridge call routinely reads "deliveries stuck" as "processing is stuck" and reaches for S1's playbook.

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 13:29 | Sonar | last IDoc exchange from PI7 hub CE created 13:29:48; heartbeat line from `AN_COMMON_PI7IDOCListner` every 60 s until 13:30:12, then nothing |
| 13:35 | Sonar | inbound exchange count from PI7 = 0 in 5-minute buckets (baseline 180 per 5 min) |
| 13:45 | Kafka | lag on all processing groups 0; no growth anywhere |
| 14:10 | HIPMON | `NO DATA FROM SAPCE/Pi7 IN LAST 60 minutes` alert |
| 14:20 | ServiceNow | User incident: "CZ warehouse — no deliveries from SAP"; reprocess (YODI) attempted, no effect |
| 15:49 | ServiceNow | Raised to Critical; 17:17 escalated to Major |

**Planted contradiction.** The listener process passes its health check and the JVM shows normal CPU and heap. Argues against "the node is down" — it is up, it is simply not consuming.

**Expected AI output.** First: listener node hung (heartbeat stopped, zero inbound, health check misleadingly green). Second: processing-group saturation as in S1, explicitly ruled out on zero lag, flat heap, no `INPROGRESS`. First check: count of exchanges created in the last 15 minutes from PI7 — one query, decisive between S1 and S2. Recovery: restart the listener node (approval-gated), then reprocess from Manhattan.

---

### S3 — Vendor platform push breaks IDoc outbound to SAP

**Real basis.** July 20: Workato product team pushed a change with missing parameters; all IDoc outflows to the SAP CE/UK/IT hubs failed. June 9: same family, rolled back to TIBCO by emergency change.

**Fault.** A Workato platform release changes an HTTP/RFC connector default. Every recipe that calls `ConfigForDocSending` fails. HIP has no change record — the release was the vendor's.

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 09:40 | Change | Vendor release notice (Workato platform push) logged as an informational record; no HIP change, no approval record |
| 09:52 | Workato | `Recipe function execution error: Recipe function call failed` begins across IDoc-out recipes |
| 09:55 | HIPMON | `[AUTO]|EURO_COMMON_IDOC_SAPCE_YLCD01…` — `SAP RFC Error: Failed to fetch ConfigForDocSending` — then the same for SAPUK, SAPIT, SAPNE |
| 10:05 | Sonar | 30+ IDoc-out exchanges `FAILED` at half-flow 3/4 |
| 10:25 | ServiceNow | User incident: "Shipment completed in Manhattan but not integrated to SAP" |
| 10:40 | ServiceNow | Second user incident, different warehouse, same symptom |

**Planted contradiction.** A minority of IDocs (delivery type `YHIPDELVRY07` to SAPNE) still succeed intermittently, and the SAP RFC gateway health check is green. Makes it look like a flaky SAP endpoint — sending humans to the SAP team instead of the release timeline.

**Why this scenario earns its place.** No rule points at the release. The smoking gun is an unstructured vendor notice in a different system — something rules structurally cannot reach.

**Expected AI output.** First: vendor release regression (timestamp proximity 12 min before the first failure, component match, error originates on the Workato side of the RFC call). Second: SAP RFC gateway degradation, contradicted by the gateway's own green health and by the failure being on the config fetch, not the send. Recovery: emergency change to route the affected flows back to the legacy path (approval-gated), then replay failed IDocs.

---

### S4 — Silent stalled exchange after a patching window

**Real basis.** June 10: BPM file exchange stuck `INPROGRESS`, FM database locked, replay fixed it; June 15: Titan export failed during EMEA patching, user confirmed only after the fact.

**Fault.** During the EMEA patching window the MFT connector session to the ESB drops. The 02:00 file `GLBL_OPSF_ANAPLAN_BPM_to_FM` is delivered by SFG with status SUCCESS, but the ESB half-flow never starts. The exchange sits `INPROGRESS` at 2/4. It never becomes `FAILED`, so no rule fires. Five hours later the downstream database locks.

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 01:30 | Change | EMEA patching window opens — MFT hosts reboot (routine, approved) |
| 02:00 | MFT | `BPM_to_FM_0200.csv` transferred, status SUCCESS, 4.1 MB (usual 6.8 MB); trailer declares 128,400 rows, 77,032 present — never validated |
| 02:00 | Sonar | exchange starts, half-flow 1 `ENTRYINFO`, half-flow 2 never appears; exchange stays `INPROGRESS` 2/4 |
| 03:00 → 07:00 | Sonar | hourly critical-exchange report: exchange listed under InProgress, not Failed — nothing flagged |
| 07:57 | ServiceNow | User incident: "FRCPD database locked, FKF not generated" |

**Planted contradiction.** SFG and the hourly Sonar report both say the file transfer was fine — status SUCCESS, zero failed exchanges. Argues strongly against the file being the problem.

**Why this scenario earns its place.** Reasoning backwards from a late symptom to a silent, hours-earlier event that produced no alert — including reasoning about the *absence* of an expected half-flow.

**Expected AI output.** First: exchange stalled after the connector session dropped in the patching window (2/4 half-flows, truncated file, no ESB entry event). Second: source export late or empty, contradicted by the export log showing a normal run at 01:58. Recovery: replay the exchange (approval-gated), warning on duplicate delivery risk.

---

### S5 — Shared dependency failure across unrelated flows

**Real basis.** July 28, August 8, August 17: `TranscoInvoke … Connection refused: hip-fwk-transco-cache.hip-cloud-esb.svc.cluster.local:8080` on SAPIT and KEPLER sales-order flows; each replay succeeded and "went into warning as per design".

**Fault.** The `hip-fwk-transco-cache` pod restarts (memory limit) during a busy window. For roughly 20 minutes every half-flow that calls transcoding fails, across projects that have nothing in common but that dependency.

| Time (UTC) | Source | Signal |
| --- | --- | --- |
| 00:20 | Splunk | `hip-fwk-transco-cache` pod restart 1 — informational, nobody looks (**first symptom**) |
| 00:55 | Sonar | `Unhandled Internal error … Connection refused: hip-fwk-transco-cache…:8080` on `EMEA_SAPIT_SALESORDER_01_ESB_V2` |
| 00:56–01:12 | HIPMON | `[AUTO]` alerts on 30+ half-flows across `SAPITCOMMON`, `KEPLER_NEXTGEN`, `PROCESSOUT`, `AMAZONCOMMON` — codes `IVK003`, `TEC01`, `GEN01` |
| 01:05 | Kafka | lag on four processing groups simultaneously |
| 01:10 | Apigee | 5xx across nine endpoints |
| 01:15 | ServiceNow | Six auto incidents from six different rules |

**Planted contradiction.** By the time anyone looks, the cache pod is Running and Ready, and every replay succeeds — which argues against the cache being the cause and toward "intermittent, flaky networking".

**Why this scenario earns its place.** The hardest noise-versus-cause separation. Thirty alerts, all correct, all describing symptoms on flows owned by different teams. The cause is a shared framework pod nobody alerts on. Alert *volume* and diagnostic *clarity* are unrelated quantities.

**Expected AI output.** First: transco-cache restart / unavailability window, supported by the identical error string, the restart record 35 minutes earlier, and failures ending when the pod became Ready. Second: AKS network / DNS blip, contradicted because other services in the namespace were unaffected. Ruled out: source-system faults (five unrelated sources). Recovery: replay all failed exchanges in one batch (approval-gated).

---

### Standing noise, in every scenario

Two real, recurring, unrelated alerts are interleaved and later dismissed in *Ruled out*: a Splunk `Linux Host: SGLORHIPQETLPC1 has more than 90% swap space usage over last 30 mins` and a QA-host `CAPLINERR001-Linux Host - FRHIPGQAMFTSI01 has more than 98% of CPU over last 1 h`. Both are non-prod and appear dozens of times per month in the real data.

## 4. Screen 1 — "Today" (the Sonar "Full Levels" dashboard)

The job of this screen is to make the room feel the problem in ten seconds. In v2 it is deliberately a reproduction of the dashboard the L1 actually stares at — it is what makes the audience trust the rest.

### Layout

**Header.** ServiceNow-style incident bar: `INC10790101 · P1 · <scenario one-liner> · Assigned: HIP Ops L1 · State: In Progress`. Beside it, the duplicate incident chips, with a note that they describe the same event.

**Centre — the Sonar dashboard.** Modelled on the "Full Levels" screenshots:

- Filter bar: KQL box, `Last 24 hours`, dropdown filters `Project · Exchange · Exchange.status · Level.status · Source · Destination · Object.name`, tab strip `… Levels · Full Levels · Mass Replays · Exchange Overview · Global Overview · Status Overview`.
- **KPI tiles, twice** (Exchanges row, HalfFlows row): `Exchanges` · `INPROGRESS` · `COMPLETE` · `WARNING` · `FAILED` · `REPLAYED` · `Failures %` · `Duration Avg` · `Duration Max`. Colours as on the real dashboard (blue / orange / green / yellow / red / grey). Values are computed from the generated exchange records, scaled to a realistic day (~975 k exchanges, ~2% failures) with the scenario's anomaly visible in `INPROGRESS`, `FAILED` and `Duration Max`.
- **Exchange table**: `@timestamp · exchange.status · project · exchange · exchange.id · halfflow.count · halfflow.missing · duration · source · destination · object.id · object.name · event.code · business.value · framework`. Status chips coloured as in the real dashboard. `halfflow.missing` shows `2/4` for stalled exchanges.
- **Traces table** for the focal exchange: `@timestamp · event.level · exchange · exchange.id · halfflow · halfflow.id · application · event.code · event.reason · message · business.value`, with `ERROR / ENTRYINFO / EXITINFO / INFO` chips.

**Right rail — the HIPMON alert stream.** Where v1's "147 alerts in 6 minutes" now lives: dense monospace rows, newest first, severity on the left edge, real subject formats:

```
10:06:14  HIPMON  IVK003   EMEA_SAPIT_SALESORDER_01_ESB_V2         Connection refused: transco-cache   P3
10:06:11  HIPMON  GEN01    EMEA_KEPLERNG_HEALTHCHECK_01_ESB        HTTP 503 from target                P3
10:05:58  KAFKA   KFK-LAG  …process-int-opsfin-01-neo-odes-large  lag 84,210                          P2
10:05:41  SONAR   HRLY     GLBL_MSTR_HLTH_CHK                      45,212 InProgress                   P2
10:05:33  SPLUNK  CAPLIN   FRHIPGQAMFTSI01                         CPU > 98% over 1 h                  P4
```

**Left rail — team channels.** From the real ownership split: `#hip-esb`, `#hip-mft`, `#hip-azure-platform`, `#hip-workato`, `#hip-kafka`, `#hip-apigee`, each with an unread badge. Nobody is wrong; everybody is looking at their own hop.

**Right panel — the L1 panel.** What L1 can actually do, and where it stops. Runbook search returns real-shaped KB articles (`KB0041802 · Replay failed exchange`, `KB0049334 · Repush file from MFT`, a generic consumer-lag article), none matching the cross-system symptom set, and one stale reference to a renamed half-flow. Actions taken: replay attempted, no effect (S2), or replay succeeded but failures recur (S5). State: escalated to L2, awaiting bridge.

**Footer — the bridge bar.** Live timer counting up from `01:14:22`, `6 engineers on bridge · Agreed cause: none · Customer impact: ongoing`. Leave it running through every AI screen.

### Details that make it feel real

- **Two pure-noise alerts** (see §3) interleaved with the real signal.
- **The buried first symptom** — the P4 heap / restart record hours earlier, visually indistinguishable from noise.
- **Duplicate incidents** — three or four, raised by different rules.
- **A stale runbook** — one candidate references a renamed half-flow.
- **Status honesty** — in S4 the stalled exchange is shown as `INPROGRESS`, exactly as the real dashboard would show it: unremarkable among hundreds of in-progress rows.

### Optional toggle: "Show all firing rules"

Expands a panel listing the 412 rules with the ones that fired highlighted. Use it only if challenged on coverage.

## 5. The transition

Unchanged from v1 in intent; retargeted at the new rows.

**Trigger.** A single prominent button on Screen 1: **Run AI correlation**.

**The animation, in order**

1. The HIPMON stream freezes; the Sonar table stops updating.
2. Alert rows belonging to this incident (the rule hits plus repeats) get a left-edge highlight. The two noise alerts get a dimmed treatment rather than disappearing. Stalled/failed exchange rows on the dashboard highlight too.
3. The highlighted rows **fly downward and stack**, collapsing into a single incident card. Each row shrinks into a small evidence chip attached to that card rather than vanishing.
4. The card expands into the Screen 2 layout.
5. Palette shifts from alarm colours to a calm slate, severity kept only as small accents.

**Total duration.** 2.5–4 seconds, with skip-on-second-click.

**Why the rows must not disappear.** If alerts vanish, the animation says *replaced*. If they compress into evidence, it says *consumed*. Same data, opposite message.

**Persistent artefacts after the transition.**

- Badge: `N of 412 rules fired · all N consumed as evidence · 0 suppressed`
- Badge: `2 alerts assessed as unrelated — see Ruled Out`
- The bridge timer, still counting up

**The layer diagram.** Always-visible stack in the corner:

```
  ┌──────────────────────────────────────┐
  │  AI correlation & reasoning  (new)   │
  ├──────────────────────────────────────┤
  │  HIPMON · Sonar · Splunk · Kafka     │
  │  Workato · MFT · ServiceNow · CHG    │  ← unchanged
  ├──────────────────────────────────────┤
  │  HIP production estate               │  ← unchanged
  └──────────────────────────────────────┘
```

## 6. Screen 2 — "With AI"

Seven panels. The governing rule: **observed facts and inferred causes never share a panel, and are styled differently** — facts on a light surface with a solid border, inferences on a tinted surface with a dashed border and a small `INFERRED` tag.

### Panel A — Incident header

`INC… · P1 · <one-liner>` with the duplicate incidents shown as merged chips. A one-sentence plain-English summary generated by the model: what broke, for which flows, since when. This sentence is what gets pasted into the bridge call.

### Panel B — Observed timeline (facts)

Vertical, earliest at top. Each event carries: timestamp (IST display, UTC on hover); source badge — `SONAR / HIPMON / SPLUNK / KAFKA / WORKATO / APIGEE / MFT / SERVICENOW / CHANGE`; the raw signal with a link to the underlying record; a `FIRST SYMPTOM` marker where relevant. Every row traces to a source file. Nothing generated, nothing inferred.

### Panel C — Candidate causes (inferred)

Two or three cards, ranked: cause statement; confidence band (`High` / `Moderate` / `Low`); **Supports** and **Contradicts** side by side, both populated; "What would change this".

### Panel D — Ruled out

What was considered and dismissed, and why. The two standing-noise alerts live here, plus the rejected alternative from the scenario.

### Panel E — Diagnostic checks

Ordered cheapest-and-most-decisive first: the query or command (Sonar filter, `kubectl` command, Kafka group describe, SFG search), the expected result if cause A, if cause B, and which hypothesis it settles.

### Panel F — Blast radius

Populated from the observed data, not estimated by the model: business flows affected, exchanges stuck or failed, zones, downstream systems degraded, business objects at risk (deliveries, ASNs, IDocs, files).

### Panel G — Recovery, behind the gate

Proposed action stated plainly — in this estate almost always a **replay**, a **repush**, a **listener/pod restart**, or a **rollback of a flow to the legacy route**. Risk note (e.g. duplicate delivery on replay), rollback path, and the action button **disabled** until an approval dialogue is completed with an approver name and reason. On approval a logged action record appears — who, when, what, on what evidence — followed by a verification step against observed signal.

### The closer — late evidence

**Inject delayed log**, per scenario (a late Sonar batch, a delayed SFG trailer, a vendor ticket update). The new event slots into the timeline at its true position, the diagnosis is recomputed, and a diff panel explains what changed and why. In the shipped data the late record answers the discriminating check (S1: the 04:52 batch really was one 3.1x message; S2: SAP holds 214 queued IDocs and the listener's threads are blocked), so **confidence firms up and a rival hypothesis is closed out** rather than the ranking swapping — a swap is shown only when the evidence genuinely supports one, and the rank-before/after shown is derived by code.

### Scenario switcher

Discreet control top right to move between S1–S5. Run S1 then S2 back to back; run S5 for the noise-versus-cause beat.

## 7. Data generator

One Python script, `generate.py`, producing a folder per scenario. Standard library only, deterministic under a fixed seed.

```
/data
  /s1-large-mapping-heap
    sonar-exchanges.ndjson
    kafka-lag.csv
    splunk-hosts.ndjson
    hipmon-alerts.json
    workato-jobs.json
    apigee-errors.json
    mft-transfers.csv
    servicenow-incidents.json
    change-records.json
    late-evidence.ndjson      ← withheld until the closer button
  /s2-pi7-listener-hang
  /s3-vendor-release
  /s4-stalled-exchange
  /s5-transco-cache
```

### Per-source formats

**`sonar-exchanges.ndjson`** — one JSON object per exchange/half-flow event, in the dashboard's own field names so it reads as real to anyone who has used Sonar: `@timestamp`, `exchange.status`, `event.level` (`ENTRYINFO`/`EXITINFO`/`INFO`/`ERROR`), `project`, `exchange`, `exchange.id`, `halfflow`, `halfflow.id`, `halfflow.count`, `halfflow.missing`, `application`, `event.code`, `event.reason`, `message`, `duration`, `source`, `destination`, `object.id`, `object.name`, `business.value`, `framework.version`. In S2 the inbound exchange count from PI7 must genuinely drop to zero; in S4 the stalled exchange must have no half-flow-2 event.

**`kafka-lag.csv`** — 15-second buckets, one row per processing-group topic: `timestamp,consumer_group,topic,partition,current_offset,log_end_offset,lag`. In S1 the target group's lag climbs; in S2 every group's lag stays zero.

**`splunk-hosts.ndjson`** — Linux host and pod metrics/alerts: heap %, restart counts, swap, CPU, FS. Includes the two standing-noise host alerts in every scenario.

**`hipmon-alerts.json`** — the auto-incident rule hits: rule id, subject in `[AUTO]|…` form, priority, error text, exchange.id.

**`workato-jobs.json`** — recipe job records with `Recipe function call failed` / `Failed to fetch ConfigForDocSending` errors (S3).

**`apigee-errors.json`** — per-minute aggregates: endpoint, status, count, p99, sample exchange ids.

**`mft-transfers.csv`** — `transfer_id,filename,source,target,start_time,end_time,status,bytes,declared_rows,actual_rows`. Timestamps deliberately lack an offset. In S4, `status` is SUCCESS while `declared_rows` and `actual_rows` disagree.

**`servicenow-incidents.json`** — number, opened_at, short_description, description, priority, assignment_group (`TECH FNDN - WW - HIP INCIDENT L2` style), state, parent, work_notes. Deliberately overlapping duplicates.

**`change-records.json`** — change number, type, implemented_at, component, description, implementer, approval state, rollback plan; plus vendor-notice records. Include six unrelated changes in the window as chaff.

### Generation rules

- **Exchange ids must actually thread** across Sonar, HIPMON, ServiceNow and MFT records.
- **Include 60 minutes of pre-incident baseline** in every file, so trend reasoning is supportable.
- **Plant the contradiction as a real record** — S1's lower inflow and zero lag elsewhere, S2's green health check, S3's succeeding YHIPDELVRY07 IDocs, S4's SUCCESS status, S5's Ready pod and successful replays.
- **Volume target.** 800–2,000 Sonar/HIPMON lines per scenario.
- **Dashboard block.** From the generated exchanges the build step derives the KPI tiles, ~40 exchange-table rows and ~15 focal-trace rows that Screen 1 displays.
- **Fixed seed.** Same output every run.
- **No personal data.** Invented ticket numbers (`INC1079xxxx` style), invented business object ids, no employee names.

## 8. The AI reasoning layer

### What is code and what is the model

**Deterministic code does:** parse the source formats into one event list; normalise timestamps to UTC and resolve the MFT no-offset case; resolve name aliases (project ↔ half-flow ↔ Kubernetes deployment); normalise severity to 1–4; thread exchange ids and group events into incident candidates; sort chronologically.

**Deterministic code also builds the evidence pack** the model sees: every distinct rule hit (repeats collapsed into one event stating the count and first/last time), the decisive baseline-versus-incident counts, and a bounded sample of context around them — roughly 120–300 events per scenario, never thousands of raw lines. The live server rebuilds the timeline from that pack using only the event ids the model chose, so the model cannot alter a timestamp, source or component.

**The model does one thing:** takes the evidence pack (rule hits and context, kept separate) and returns hypotheses, evidence weighting, check ordering and a recovery proposal. It understands; it does not detect.

The line to say out loud: *facts are assembled by code and are traceable to source records; only the reasoning about those facts is done by the model.*

### Prompt contract

The system prompt (see `prompts/analyst-system.md`) requires: causes as hypotheses with confidence bands; every hypothesis carrying supporting **and** contradicting evidence; every evidence item citing an `event_id` from the input; two to four hypotheses; checks ordered by decisiveness per unit of effort; recovery as proposal only; explicit reasoning about absent events (absence is evidence — this is what makes S2 and S4 work); JSON only.

**HIP-specific additions in v2:** the prompt is given the exchange model (half-flow counts, status meanings, what `INPROGRESS` at `2/4` implies), the fact that replay is the most common recovery and carries duplicate-delivery risk, and the rule that "no pile-up" is a distinct signature from "pile-up".

### Output schema

```json
{
  "incident_summary": "one sentence, plain English",
  "timeline": [{"event_id":"e-0001","ts":"...","source":"SONAR","component":"...","description":"...","is_first_symptom":true}],
  "hypotheses": [{"rank":1,"cause":"...","confidence":"High|Moderate|Low",
    "supports":[{"event_id":"e-0004","why":"..."}],
    "contradicts":[{"event_id":"e-0019","why":"..."}],
    "what_would_change_this":"..."}],
  "ruled_out": [{"candidate":"...","reason":"..."}],
  "checks": [{"order":1,"action":"...","command":"...","if_result_a":"...","if_result_b":"...","effort":"low"}],
  "blast_radius": {"business_flows":["..."],"exchanges_stuck":45212,"zones":["EMEA"],"downstream_degraded":["..."],"business_objects_at_risk":"..."},
  "recovery": {"proposal":"...","risk":"...","rollback":"...","requires_approval":true},
  "post_incident_note": "draft ServiceNow work note, in the #01 Analysis/Root cause · #02 Resolution/Flow state · #03 Doc used · #04 Related records format"
}
```

The `post_incident_note` follows the close-note convention the real incidents already use, so the output can be pasted straight into ServiceNow.

### Re-run on late evidence

Second call, same schema, with the original event list plus the late event and the previous output; ask for what changed and why; render as the diff panel. Do not compute the diff in code.

### Validation before you trust it

Run all five scenarios and check by hand:

1. Every cited `event_id` exists in the input (a 20-line validator does this in `build_bundles.py`).
2. Every hypothesis has a non-empty `contradicts` array.
3. **S1 and S2 produce different first-ordered checks** — heap/payload-size for S1, inbound-exchange-count for S2.
4. **S5 produces one shared-cause hypothesis**, not thirty per-flow ones.

## 9. Architecture and stack

Deliberately boring. Every hour on infrastructure is an hour not spent on the reasoning layer.

- **Frontend:** single-page React + Tailwind + Vite. No router, no state library.
- **Data:** static JSON committed under `app/src/data/<slug>/`, loaded at startup.
- **AI calls:** pre-computed cached responses shipped as JSON, plus a thin local server (Azure AI Foundry endpoint, key in `server/.env`) for one live-call scenario.
- **Normaliser:** Python pre-pass emitting `normalised-events.json`.
- **Deployment:** runs locally; publishable as a self-contained page.

### Why no real infrastructure

A real Kafka cluster proves Kafka works. The question on the table is whether the reasoning is good, and synthetic signals answer it exactly as well. The natural second step is retrospective validation against real past P1s — see §12.

### File layout

```
/generator      generate.py, scenarios.py
/normaliser     normalise.py, cmdb-aliases.json
/authoring      hand-authored diagnosis + late-evidence per scenario
/scripts        build_alert_feed.py (HIPMON stream + Sonar dashboard block), build_bundles.py
/prompts        analyst-system.md, late-evidence.md
/app/src        screens/AlertFloor.tsx (Sonar dashboard), screens/AiView.tsx, panels/*, components/*, lib/*
/server         live-call server
/Auto Alerts    raw ops exports — git-ignored, never committed
```

### AI-first, with a fallback — not a cache-first demo

- **S1, S2 (curated):** a hand-authored diagnosis ships in the bundle and is the default, so the main story never depends on a network call. A live toggle runs the real model on the same evidence.
- **S3, S4, S5 (AI-live):** no cached answer exists. The live call starts in the background as soon as the scenario is on screen, so it is usually finished before the presenter clicks *Run AI correlation*; otherwise Screen 2 shows an honest loading state with elapsed time.
- **Fallback.** Every successful live result is written to `server/cache/` and replayed if a later call fails, with a visible "replayed from last successful live run" note. If there is neither a live answer nor a saved one, the screen says so — it never shows invented content.
- **Guardrails on live output** (in the server, not the model): every cited `event_id` must exist in the pack (one automatic retry with the errors fed back, then uncitable items are dropped); the timeline is rebuilt from the pack; `requires_approval` is forced true; rank-before/after in the late-evidence diff is derived by code.
- **Latency is the live risk.** gpt-5 with reasoning can take a minute or more on a 200-event pack. Mitigations: background prefetch, `FOUNDRY_REASONING_EFFORT` tunable in `server/.env`, and run one live pass in rehearsal so the saved fallback exists before the room does.

### Visual design

- **Screen 1:** Sonar/Kibana-faithful — KPI tiles, table density, chips as in the screenshots — with monospace, tight spacing, alarm colours. Deliberately hard to read.
- **Screen 2:** generous spacing, clear hierarchy, calm slate palette, colour reserved for the fact/inference distinction and severity accents.
- **Fact surfaces:** light background, solid border. **Inference surfaces:** tinted background, dashed border, `INFERRED` tag.
- One accent colour on Screen 2. Its credibility comes from looking restrained.

## 10. Three-day build order

Principle: **the reasoning layer must work before any pixel is styled.** If the prompt is not producing clean output by the end of Day 1, cut to three scenarios rather than compressing Day 2.

### Day 1 — data and reasoning

- **Scenario specs as data** (`scenarios.py`) — from §3, including exchange ids, half-flow names and error strings from the real vocabulary.
- **Generator** — spot-check by hand: S1 lag climbing while every other group is zero; S2 inbound count actually zero and lag actually zero; S3 the YHIPDELVRY07 successes present; S4 row counts disagree and half-flow 2 absent; S5 the pod restart record present 35 minutes before the first error.
- **Normaliser** — alias map, MFT no-offset time, severity, exchange-id threading.
- **The prompt. This is the POC.** Expect 6–10 iterations. Failure modes in the order they usually appear: empty `contradicts`; unearned certainty; checks ordered by thoroughness; citations to non-existent event ids; S2 diagnosed as S1; S5 diagnosed as thirty separate problems.
- **End-of-day gate.** Five valid JSON outputs, all citations resolving, S1 and S2 genuinely differing.

### Day 2 — the application

- **Screen 1** — the Sonar dashboard reproduction (KPI tiles, exchange table, traces) plus HIPMON stream, channels, L1 panel, bridge timer. Density is the point.
- **Screen 2 skeleton** — seven panels, real data, minimal styling. Facts/inference separation first.
- **Evidence columns and approval gate.**
- **The transition.** Budget properly; timebox to 90 minutes.
- **Late-evidence closer.**
- **End-of-day gate.** Full path clickable on S1.

### Day 3 — hardening and rehearsal

All five scenarios wired; visual pass; break it deliberately (wrong-order clicks, double-click the transition, switch scenarios mid-animation, approve twice); 5-slide closing deck; rehearse three times out loud.

### Working with Claude Code

- Give it this whole document as context at the start of each session.
- One session per component: generator, normaliser, Screen 1, Screen 2, transition.
- Let it write the generator and normaliser almost unsupervised.
- Do **not** delegate the prompt iteration.
- Build the normaliser as plain code even if it is tempting to let the model parse.

## 11. Demo run sheet — 12 minutes

No slides until minute 10. Open on Screen 1, already live, before anyone has settled. (Run S1 as the main case; S2 second; S5 if the room wants the noise story; S3/S4 in Q&A.)

**0:00 — Silence, 10 seconds.** Let them look at the Sonar dashboard. Then: *"This is your own dashboard, on a bad morning. Every alert is correct. Three duplicate incidents. Nobody in this picture knows what broke."*

**0:30 — The L1 dead end.** Walk the right panel. Runbook search returns generic articles, one renamed. Replay tried, no effect. Escalated. Point at the bridge timer.

**1:30 — Name the gap.** *"Detection took ninety seconds. Diagnosis is still running. In your last three months the median auto-raised incident took six and a half hours to resolve."*

**2:00 — Click Run AI correlation.** Say nothing over the animation. *"Nothing was suppressed. Every rule hit is in there as evidence."*

**2:30 — The timeline.** Stop on the first symptom: *"This fired hours before anyone noticed. It was a P4. It is the first symptom."* Then: *"Every row traces to a source record. This panel contains no inference."*

**4:00 — The causes.** Read the top hypothesis, then move to Contradicts: *"It argues against itself. Inflow was lower than last Thursday, and every other group has zero lag — so this is payload size, not load."*

**5:00 — Ruled out.** *"Two of these alerts were unrelated. Here is why."*

**5:30 — Checks.** *"Ordered by decisiveness. The first is one query and it settles between the top two causes."*

**6:00 — Approval gate.** Show the proposal (replay / move / restart), the disabled button, complete the dialogue, show the logged record. *"Nothing executes without a named human."*

**7:00 — Switch to S2.** *"Same message from the warehouse — deliveries not arriving. Watch the dashboard."* Show: no pile-up, zero lag, flat heap, zero inbound. *"A bridge call would reach for the S1 playbook. Different cause, different first check."* Give it the full 90 seconds.

**8:30 — The closer.** Click **Inject delayed log**. Let the confidence move and the rival close out. *"A record arrived late. The diagnosis moved from moderate to high, one alternative is now eliminated, and it says which piece of evidence did that. How long would that have taken on the call?"*

**9:30 — Stop clicking.** Five slides.

**11:00 — Questions.**

### Objection handling

**"We already have 400 rules."** Agree immediately. *"You do, and they all fired correctly — that is the first screen. The rules are the sensors. This is the analyst."* Then the layer diagram. Then: *"On your last cross-system P1, how long between first alert and agreed cause?"*

**"Can we trust the AI?"** *"You are not asked to. It cannot execute anything. It proposes, cites its evidence, shows what argues against its own conclusion, and a named human approves."*

**"This is synthetic data."** *"It is — but built from three months of your own incident patterns: the same error strings, the same half-flow naming, the same replay-as-recovery. What is on trial is the reasoning. Give us a real past P1 — the alert list and the timeline someone wrote afterwards — and we will run it against that."*

**"What about rule maintenance burden?"** Do not oversell. This does not reduce rule count; it changes what happens after they fire.

**"How long to make it real?"** Be honest about the dependencies: exchange-id coverage, timestamp consistency, CMDB-to-runtime name mapping.

## 12. Risks, cut lines, and what comes after

### Risks in the build

| Risk | Mitigation |
| --- | --- |
| Prompt iteration overruns Day 1 | Hard gate. Cut to three scenarios (S1, S2, S5) rather than compressing Day 2. |
| Sonar dashboard reproduction eats Day 2 | Tiles and table first; traces panel last. A static-looking table beats an unfinished one. |
| S1 and S2 produce the same diagnosis | Make the "no pile-up" evidence salient in normalised event text (inbound count 0, lag 0), not hinted in the prompt. |
| S5 explodes into thirty hypotheses | Validation check 4; feed the model exchange-error strings grouped by identical `event.reason`. |
| Live call fails or is slow in the room | Prefetch on scenario select; server-side fallback to the last successful live run; run every AI-live scenario once in rehearsal to seed it. |
| AI-live output is weak or mis-cites | Server-side citation validation with one retry; evidence pack built by code so the decisive fact is a single explicit event; S3–S5 spot-checked against the intended cheapest-decisive-check evidence. |
| Hallucinated event citations | Validator over every cached response before the demo. |
| Real data leaks into the repo | `/Auto Alerts/` is git-ignored; generator uses invented ids and no names. |

### Cut lines, in order

1. S3 (vendor release) — most dependent on a non-log source
2. S4 (stalled exchange) — most distinctive, cut reluctantly
3. Blast radius panel
4. The collapse animation, down to a crossfade

(The live path is no longer a cut line: S3–S5 exist only as live AI. If live is unusable, present S1 and S2 only.)

**Never cut:** S1 and S2 as a pair, S5 as the noise story, the Contradicts column, the Ruled Out panel, the approval gate, the late-evidence closer.

### Honest limitations to state rather than hide

- Output quality depends on exchange-id discipline, timestamp consistency and CMDB accuracy. Where those are weak, the timeline degrades.
- This does not reduce the number of rules or their maintenance burden.
- Novel failure modes with no precedent in the signal data will produce weaker hypotheses.
- The L1 role changes from "check and escalate" to "verify and approve" — an organisational conversation, better raised by you than discovered by them.
- The scenarios are derived from patterns in real incidents, not replays of them; accuracy on real incidents is exactly what the retrospective step below measures.

### What a real deployment needs

1. **Signal readiness assessment** — exchange-id coverage, timestamp consistency, CMDB-to-runtime name mapping. One to two weeks; make-or-break.
2. **Read-only connectors** — Sonar/ELK, Kafka metrics, Splunk, Workato, Apigee, MFT/SFG, ServiceNow, change management.
3. **Retrospective validation** — run against 20–30 historical P1/P2s and compare with what the team concluded. The June–August export already contains the ground truth for this: 27 incidents at Critical/Major with written root causes.
4. **Shadow mode** — alongside live incidents, changes nothing.
5. **Approval workflow integration** — ServiceNow approval records, RBAC, tied to the replay/repush/restart action types that dominate real recoveries.
6. **Feedback loop** — post-incident learning closing back into hypothesis quality, using the existing `#01–#04` close-note structure.

### The strongest next step to propose

Ask for one real past P1: the alert list, the eventual timeline, and the post-incident report. The three-month export already shows there are plenty (the 27 Critical/Major incidents). Run the system against one and compare. It costs them nothing, requires no access to production, and turns "does this work" into "how well does it work on ours."
