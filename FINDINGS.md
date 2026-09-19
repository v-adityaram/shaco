# Findings — what we did, why, what worked, what didn't

Session of 2026-09-19. Covers the move from an invented demo estate to one grounded in real HIP Ops data, and the shift to an AI-first design where the AI sits on top of the existing rules.

## 1. Why we changed anything

The first version demonstrated the idea on an invented retail estate ("Meridian Retail"). It told a good story, but nothing on screen looked like the client's real floor, so a HIP Ops reviewer would notice within seconds that it was synthetic.

Two inputs made a better version possible:

- **Three months of real incident inflow** (June, July, August 2026 — 3,118 incidents) with classification, close codes, teams and trends.
- **Screenshots of the live Sonar "Full Levels" Kibana dashboard**, showing the exact layout, fields and status vocabulary the L1 team uses.

Then a second instruction reshaped the design: *only use a small part for showcase and fallback; everything else should be produced by the AI; and the AI must sit on top of the client's rules — understand, not detect.*

## 2. What we did

| Area | Change | Why |
| --- | --- | --- |
| Plan | Rewritten as v2 with real-data calibration and the governing principle (AI understands, never detects) | The plan is the spec the code is built from, so it had to change first |
| Estate | Replaced retail with HIP: exchanges, half-flows, processing groups, HIPMON, Sonar, Splunk, Workato, MFT | Every name, error string and recovery step is now something the audience has seen |
| Scenarios | Five, each from a real incident family (see §3) | Grounded in what actually breaks, with a planted contradiction each |
| Screen 1 | Reproduction of the Sonar dashboard (KPI tiles, exchange table, traces) plus a HIPMON alert stream | The audience trusts the rest if the first screen is their own dashboard |
| Data pipeline | Generator, normaliser, alert-feed and bundle builder rewritten | Deterministic, seeded, citation-validating |
| Evidence pack | Code builds a 120–260 event pack per scenario from rule hits plus retrieved context | The model can't be handed thousands of raw lines, and "facts assembled by code" stays true |
| AI split | S1 and S2 hand-authored (showcase and fallback); S3, S4, S5 live-AI only | Matches the instruction: only a small part is scripted |
| Server | Citation validation with one retry, JSON-parse retry, timeline rebuilt from the pack, on-disk fallback of the last good live run | Live output must never be trusted blindly or fabricated |
| Prompt | Rules-on-top framing, plus scoping rules added after a live failure (see §5) | See §5 |
| Privacy | `/Auto Alerts/` git-ignored; generated data uses invented ids and no names | The exports contain employee names and ticket text |

## 3. The five scenarios and their real basis

| Slug | Scenario | Real basis | Mode |
| --- | --- | --- | --- |
| s1-large-mapping-heap | Oversized ASN payloads exhaust a processing group's heap | June 4–5: 45k+ exchanges INPROGRESS, ASNs missing in S4 | Curated |
| s2-pi7-listener-hang | PI7 IDoc listener hangs; nothing enters HIP | June 2: SAP-to-warehouse deliveries stopped, replay did nothing | Curated |
| s3-vendor-release | Vendor platform push breaks IDoc outbound to SAP | July 20 and June 9: `Failed to fetch ConfigForDocSending` | AI-live |
| s4-stalled-exchange | Exchange stalls INPROGRESS after a patching window | June 10, June 15: file never processed, database locked hours later | AI-live |
| s5-transco-cache | Shared cache pod fails behind 30+ alerts | July 28, Aug 8, Aug 17: `Connection refused` on the transco cache | AI-live |

S1 and S2 are a deliberate pair: the same business symptom ("deliveries not arriving") with opposite signatures — a pile-up versus no inflow at all — and different first checks.

## 4. What worked

- **The pipeline is deterministic.** Two full runs produced identical hashes across all generated data.
- **The decisive evidence is real data, not narration.** 44 checks against the raw files passed (for example S2's inbound count is genuinely zero, S4's file row counts genuinely disagree, S5's restart precedes the first error by 35 minutes).
- **Curated diagnoses validate.** S1 and S2 resolve every citation (19 and 17) inside the evidence pack, and every hypothesis carries contradicting evidence.
- **Live AI reached the right cause on all three AI-only scenarios** after the prompt fix: cache restart for S5, vendor release regression for S3 (citing the vendor notice), post-patching stall for S4 (citing the missing half-flow).
- **Guardrails held.** The timeline is rebuilt from the pack by code, `requires_approval` is forced true, and rank-before/after in the late-evidence diff comes from code.
- **The UI works with real bundles.** Typecheck, lint and build pass. In a real browser, the curated S1 path and the AI-live S5 path both rendered, with no console errors. The background call had finished by the time the presenter clicked.
- **The fallback path is real.** Successful live runs are saved to `server/cache/` and replayed if a later call fails, with a visible note.

## 5. What didn't work, and what we did about it

| Problem | Evidence | Fix | Status |
| --- | --- | --- | --- |
| **The AI promoted an unrelated alert to a hypothesis** (S5, first live run) | It ranked a "Plant field missing" mapping error as the second cause and proposed rolling back an unrelated change | Prompt rules: hypotheses are rival explanations of the *same* incident; unrelated concurrent problems go to Ruled out; a change is a cause only if linked in time and component. No scenario answer was hinted | Fixed; re-run correct |
| **The AI missed the first symptom** (S5, first run) | It marked the first failing exchange, not the cache pod restart 35 minutes earlier | Prompt rule: the first symptom is the earliest event belonging to the incident, including precursors on a shared dependency | Fixed |
| **Live latency was 124 s** | Measured on S5 at default reasoning effort | Reasoning effort set to low: 68–77 s. Plus background prefetch when a scenario is shown | Improved, still slow |
| **Late-evidence call failed on malformed JSON** | HTTP 502, JSON syntax error from the model | Server now retries once when JSON does not parse | Fixed; re-run worked |
| **The bridge bar said "Agreed cause:" next to the AI's guess** | Screenshot review | Now reads "Agreed cause: none · AI-proposed (not yet agreed)" | Fixed |
| **A missing `failurePct` would crash Screen 1** | Flagged by the UI agent | Guarded with a default | Fixed |
| **Neither curated scenario has a genuine ranking flip** | The evidence supports one leading cause from the start in both; forcing a swap would mean authoring a deliberately worse first answer | The closer now shows confidence firming and a rival closed out. The plan's run sheet was changed to say so | **Accepted trade-off** — the plan originally promised a flip |

## 6. Known limitations (not fixed)

- **Live latency is still about 70–80 s** per call. Prefetch hides it only if the presenter lingers on Screen 1. Run each AI-only scenario once before a demo so the fallback exists.
- **`server/cache/` is git-ignored**, so a fresh clone has no fallbacks for S3–S5 until each has been run once.
- **The AI sometimes cites the same event as both support and contradiction** for one hypothesis (seen on S3 and S5). Not wrong, but sloppy; the validator does not flag it.
- **Some checks are unverified visually:** the collapse animation frames, the live-error and Retry path, and the "replayed from server cache" banner were coded but not exercised.
- **The app bundle is large** because bundle data ships inside it. Fine locally; would want code-splitting to publish.
- **A small amount of accidental correlation exists in the synthetic data** (for example an unrelated change followed by unrelated alerts on the same component). The AI handled it after the prompt fix, but it shows that generated chaff can create plausible decoys.
- **The scenarios are patterns from real incidents, not replays.** True accuracy needs the retrospective test described in the plan: run the system on real past P1s and compare with what the team concluded.

## 7. Decisions worth remembering

1. **The AI understands; it does not detect.** Its input is rule output plus retrieved context. Where no rule fired, that absence is a finding.
2. **Counts, timelines and rank changes are computed by code**, not stated by the model.
3. **Nothing is fabricated to fill a gap.** If neither a live answer nor a saved one exists, the screen says so.
4. **Honest over impressive.** We did not stage a ranking flip the data does not support.
5. **Real data stays out of the repo.** Raw exports are git-ignored; generated data is invented.

## 8. Where things are

- Plan: `Incident Response AI — POC Implementation Plan.md`
- Generator, normaliser, scripts: `generator/`, `normaliser/`, `scripts/`
- Curated diagnoses: `authoring/`
- Analyst prompts: `prompts/`
- Live server and fallback cache: `server/`
- App: `app/`
