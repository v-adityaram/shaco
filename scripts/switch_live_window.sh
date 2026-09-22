#!/usr/bin/env bash
# Switches which Live-mode window the server is currently serving. Takes effect
# immediately -- the server reads server/live-data/june-window.json on every
# request, so no restart or rebuild is needed.
#
# Usage (run from the repo root, e.g. ~/incident-ai on the VM):
#   scripts/switch_live_window.sh full       # our fully-scrubbed version (default)
#   scripts/switch_live_window.sh minimal    # touches only e-mails/phones/names/brand;
#                                             # everything else stays exactly as the team's file
#   scripts/switch_live_window.sh status     # show which one is currently active
#
# Both variants live in synthetic-data/live/ (git-ignored). See
# docs/VM-SYNTHETIC-DATA.md and FINDINGS.md ("Round 6") for what differs between them.
set -euo pipefail
cd "$(dirname "$0")/.."

FULL=synthetic-data/live/june-window.synthetic.json
MINIMAL=synthetic-data/live/june-window.minimal.json
ACTIVE=server/live-data/june-window.json

case "${1:-}" in
  full)
    [ -f "$FULL" ] || { echo "missing $FULL -- run: python scripts/build_team_synthetic_window.py <xlsx>"; exit 1; }
    cp "$FULL" "$ACTIVE"
    echo "active: full (fully scrubbed)"
    ;;
  minimal)
    [ -f "$MINIMAL" ] || { echo "missing $MINIMAL -- run: python scripts/build_team_minimal_scrub_window.py <xlsx>"; exit 1; }
    cp "$MINIMAL" "$ACTIVE"
    echo "active: minimal (only e-mails/phones/names/brand removed; everything else is the team's own file)"
    ;;
  status)
    python3 -c "import json; d=json.load(open('$ACTIVE',encoding='utf-8')); print(d.get('source'))" 2>/dev/null \
      || echo "no active window at $ACTIVE"
    ;;
  *)
    echo "usage: $0 {full|minimal|status}"; exit 1
    ;;
esac
