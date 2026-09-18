#!/usr/bin/env python3
"""One-off helper (not part of the shipped pipeline): for each scenario's
anchor `signals` in generator/scenarios.py, find the matching event_id(s) in
data/<slug>/normalised-events.json by timestamp (+/- a few seconds), so the
hand-authored AI diagnosis bundles can cite real event_ids. Prints candidates
for manual review -- does not write anything."""
import json
import os
import sys
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "generator"))
from scenarios import SCENARIOS  # noqa: E402

TOLERANCE = timedelta(seconds=30)


def parse_ts(s):
    return datetime.fromisoformat(s)


def main():
    for scen in SCENARIOS:
        slug = scen["slug"]
        path = os.path.join(REPO_ROOT, "data", slug, "normalised-events.json")
        with open(path, encoding="utf-8") as f:
            events = json.load(f)
        print(f"\n===== {slug} =====")
        for sig in scen["signals"]:
            target = parse_ts(f"2026-09-18T{sig['time']}+00:00")
            exact = [e for e in events if parse_ts(e["ts"]) == target]
            candidates = exact or [
                e for e in events
                if abs(parse_ts(e["ts"]) - target) <= TOLERANCE
            ]
            print(f"\n  signal: {sig['time']} {sig['source']} -- {sig['text'][:70]}")
            if not candidates:
                print("    NO MATCH")
            for e in candidates[:10]:
                print(f"    {e['event_id']} {e['ts']} {e['source']:10s} {e['component']:22s} {e['description'][:70]}")


if __name__ == "__main__":
    main()
