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
| AI split | **S5 hand-authored (the one stored scenario)**; S1 to S4 live-AI only (was S1 and S2 stored; changed in round 3) | Matches the instruction: only a small part is scripted, and one stored scenario is easier to explain than two |
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

## 9. Round 2 — S3 gave a different, worse answer on a later run

**What happened.** A later live run of S3 ranked "problem inside SAP" first (High) and the vendor release second (Low), the opposite of an earlier run. It also reported 493 "stuck / failed" exchanges when that figure was the *in-progress* count (the failed count in the same record was 279), and it listed the same evidence on both sides of a hypothesis.

**Root cause.** Partly the model, partly our evidence. The generator wrote "(Workato recipe ...)" into each failing exchange's log message, but the normaliser dropped that text and kept only the error reason. The model therefore saw failing half-flows named `EURO_RFCT_...` with no sign they call Workato, and reasonably concluded they were separate ESB flows that a Workato-only regression could not explain. The data contradicted itself.

**Fixes.**
| Fix | Where |
| --- | --- |
| Failing Sonar lines (and the grouped summaries) now state when the failing step is a Workato recipe call: 167 of 260 pack events carry it | `normaliser/normalise.py` |
| New prompt rules: count only the incident's own flows and name the status; cite each event on one side only; use High confidence only when the discriminating check is done; mark exactly one first symptom | `prompts/analyst-system.md` |
| Server flags a blast-radius number that appears in no evidence event, flags events cited on both sides, and keeps only the earliest first symptom | `server/index.js` |

**Result.** Two clean live runs of S3: both ranked the vendor release first at Moderate with the SAP-side cause second at Low, both marked the single vendor notice as the first symptom, both reported 318 (the cumulative failed count, present in the evidence), and neither triggered a warning. The saved fallback now holds a correct answer.

**New finding: rate limiting.** Firing three live calls at once produced a 429 "rate limit exceeded" from the model service on one of them; the server correctly replayed the saved fallback. In the room, do not switch between AI-only scenarios quickly, since each switch starts a live call.

**Still true.** Two runs is a small sample. gpt-5 gives no way to fix the random seed, so some run-to-run variation remains; the server-side checks and the fallback exist for that reason.

## 10. Round 3 — S5 is now the only stored scenario

**Change.** S1 and S2 used to ship a hand-written diagnosis; S3 to S5 were live. It is now **S5 stored, S1 to S4 live**. The retired S1 and S2 answers are archived in `authoring/unused/`.

**Why.** Two behaviours (two stored, three live) were harder to explain than one stored and four live, and the original reason for storing S1 and S2 was protection: they are the "never cut" pair, and the run sheet leads with them. That protection is still available as the saved fallback of the last live run.

**What we tested before switching (S1 and S2 had never been run live).**
| Scenario | Live result |
| --- | --- |
| S1 | Correct: payload growth first (Moderate), leak second (Low), first symptom the 05:10 heap alert, 82,900 quoted correctly, no warnings. Late evidence firmed it to High. |
| S2 | Not confused with S1 (good), but it **hedges**: "the SAP hub stopped sending" ranked first and "the listener lost its connection" second, both Moderate. The stored answer had put the listener first. The ambiguity is real and is exactly what the late record resolves. |

**Consequences to know.**
- The two most important scenarios now depend on the live model (about 75 s per call, and run-to-run variation). Run each once before a demo so a saved fallback exists.
- Because S2's first answer can hedge, its late-evidence closer can produce a **genuine ranking flip live**, which the stored answers could not.
- With four live scenarios the model service rate-limits bursts, so the server now queues calls (two at a time) and retries a 429 after waiting instead of falling straight back to the saved answer.

## 11. Round 4 — Live mode (real June replay), Global Overview panel, first production deploy

Session of 2026-09-21. Two feature additions, then a real deployment onto a shared VM. Everything here is pushed to `hip-real-data-ai-first` (currently at `6ea74ab`) except the one open item at the end.

### What we built

**Live mode** (`app/src/screens/LiveFloor.tsx`, `app/src/lib/liveIncidents.ts`, `scripts/extract_live_incidents.py`, `server/index.js`'s `/api/live-window`). Replays a real 48h window (June 9–11, chosen for containing two real linked incident clusters) of the actual June 2026 HIP incident export, redacted and re-anchored to "now" so it plays out live on a simulated clock (240× by default) instead of on the real June date.

- **Redaction is at extraction time, not display time.** `extract_live_incidents.py` drops `Caller`/`Assigned to`/`Updated by`/`Resolved by` entirely before the file ever gets written; nothing downstream can leak a name because the name is never in the data.
- **No raw telemetry exists for real incidents** — the June export is ServiceNow ticket data only (subject, description, classification, close notes, timestamps). Live mode's AI evidence is built from that ticket text directly; we did not fabricate synthetic logs to sit behind it. This is a real, disclosed constraint, not a bug.
- **Incident selection.** Users can tick individual incidents, "select linked cluster" (follows the real `parent_incident` field — confirmed this is genuine ServiceNow triage data, not something we invented: e.g. three separately-auto-raised `Global Daily Flow Failure Report` tickets for three different country exchanges, hand-linked by a real triager to one parent), or leave nothing ticked to send everything arrived so far. This required moving off the shared `ensureDiagnosis`/`useLiveState` cache (keyed only by scenario slug, so it can't be forced to re-run against a different hand-picked event subset) to a locally-managed, always-rerunnable call in the screen itself.

**Global Overview panel** (`SonarDashboardView` → new `GlobalOverviewView` in `app/src/components/SonarDashboard.tsx`, generation in `scripts/build_alert_feed.py`). Reproduces the real "Global Daily Flow Failure Report" — a Critical Flows table ranked by failure rate (red-gradient shaded, same as the real one) plus Failure Rate by Zone/Application tiles.

- Only built for S1–S5 (synthetic), not Live mode — the real Failure Report needs raw exchange-level pass/fail *volume* (how many times did this exchange run today, how many failed), which the ticket export doesn't have. Checked the export's other sheets (`Platform`, `By Team`, `By Day`, `Classification`, `1 Year Trends`) first to be sure; none of them have it either. Didn't fabricate a fake version for Live mode.
- Every number in the panel is a **disaggregation of the already-computed `exchangeKpis` totals** (`build_critical_flows()` etc.), never a second, contradicting figure — same principle as the rest of the pipeline ("counts are computed by code, not stated by the model"), just applied to a finer partition of a count that already existed.

### Deploying to the shared VM (RapidBuildFactory, 104.211.224.38)

First real deployment of this app, onto a box that already runs two other live projects (`telecom-assistant`, `GAF Customer Service AI`) behind one nginx reverse proxy, landing page at `/home/`. Incident Response AI already had a slot prepared: nginx `location /incident/` (alias to `/var/www/incident-ai/`, basic-auth protected) and `location /incident/api/` (proxy to `127.0.0.1:8002`), plus a `incident-ai.service` systemd unit — someone had set this up in advance, just never deployed code to it.

**What worked:**
- The earlier "harden for public use" pass on `server/index.js` (rate limiting, concurrency cap, request-size cap, `ALLOWED_SLUGS` whitelist) meant zero server code changes were needed just to go public — it was already safe to expose.
- `VITE_BASE=/incident/ npm run build` produces a correctly-relocated build with no other changes, because `app/src/lib/ai.ts` already computes its API base from `import.meta.env.BASE_URL` rather than a hardcoded `/api`.
- `/api/live-window` reads its file fresh on every request (not cached at server startup), so running the extraction script never requires a service restart — only actual `server/index.js` changes do.
- Retrofitting a non-git deployment directory into a real checkout is safe with `git init && git remote add origin ... && git fetch && git checkout -f -b <branch> origin/<branch>` — it only overwrites paths git actually tracks, so secrets/real-data/`node_modules` (never tracked) are untouched by construction, no `.gitignore` awareness needed before the fact.

**What didn't work / gotchas for next time:**
- The deployment directory was **not a git repo** — someone had `scp`/`rsync`'d files there directly rather than cloning. `git pull` is meaningless until you `git init` + add the remote + fetch first; wasted a round-trip discovering this.
- `node`/`npm` are **not on the VM's system `PATH`** — the systemd service runs a self-contained Node at `/home/azureuser/incident-ai/node/bin/node`. Needs `export PATH="/home/azureuser/incident-ai/node/bin:$PATH"` before any npm command, every session.
- Fresh checkout means no `node_modules` (gitignored, obviously) — `npm run build` fails on `tsc: not found` until `npm install` runs first. Easy to forget when the source tree looks otherwise complete.
- **Port 22 (SSH) is closed at the network level** on this VM (Azure NSG, near-certainly) — confirmed by direct-connection timeout both from outside and from the user's own machine. The only working remote shell is Azure's own web console (Serial Console / Run Command), which is not SSH and doesn't support `scp`. This fully blocked transferring the real June Excel export onto the VM — **Live mode's data extraction is not done on production**, only the feature/code is deployed there (confirmed: it correctly shows "no live window extracted" rather than crashing or faking data).
- Classic Windows `scp` + drive-letter gotcha: `scp` parses `C:\Users\...` as `host:path` and tries to resolve "C" as a hostname. Fix is `cd` into the folder first so the local argument has no leading drive-letter colon.
- Several relay round-trips were wasted on **terminal confusion** — commands meant for the user's local PowerShell landing in the VM's browser-console tab instead (same-looking shell prompt style, easy to lose track of which window has focus). Worth having the user run a throwaway sanity command (`pwd` / `dir`) before any multi-step sequence to confirm which shell is active.
- **Considered and explicitly rejected:** pushing the real Excel export to GitHub so the VM could `git pull` it. Even on a private repo this would permanently embed real employee/ticket data in git history — directly contradicts this project's own stated privacy rule (§7 above, and `.gitignore`).

**Open item for next session:** Live mode's real data is still not set up on the production VM. Two viable, undone paths: (a) open NSG port 22 inbound, scoped to the operator's IP only, then `scp` normally; (b) stage the Excel behind a short-lived private link (OneDrive/SharePoint share, or an Azure Blob SAS URL) and `curl`/`wget` it from *inside* the VM's web console, which does have working outbound internet (confirmed — `git clone`, `apt install` all worked fine from there). Neither was executed; the user paused here rather than choose.
