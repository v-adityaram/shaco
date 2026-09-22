# Running the demo on synthetic data (VM runbook)

The demo runs on **synthetic data** by default: the same shape, timing and relationships as the real
scenarios and the Live window, with every production name replaced. As of the "Switch S1-S5 and Live
mode to fully synthetic data" commit, this is what a fresh `git clone` and deploy already ships --
the steps below are for redeploying, for regenerating the synthetic set from a newer real export, and
for the rare case of switching back to real data for a specific check.

The `synthetic-data/` working folder itself (the intermediate output of the generator scripts) is
**not in git** -- only the two places the app actually reads from (`app/src/data/` and
`server/live-data/june-window.json`) are committed.

## Where the files come from

Generated on the machine that holds the real exports:

    python scripts/synthesize_all.py        # writes synthetic-data/ (git-ignored)

Copied to the VM at `~/incident-ai/synthetic-data/` (owner-only, outside every web root):

    synthetic-data/
      app-data/<slug>/{bundle,alert-feed}.json   scenarios S1-S5 (every screen except Live)
      live/june-window.synthetic.json            Live mode window
      authoring/  normaliser/                    reference copies (not needed at runtime)
      README.md                                  what was replaced and what was kept

## What runs where

| Part | How the app gets its data | So switching needs |
|---|---|---|
| Live mode | the server reads `server/live-data/june-window.json` on every request | a file copy only, **no restart, no rebuild** |
| Scenarios S1-S5 (Alert Floor, Sonar dashboard, Global Overview, AI view) | JSON is compiled into the web build from `app/src/data/<slug>/` | copy the files, then **rebuild** the web app |

## Switch the VM to synthetic data

Run as the app user on the VM:

```bash
export PATH="$HOME/incident-ai/node/bin:$PATH"     # node/npm are not on the system PATH here
cd ~/incident-ai
git pull --ff-only                                   # get this runbook and any newer code

# 0. keep the real data so you can switch back
STAMP=$(date +%Y%m%d-%H%M%S); mkdir -p backups/real-data-$STAMP
cp -r app/src/data backups/real-data-$STAMP/app-data
[ -f server/live-data/june-window.json ] && cp server/live-data/june-window.json backups/real-data-$STAMP/

# 1. Live mode (takes effect immediately)
mkdir -p server/live-data
cp synthetic-data/live/june-window.synthetic.json server/live-data/june-window.json

# 2. Scenarios S1-S5: overwrite the compiled-in data, keeping the same slugs
for d in synthetic-data/app-data/*/; do
  slug=$(basename "$d"); cp "$d"/*.json "app/src/data/$slug/"
done

# 3. Rebuild the web app under the /incident/ sub-path and publish it
cd app
[ -d node_modules ] || npm install                   # a fresh checkout has no node_modules
VITE_BASE=/incident/ npm run build
rsync -a --delete dist/. /var/www/incident-ai/    # mirror, don't overlay -- see note below
cd ..
```

**Always mirror, never `cp -r` over the web root.** Vite fingerprints every build's JS/CSS with a
content hash, so each build produces new filenames and never deletes the previous build's files.
`cp -r` only adds files, so an old bundle -- potentially built before a scrub fix -- stays on disk
and reachable at its old URL even after `index.html` stops linking to it. `rsync -a --delete` (or
`rm -rf` the target first) removes anything not in the new `dist/`. This bit us once: two prior
builds' JS bundles sat live in `/var/www/incident-ai/assets/` for about a day after the intended fix,
including one built before the last hardcoded name was scrubbed.

The API server does not need a restart (it only reads the live window file). Restart it only if
`server/index.js` itself changed in the `git pull`:

```bash
sudo systemctl restart incident-ai
```

## Check it worked

```bash
# the server is up and serving the synthetic live window (138 incidents)
curl -s http://127.0.0.1:8002/api/health
curl -s http://127.0.0.1:8002/api/live-window | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['incident_count'], d['source'])"

# no production names left in what the browser downloads (should print nothing).
# Replace <COMPANY> with the real company name; do not commit the actual string.
grep -rli "<COMPANY>" /var/www/incident-ai || true

# only the current build's files should exist (matches what index.html references)
cat /var/www/incident-ai/index.html | grep -o 'assets/[^"]*'
ls /var/www/incident-ai/assets/
```

Then open the app in a browser and click through each scenario plus Live mode. Names should read as
pronounceable nonsense (for example `LAFOSA`) and every number, count and timeline should be unchanged.

## Switch back to the real data

```bash
export PATH="$HOME/incident-ai/node/bin:$PATH"
cd ~/incident-ai
git checkout -- app/src/data                          # tracked scenario files return to the committed ones
cp backups/real-data-<STAMP>/june-window.json server/live-data/june-window.json   # if you had one
cd app && VITE_BASE=/incident/ npm run build && rsync -a --delete dist/. /var/www/incident-ai/
```

## Things worth knowing

- **Slugs never change** (`s1-...` to `s5-...`, `live-june-2026`), so routing and the server's
  allow-list keep working.
- Step 2 leaves `git status` showing modified files under `app/src/data/`. That is expected while the
  VM is on synthetic data; the `git checkout` above clears it.
- The model still receives whatever data the screen holds, so with synthetic data it reasons over
  synthetic evidence only.
- Free-text names are removed with rules, so skim the Live window once before showing it outside the team.
- `synthetic-data/` is not covered by the pipeline scripts (`naming.py`, `generator/`), the prompts or
  the docs; those still contain production examples.

## Regenerating

```bash
python scripts/synthesize_all.py         # rebuilds every file, prints the integrity checks
python scripts/synthesize_live_window.py # only the Live window
```

The scrubber is one-way (a random salt stays on the generating machine and is never copied), and a
short private list of internal component names is read from `synthetic-data/.extra-terms.txt`
(also never copied or committed).
