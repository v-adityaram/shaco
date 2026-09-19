# Incident Response AI — POC frontend

React + Vite + Tailwind + TypeScript. Grounded on the HIP (Hybrid Integration Platform) ops estate.

- **Screen 1 (`AlertFloor`)** — reproduction of the Sonar "Full Levels" Kibana dashboard (KPI tiles, exchange table, traces), the HIPMON alert stream, the six HIP team channels, the L1 runbook panel and the bridge timer. Fed by `bundle.dashboard` and `bundle.alertRows`.
- **Screen 2 (`AiView`)** — incident header, observed timeline (facts), candidate causes / ruled out / checks (inferences), blast radius, approval-gated recovery, late-evidence closer.
- Light/dark toggle on both screens; scenario switcher on both.

## Data
`src/data/<slug>/bundle.json` per scenario (`s1-large-mapping-heap`, `s2-pi7-listener-hang`, `s3-vendor-release`, `s4-stalled-exchange`, `s5-transco-cache`), produced by `scripts/build_bundles.py`. Types are in `src/lib/types.ts`. Missing bundles/fields are logged to the console rather than crashing.

- `meta.mode = 'curated'` (S1, S2): cached diagnosis in the bundle; the "Run live" toggle can swap in a live result.
- `meta.mode = 'ai-live'` (S3-S5): no cached diagnosis. The live call (`POST /api/diagnose`, proxied by Vite to `:8787`) starts as soon as the scenario is shown on Screen 1 and is memoised per slug (`src/lib/liveCache.ts`).

## Scripts
`npm run dev`, `npm run build` (typecheck + build), `npm run lint`.
