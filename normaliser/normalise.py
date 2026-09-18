#!/usr/bin/env python3
"""
normaliser/normalise.py -- deterministic, mechanical normalisation layer
for the "Incident Response AI" POC (Meridian Retail synthetic estate).

Standard library only. For each scenario under data/<slug>/, parses all 7
raw source files (everything except late-evidence.ndjson, which is kept
separate/withheld) and emits:

    data/<slug>/normalised-events.json      -- the main, chronologically
                                                sorted unified event list
    data/<slug>/late-event-normalised.json  -- the single withheld late
                                                event, same shape, NOT
                                                included in the main array

This module does no diagnosis, ranking, or correlation reasoning -- it
only parses, resolves aliases, converts timestamps to UTC, normalises
severities onto a common 1-4 scale, and assigns stable event ids. That is
the entire scope of the "deterministic data layer".
"""

import csv
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import naming  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generator"))
from scenarios import SCENARIOS  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
NORMALISER_DIR = os.path.dirname(os.path.abspath(__file__))

IST_OFFSET = timedelta(hours=5, minutes=30)

# --------------------------------------------------------------------------
# CMDB alias resolution
# --------------------------------------------------------------------------

# The alias map is derived from naming.py (the single shared source of
# truth also used by generator/generate.py) and written out here so the
# mapping is inspectable/auditable as its own artefact, guaranteed in sync
# with the generator because both come from the same naming.alias_map().
ALIAS_MAP = naming.alias_map()
_ALIAS_KEYS_BY_LEN = sorted(ALIAS_MAP.keys(), key=len, reverse=True)


def resolve_component(*candidates):
    """Resolve the first non-empty candidate string to a CMDB service name
    via longest-prefix match against the alias map. Falls back to the raw
    string if nothing matches (e.g. non-catalogued components like
    oracle-oms, fin-monthend-extract, a Kafka consumer group, or a raw
    partner-feed/MFT system name -- those pass through unchanged, which is
    the correct behaviour for components outside the six core services +
    two gateways)."""
    for c in candidates:
        if not c:
            continue
        for key in _ALIAS_KEYS_BY_LEN:
            if c == key or c.startswith(key):
                return ALIAS_MAP[key]
        return c
    return None


# --------------------------------------------------------------------------
# Timestamp normalisation
# --------------------------------------------------------------------------

def norm_ts_utc(iso_str_with_offset):
    """Already-UTC ISO-8601 timestamps (every file except MFT) pass through
    with the offset canonicalised to +00:00."""
    s = iso_str_with_offset
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return s


def norm_ts_from_ist_naive(naive_local_str):
    """MFT timestamps are naive local IST (UTC+5:30) with no offset suffix
    -- the deliberate wrinkle. Resolve by parsing as naive, subtracting
    5:30, and re-emitting as UTC ISO-8601 with an explicit +00:00 offset."""
    from datetime import datetime
    local = datetime.strptime(naive_local_str, "%Y-%m-%d %H:%M:%S")
    utc = local - IST_OFFSET
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


# --------------------------------------------------------------------------
# Severity normalisation -> common 1 (most severe) .. 4 (least severe) scale
# --------------------------------------------------------------------------
#
#   ELK            event.severity is already P1-P4 -> used as-is (1..4).
#   ServiceNow     priority 1-5 collapsed: 1,2 -> 1 | 3 -> 2 | 4 -> 3 | 5 -> 4
#   Apigee/APIM    from HTTP status + volume: 5xx -> 1 (server-side failure);
#                  4xx with count > 50/min -> 2 (client-error spike, likely
#                  incident-relevant, e.g. an auth break); other 4xx -> 3;
#                  2xx -> 4 (healthy baseline).
#   Kafka          no native severity; derived from lag: lag >= 10,000 -> 1;
#                  1,000-9,999 -> 2; 1-999 -> 3; 0 (caught up) -> 4.
#   MFT            SUCCESS with declared_rows == actual_rows -> 4 (healthy);
#                  SUCCESS but declared_rows != actual_rows -> 1 (silent
#                  failure -- worse than an overt one, since nothing else
#                  flags it); any non-SUCCESS status -> 1.
#   DevOps/change  no native severity; a change with a missing/none
#                  approval_state -> 2 (flagged for review), routine
#                  approved changes -> 4.

def sev_from_sn_priority(p):
    return {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}.get(p, 3)


def sev_from_http(status, count):
    if 500 <= status < 600:
        return 1
    if 400 <= status < 500:
        return 2 if count and count > 50 else 3
    return 4


def sev_from_lag(lag):
    if lag >= 10_000:
        return 1
    if lag >= 1_000:
        return 2
    if lag >= 1:
        return 3
    return 4


def sev_from_mft(status, declared_rows, actual_rows):
    if status != "SUCCESS":
        return 1
    if int(declared_rows) != int(actual_rows):
        return 1
    return 4


def sev_from_change(approval_state):
    if not approval_state or "no approval" in approval_state.lower() or approval_state.lower() == "none":
        return 2
    return 4


# --------------------------------------------------------------------------
# Per-source parsing -> list of normalised (pre-id) event dicts
# --------------------------------------------------------------------------

def parse_elk(path, filename):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            component = resolve_component(d.get("kubernetes.pod.name"), d.get("service.name"))
            events.append({
                "ts": norm_ts_utc(d["@timestamp"]),
                "source": "ELK",
                "component": component,
                "severity": d.get("event.severity", 4),
                "description": d.get("message", ""),
                "correlation_id": d.get("labels.correlation_id"),
                "raw_ref": {"file": filename, "line": i},
            })
    return events


def parse_kafka(path, filename):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            lag = int(row["lag"])
            component = resolve_component(row["consumer_group"].replace("-cg", ""), row["topic"])
            desc = (f"consumer_group={row['consumer_group']} topic={row['topic']} "
                    f"partition={row['partition']} current_offset={row['current_offset']} "
                    f"log_end_offset={row['log_end_offset']} lag={lag}")
            events.append({
                "ts": norm_ts_utc(row["timestamp"]),
                "source": "Kafka",
                "component": component,
                "severity": sev_from_lag(lag),
                "description": desc,
                "correlation_id": None,  # kafka-lag.csv carries no correlation id column
                "raw_ref": {"file": filename, "row": i},
            })
    return events


def parse_gw(path, filename, source_label):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8") as f:
        arr = json.load(f)
    component = "apigee-edge" if source_label == "Apigee" else "azure-apim"
    for i, rec in enumerate(arr):
        sample_ids = rec.get("sample_correlation_ids") or []
        desc = (f"endpoint={rec['endpoint']} status={rec['status']} count={rec['count']} "
                f"p99_latency_ms={rec['p99_latency_ms']}")
        events.append({
            "ts": norm_ts_utc(rec["minute"]),
            "source": source_label,
            "component": component,
            "severity": sev_from_http(rec["status"], rec["count"]),
            "description": desc,
            "correlation_id": sample_ids[0] if sample_ids else None,
            "raw_ref": {"file": filename, "index": i},
        })
    return events


def parse_mft(path, filename):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            desc = (f"{row['filename']} {row['source']}->{row['target']} "
                    f"status={row['status']} bytes={row['bytes']} "
                    f"declared_rows={row['declared_rows']} actual_rows={row['actual_rows']}")
            events.append({
                "ts": norm_ts_from_ist_naive(row["start_time"]),
                "source": "MFT",
                "component": resolve_component(row["target"]),
                "severity": sev_from_mft(row["status"], row["declared_rows"], row["actual_rows"]),
                "description": desc,
                "correlation_id": None,  # mft-transfers.csv carries no correlation id column
                "raw_ref": {"file": filename, "row": i},
            })
    return events


def parse_servicenow(path, filename):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8") as f:
        arr = json.load(f)
    for i, rec in enumerate(arr):
        events.append({
            "ts": norm_ts_utc(rec["opened_at"]),
            "source": "ServiceNow",
            "component": resolve_component(rec.get("assignment_group")),
            "severity": sev_from_sn_priority(rec["priority"]),
            "description": f"{rec['number']}: {rec['short_description']}",
            "correlation_id": None,  # ticket schema carries no correlation id field
            "raw_ref": {"file": filename, "index": i},
        })
    return events


def parse_change_records(path, filename):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, encoding="utf-8") as f:
        arr = json.load(f)
    for i, rec in enumerate(arr):
        events.append({
            "ts": norm_ts_utc(rec["implemented_at"]),
            "source": "DevOps",
            "component": resolve_component(rec.get("component")),
            "severity": sev_from_change(rec.get("approval_state")),
            "description": f"{rec['change_number']} ({rec['type']}): {rec['description']}",
            "correlation_id": None,  # change records carry no correlation id field
            "raw_ref": {"file": filename, "index": i},
        })
    return events


def parse_late_evidence(path, filename):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        line = f.readline().strip()
    d = json.loads(line)
    component = resolve_component(d.get("kubernetes.pod.name"), d.get("service.name"))
    return {
        "ts": norm_ts_utc(d["@timestamp"]),
        "source": "ELK",
        "component": component,
        "severity": d.get("event.severity", 4),
        "description": d.get("message", ""),
        "correlation_id": d.get("labels.correlation_id"),
        "raw_ref": {"file": filename, "line": 1},
    }


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def normalise_scenario(slug):
    scen_dir = os.path.join(DATA_DIR, slug)
    events = []
    events += parse_elk(os.path.join(scen_dir, "elk-logs.ndjson"), "elk-logs.ndjson")
    events += parse_kafka(os.path.join(scen_dir, "kafka-lag.csv"), "kafka-lag.csv")
    events += parse_gw(os.path.join(scen_dir, "apigee-errors.json"), "apigee-errors.json", "Apigee")
    events += parse_gw(os.path.join(scen_dir, "apim-errors.json"), "apim-errors.json", "APIM")
    events += parse_mft(os.path.join(scen_dir, "mft-transfers.csv"), "mft-transfers.csv")
    events += parse_servicenow(os.path.join(scen_dir, "servicenow-incidents.json"), "servicenow-incidents.json")
    events += parse_change_records(os.path.join(scen_dir, "change-records.json"), "change-records.json")

    events.sort(key=lambda e: e["ts"])
    for idx, e in enumerate(events, start=1):
        e["event_id"] = f"e-{idx:04d}"
    # reorder keys for readability: event_id first
    ordered = [
        {"event_id": e["event_id"], "ts": e["ts"], "source": e["source"],
         "component": e["component"], "severity": e["severity"],
         "description": e["description"], "correlation_id": e["correlation_id"],
         "raw_ref": e["raw_ref"]}
        for e in events
    ]

    late = parse_late_evidence(os.path.join(scen_dir, "late-evidence.ndjson"), "late-evidence.ndjson")
    late_ordered = None
    if late is not None:
        late_ordered = {
            "event_id": "e-late-0001", "ts": late["ts"], "source": late["source"],
            "component": late["component"], "severity": late["severity"],
            "description": late["description"], "correlation_id": late["correlation_id"],
            "raw_ref": late["raw_ref"],
        }

    with open(os.path.join(scen_dir, "normalised-events.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if late_ordered is not None:
        with open(os.path.join(scen_dir, "late-event-normalised.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(late_ordered, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return ordered, late_ordered


def main():
    os.makedirs(NORMALISER_DIR, exist_ok=True)
    with open(os.path.join(NORMALISER_DIR, "cmdb-aliases.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(ALIAS_MAP, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    for scn in SCENARIOS:
        slug = scn["slug"]
        events, late = normalise_scenario(slug)
        if events:
            date_range = f"{events[0]['ts']} -> {events[-1]['ts']}"
        else:
            date_range = "n/a"
        late_desc = f"late-event: {late['ts']} ({late['description'][:60]}...)" if late else "late-event: none"
        print(f"[{slug}] events={len(events)} range={date_range} {late_desc}")


if __name__ == "__main__":
    main()
