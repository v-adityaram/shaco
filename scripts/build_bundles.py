#!/usr/bin/env python3
"""Assembles app/src/data/<slug>/bundle.json for each scenario from:
  - authoring/<slug>.json           hand-authored diagnosis + late-evidence diff/overrides
  - data/<slug>/normalised-events.json / late-event-normalised.json   real generated events
  - app/src/data/<slug>/alert-feed.json  Screen 1 alert rows (see build_alert_feed.py)

Also validates every event_id cited in the authored diagnosis actually exists
in the scenario's normalised event list (or the late event) -- an unresolved
citation is a hard error, per the plan's own validation requirement.
Standard library only.
"""
import copy
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
AUTHORING_DIR = os.path.join(REPO_ROOT, "authoring")
APP_DATA_DIR = os.path.join(REPO_ROOT, "app", "src", "data")

SLUGS = [
    "s1-memory-leak",
    "s2-poison-message",
    "s3-config-change",
    "s4-mft-truncation",
    "s5-oracle-saturation",
]


def collect_cited_ids(diagnosis):
    ids = set()
    for item in diagnosis.get("timeline", []):
        ids.add(item["event_id"])
    for h in diagnosis.get("hypotheses", []):
        for s in h.get("supports", []):
            ids.add(s["event_id"])
        for c in h.get("contradicts", []):
            ids.add(c["event_id"])
    return ids


def to_normalised_event(e):
    return {
        "event_id": e["event_id"],
        "ts": e["ts"],
        "source": e["source"],
        "component": e["component"],
        "severity": e["severity"],
        "description": e["description"],
        "correlation_id": e.get("correlation_id"),
        "raw_ref": e.get("raw_ref"),
    }


def count_rules_fired(slug):
    rules = set()
    path = os.path.join(DATA_DIR, slug, "elk-logs.ndjson")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("rule.id"):
                rules.add(d["rule.id"])
    return len(rules)


def apply_hypothesis_patches(hypotheses, patches):
    for h in hypotheses:
        patch = patches.get(str(h["rank"]))
        if not patch:
            continue
        h.update(patch)
    return hypotheses


def build(slug):
    with open(os.path.join(AUTHORING_DIR, f"{slug}.json"), encoding="utf-8") as f:
        authored = json.load(f)
    with open(os.path.join(DATA_DIR, slug, "normalised-events.json"), encoding="utf-8") as f:
        norm_events = {e["event_id"]: e for e in json.load(f)}
    with open(os.path.join(DATA_DIR, slug, "late-event-normalised.json"), encoding="utf-8") as f:
        late_event = json.load(f)
    with open(os.path.join(APP_DATA_DIR, slug, "alert-feed.json"), encoding="utf-8") as f:
        alert_rows = json.load(f)

    diagnosis = authored["diagnosis"]
    late = authored["lateEvidence"]

    cited = collect_cited_ids(diagnosis)
    missing = [i for i in cited if i not in norm_events]
    if missing:
        raise SystemExit(f"[{slug}] UNRESOLVED CITATIONS: {missing}")

    for h in diagnosis["hypotheses"]:
        if not h.get("contradicts"):
            raise SystemExit(f"[{slug}] hypothesis rank {h['rank']} has an empty contradicts array")
    if len(diagnosis["hypotheses"]) < 2:
        raise SystemExit(f"[{slug}] fewer than 2 hypotheses")

    events = [to_normalised_event(norm_events[i]) for i in sorted(cited, key=lambda i: norm_events[i]["ts"])]
    events.append(to_normalised_event(late_event))

    # ---- diagnosisAfter: deep-copy diagnosis, splice in the late event,
    # apply the authored overrides ----
    diagnosis_after = copy.deepcopy(diagnosis)
    overrides = late.get("diagnosisAfterOverrides", {})
    if "incident_summary" in overrides:
        diagnosis_after["incident_summary"] = overrides["incident_summary"]
    new_timeline_item = {
        "event_id": late_event["event_id"],
        "ts": late_event["ts"],
        "source": late_event["source"],
        "component": late_event["component"],
        "description": late_event["description"],
        "is_first_symptom": False,
    }
    diagnosis_after["timeline"] = sorted(
        diagnosis_after["timeline"] + [new_timeline_item], key=lambda t: t["ts"]
    )
    apply_hypothesis_patches(diagnosis_after["hypotheses"], overrides.get("hypothesisPatches", {}))

    diff = {
        "new_event": new_timeline_item,
        "changed_summary": late["diff"]["changed_summary"],
        "rank_before": late["diff"]["rank_before"],
        "rank_after": late["diff"]["rank_after"],
        "what_changed": late["diff"]["what_changed"],
    }

    bundle = {
        "meta": authored["meta"],
        "events": events,
        "alertRows": alert_rows,
        "diagnosis": diagnosis,
        "lateEvidence": {
            "event": to_normalised_event(late_event),
            "diff": diff,
            "diagnosisAfter": diagnosis_after,
        },
        "rulesFired": count_rules_fired(slug),
        "rulesTotal": 412,
    }

    out_path = os.path.join(APP_DATA_DIR, slug, "bundle.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[{slug}] OK — events={len(events)} alertRows={len(alert_rows)} "
          f"rulesFired={bundle['rulesFired']} citations_resolved={len(cited)}")


def main():
    for slug in SLUGS:
        build(slug)


if __name__ == "__main__":
    main()
