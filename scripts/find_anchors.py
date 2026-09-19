#!/usr/bin/env python3
"""Resolves the declarative anchor specs in generator/anchors_spec.py against
data/<slug>/normalised-events.json and writes data/<slug>/anchors.json.

anchors.json = {
  slug, title, incident_number, duplicate_incidents, fault_one_line,
  cheapest_check_text,
  first_symptom: event_id,
  late_event: 'e-late-0001', late_event_ts,
  cheapest_decisive_check: [event_id ...],          # evidence for the cheapest decisive check
  by_role: { role: [event_id...] },                 # first_symptom|onset|decisive|contradiction|ticket|context
  anchors: [ {key, role, event_ids, kind: 'rule_hit'|'context'|'mixed',
              rule_ids, label, ts, check} ... ]
}

Fails loudly if an anchor matches nothing or the matched event has a
different `kind` than the spec expects. The authoring step depends on this
file plus normalised-events.json. Standard library only."""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "generator"))
from scenarios import SCENARIOS  # noqa: E402
from anchors_spec import ANCHORS  # noqa: E402


def hms(ts):
    return ts[11:19]


def resolve(events, spec):
    m = spec["match"]
    rx = re.compile(m["re"])
    out = []
    for e in events:
        if m.get("source") and e["source"] != m["source"]:
            continue
        if m.get("rule_id") and e.get("rule_id") != m["rule_id"]:
            continue
        if m.get("ts_from") and hms(e["ts"]) < m["ts_from"]:
            continue
        if m.get("ts_to") and hms(e["ts"]) > m["ts_to"]:
            continue
        if not rx.search(e["description"]):
            continue
        out.append(e)
    if not out:
        return []
    pick = m.get("pick", "first")
    return out if pick == "all" else [out[-1]] if pick == "last" else [out[0]]


def main():
    problems = 0
    for sc in SCENARIOS:
        slug = sc["slug"]
        d = os.path.join(REPO_ROOT, "data", slug)
        with open(os.path.join(d, "normalised-events.json"), encoding="utf-8") as f:
            events = json.load(f)
        with open(os.path.join(d, "late-event-normalised.json"), encoding="utf-8") as f:
            late = json.load(f)
        anchors, by_role, checks = [], {}, []
        first_symptom = None
        print(f"\n===== {slug} ({len(events)} events) =====")
        for spec in ANCHORS[sc["id"]]:
            hit = resolve(events, spec)
            if not hit:
                print(f"  !! NO MATCH: {spec['key']}")
                problems += 1
                continue
            kinds = {e["kind"] for e in hit}
            if kinds != {spec["expect"]}:
                print(f"  !! KIND MISMATCH {spec['key']}: expected {spec['expect']} got {kinds}")
                problems += 1
            ids = [e["event_id"] for e in hit]
            anchors.append({"key": spec["key"], "role": spec["role"], "event_ids": ids,
                            "kind": next(iter(kinds)) if len(kinds) == 1 else "mixed",
                            "rule_ids": sorted({e["rule_id"] for e in hit if e.get("rule_id")}),
                            "label": spec["label"], "ts": hit[0]["ts"], "check": spec["check"]})
            by_role.setdefault(spec["role"], []).extend(ids)
            if spec["check"]:
                checks.extend(ids)
            if spec["role"] == "first_symptom":
                first_symptom = ids[0]
            print(f"  {spec['key']:22s} {spec['role']:13s} {','.join(ids[:3]):22s} {hit[0]['ts'][11:19]} "
                  f"{hit[0]['kind']:9s} {spec['label'][:72]}")
        out = {
            "slug": slug, "title": sc["title"], "incident_number": sc["incident_number"],
            "duplicate_incidents": sc["duplicate_incidents"], "fault_one_line": sc["fault_one_line"],
            "cheapest_check_text": sc["cheapest_check"],
            "first_symptom": first_symptom, "late_event": late["event_id"], "late_event_ts": late["ts"],
            "cheapest_decisive_check": checks, "by_role": by_role, "anchors": anchors,
        }
        with open(os.path.join(d, "anchors.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
    if problems:
        raise SystemExit(f"{problems} anchor problem(s)")
    print("\nall anchors resolved")


if __name__ == "__main__":
    main()
