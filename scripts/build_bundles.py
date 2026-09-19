#!/usr/bin/env python3
"""Assembles app/src/data/<slug>/bundle.json for every scenario.

Inputs
  data/<slug>/normalised-events.json, late-event-normalised.json, anchors.json
  app/src/data/<slug>/alert-feed.json   ({alertRows, dashboard} object form)
  authoring/<slug>.json                 OPTIONAL. Present  -> meta.mode 'curated'
                                        (hand-authored diagnosis + late-evidence diff).
                                        Absent   -> meta.mode 'ai-live'
                                        (diagnosis null, lateEvidence.diff/diagnosisAfter null;
                                        nothing is ever fabricated for these).
Output bundle keys
  meta, events (the EVIDENCE PACK), alertRows, dashboard, diagnosis, lateEvidence,
  rulesFired, rulesTotal (412), noiseRulesFired.

EVIDENCE PACK -- deterministic, code-built, ~120-300 events (full list stays
in data/<slug>/normalised-events.json as the source of truth). Selection rules:
  1. RULE HITS. Every distinct rule hit is present. Identical repeats are
     collapsed into one event whose description states the count and the
     first/last time. Identity = (source, rule_id, component, description with
     exchange ids / long numbers removed; all digits removed for non-HIPMON
     sources). Kafka lag hits keep up to 6 evenly spaced samples (the lag
     trajectory), Apigee up to 3; Sonar hourly reports and ServiceNow
     incidents are never collapsed. The standing-noise hits are included
     (collapsed) so the analyst can dismiss them.
  2. ANCHORS. Every event id in data/<slug>/anchors.json (first symptom, onsets,
     decisive evidence, contradictions, tickets) is included individually,
     uncollapsed, with its original description.
  3. COMPUTED SUMMARIES. Code-computed context events (raw_ref.computed: silence,
     heartbeat absence, stalled-exchange, failed-by-reason, partial-success),
     up to 12 evenly spaced per kind. This is where absences are stated.
  4. CHANGE + MFT + TICKET CONTEXT. All change/vendor records, all MFT rows,
     all ServiceNow updates/work notes (all are few).
  5. BASELINE-VS-INCIDENT + RELEVANT CONTEXT. Remaining context events that are
     in incident scope (component in scope), share a correlation id with a
     selected event, or deviate from baseline (severity <= 3) are added, evenly
     sampled, until the pack holds TARGET_MIN..TARGET_MAX events; ordinary
     baseline context (severity 4) is sampled last.
The pack is sorted by time; citations and the validator work on it.
`python scripts/build_bundles.py --pack-only` writes data/<slug>/evidence-pack.json
only (the authoring step reads that). Standard library only."""
import copy
import json
import os
import re
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "generator"))
sys.path.insert(0, REPO_ROOT)
import naming  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

DATA_DIR = os.path.join(REPO_ROOT, "data")
AUTHORING_DIR = os.environ.get("HIP_AUTHORING_DIR") or os.path.join(REPO_ROOT, "authoring")
APP_DATA_DIR = os.path.join(REPO_ROOT, "app", "src", "data")
RULES_TOTAL = 412
TARGET_MIN, TARGET_MAX = 150, 260
NOISE_RULE_IDS = {n["rule_id"] for n in naming.STANDING_NOISE}
KEEP_K = {"Kafka": 6, "Apigee": 3}
NEVER_COLLAPSE_SOURCES = {"ServiceNow"}
NEVER_COLLAPSE_RULES = {"SNR-HRLY-CRIT"}
XID = re.compile(r"\b(\d{24}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def even_sample(items, k):
    if k >= len(items):
        return list(items)
    if k <= 0:
        return []
    step = (len(items) - 1) / (k - 1) if k > 1 else 0
    idx = sorted({round(i * step) for i in range(k)}) if k > 1 else [0]
    return [items[i] for i in idx]


def group_key(e):
    d = XID.sub("<id>", e["description"])
    if e["source"] == "HIPMON":
        d = re.sub(r"\b\d{4,}\b", "#", d)
    else:
        d = re.sub(r"\d+", "#", d)
    if e["source"] in NEVER_COLLAPSE_SOURCES or e.get("rule_id") in NEVER_COLLAPSE_RULES:
        return (e["source"], e.get("rule_id"), e["event_id"])
    return (e["source"], e.get("rule_id"), e["component"], d)


def in_scope(e, sc):
    s = sc["scope"]
    return e["component"] in s["components"] or e["component"] in s["projects"]


def related_hit(e, sc, first_ts):
    """Is this rule hit related to the incident (for rulesFired)?"""
    rid = e.get("rule_id") or ""
    if rid.startswith("SNOW-") or rid in NOISE_RULE_IDS:
        return False
    if in_scope(e, sc):
        return True
    code = rid.replace("HIPMON-", "")
    if rid.startswith("HIPMON-") and code in sc["scope"]["incident_codes"]:
        return True
    if rid in ("KFK-LAG-004", "APG-5XX-012", "WKT-JOBFAIL-001", "SNR-HRLY-CRIT") and e["ts"] >= first_ts:
        return True
    return False


def build_pack(events, anchors, sc):
    by_id = {e["event_id"]: e for e in events}
    anchor_ids = set(anchors["first_symptom"] and [anchors["first_symptom"]] or [])
    for a in anchors["anchors"]:
        anchor_ids.update(a["event_ids"])
    first_ts = by_id[anchors["first_symptom"]]["ts"]
    sel = {}

    def add(e, desc=None):
        c = copy.deepcopy(e)
        if desc:
            c["description"] = desc
        sel.setdefault(c["event_id"], c)
        return sel[c["event_id"]]

    # 1. rule hits
    groups = defaultdict(list)
    for e in events:
        if e["kind"] == "rule_hit":
            groups[group_key(e)].append(e)
    for key, members in groups.items():
        rest = [m for m in members if m["event_id"] not in anchor_ids]
        for m in members:
            if m["event_id"] in anchor_ids:
                add(m)
        if not rest:
            continue
        n = len(members)
        k = KEEP_K.get(members[0]["source"], 1)
        keep = even_sample(rest, k)
        for i, m in enumerate(keep):
            if i == 0 and n > 1:
                add(m, f"{m['description']}  [x{n} identical hits in total; first {members[0]['ts'][11:19]}, "
                       f"last {members[-1]['ts'][11:19]} UTC]")
            else:
                add(m)
    # 2. anchors
    for i in sorted(anchor_ids):
        add(by_id[i])
    # 3. computed summaries
    comp = defaultdict(list)
    for e in events:
        rr = e.get("raw_ref") or {}
        if e["kind"] == "context" and rr.get("computed"):
            comp[rr["computed"]].append(e)
    for kind, es in comp.items():
        for e in even_sample(es, 12):
            add(e)
    # 4. change / MFT / ticket context
    for e in events:
        if e["source"] in ("Change", "MFT") or (e["source"] == "ServiceNow" and e["kind"] == "context"):
            add(e)
    # 5. relevant + baseline context, evenly sampled up to the target
    corr = {e["correlation_id"] for e in sel.values() if e.get("correlation_id")}
    pool = [e for e in events if e["event_id"] not in sel and e["kind"] == "context"]
    tier1 = [e for e in pool if in_scope(e, sc) or (e.get("correlation_id") in corr) or e["severity"] <= 3]
    t1_ids = {e["event_id"] for e in tier1}
    tier2 = [e for e in pool if e["event_id"] not in t1_ids]
    room = TARGET_MAX - len(sel)
    for e in even_sample(tier1, max(room, 0)):
        add(e)
    if len(sel) < TARGET_MIN:
        for e in even_sample(tier2, TARGET_MIN - len(sel)):
            add(e)
    pack = sorted(sel.values(), key=lambda e: (e["ts"], e["event_id"]))
    return pack, first_ts


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


def to_event(e):
    out = {"event_id": e["event_id"], "ts": e["ts"], "source": e["source"], "component": e["component"],
           "severity": e["severity"], "description": e["description"], "correlation_id": e.get("correlation_id"),
           "kind": e["kind"]}
    if e.get("rule_id"):
        out["rule_id"] = e["rule_id"]
    if e.get("raw_ref") is not None:
        out["raw_ref"] = e["raw_ref"]
    return out


def build(sc, pack_only=False):
    slug = sc["slug"]
    d = os.path.join(DATA_DIR, slug)
    events = load(os.path.join(d, "normalised-events.json"))
    late_event = load(os.path.join(d, "late-event-normalised.json"))
    anchors = load(os.path.join(d, "anchors.json"))
    pack, first_ts = build_pack(events, anchors, sc)
    pack_ids = {e["event_id"] for e in pack}
    hits = [e for e in pack if e["kind"] == "rule_hit"]
    related = [e for e in hits if related_hit(e, sc, first_ts)]
    rules_fired = len({e["rule_id"] for e in related})
    noise_fired = len({e["rule_id"] for e in hits if e["rule_id"] in NOISE_RULE_IDS})
    with open(os.path.join(d, "evidence-pack.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"slug": slug, "events": [to_event(e) for e in pack]}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if pack_only:
        print(f"[{slug}] pack events={len(pack)} rule_hit={len(hits)} context={len(pack) - len(hits)} "
              f"rulesFired={rules_fired} noiseRulesFired={noise_fired}")
        return

    feed = load(os.path.join(APP_DATA_DIR, slug, "alert-feed.json"))
    if not (isinstance(feed, dict) and "alertRows" in feed and "dashboard" in feed):
        raise SystemExit(f"[{slug}] alert-feed.json must be the object form {{alertRows, dashboard}}")
    auth_path = os.path.join(AUTHORING_DIR, f"{slug}.json")
    curated = os.path.exists(auth_path)
    late_norm = to_event(late_event)
    if curated:
        authored = load(auth_path)
        diagnosis = authored["diagnosis"]
        late = authored["lateEvidence"]
        cited = collect_cited_ids(diagnosis)
        missing = sorted(i for i in cited if i not in pack_ids)
        if missing:
            raise SystemExit(f"[{slug}] UNRESOLVED CITATIONS (not in evidence pack): {missing}")
        for h in diagnosis["hypotheses"]:
            if not h.get("contradicts"):
                raise SystemExit(f"[{slug}] hypothesis rank {h['rank']} has an empty contradicts array")
        if len(diagnosis["hypotheses"]) < 2:
            raise SystemExit(f"[{slug}] fewer than 2 hypotheses")
        meta = dict(authored["meta"])
        meta["mode"] = "curated"
        diagnosis_after = copy.deepcopy(diagnosis)
        overrides = late.get("diagnosisAfterOverrides", {})
        if "incident_summary" in overrides:
            diagnosis_after["incident_summary"] = overrides["incident_summary"]
        item = {"event_id": late_event["event_id"], "ts": late_event["ts"], "source": late_event["source"],
                "component": late_event["component"], "description": late_event["description"], "is_first_symptom": False}
        diagnosis_after["timeline"] = sorted(diagnosis_after["timeline"] + [item], key=lambda t: t["ts"])
        for h in diagnosis_after["hypotheses"]:
            patch = overrides.get("hypothesisPatches", {}).get(str(h["rank"]))
            if patch:
                h.update(patch)
        diff = {"new_event": item, "changed_summary": late["diff"]["changed_summary"],
                "rank_before": late["diff"]["rank_before"], "rank_after": late["diff"]["rank_after"],
                "what_changed": late["diff"]["what_changed"]}
        late_block = {"event": late_norm, "diff": diff, "diagnosisAfter": diagnosis_after}
    else:
        meta = {"slug": slug, "title": sc["title"], "incidentNumber": sc["incident_number"],
                "duplicateIncidents": sc["duplicate_incidents"], "faultOneLine": sc["fault_one_line"], "mode": "ai-live"}
        diagnosis = None
        late_block = {"event": late_norm, "diff": None, "diagnosisAfter": None}
        cited = set()

    bundle = {"meta": meta, "events": [to_event(e) for e in pack], "alertRows": feed["alertRows"],
              "dashboard": feed["dashboard"], "diagnosis": diagnosis, "lateEvidence": late_block,
              "rulesFired": rules_fired, "rulesTotal": RULES_TOTAL, "noiseRulesFired": noise_fired}
    out_path = os.path.join(APP_DATA_DIR, slug, "bundle.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[{slug}] OK mode={meta['mode']} pack={len(pack)} (rule_hit={len(hits)} context={len(pack) - len(hits)}) "
          f"alertRows={len(feed['alertRows'])} rulesFired={rules_fired} noiseRulesFired={noise_fired} "
          f"citations_resolved={len(cited)}")


def main():
    pack_only = "--pack-only" in sys.argv
    for sc in SCENARIOS:
        build(sc, pack_only)


if __name__ == "__main__":
    main()
