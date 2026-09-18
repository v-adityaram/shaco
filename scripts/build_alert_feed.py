#!/usr/bin/env python3
"""Builds app/src/data/<slug>/alert-feed.json -- the Screen 1 "Today" dense
alert list -- from the real generated raw files. Every row is drawn from
actual generated data (no fabricated content); this script only selects,
labels (P1-P4 + a display rule id) and orders rows for the dramatized
alert-floor view. Standard library only."""
import csv
import json
import os
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
OUT_DIR = os.path.join(REPO_ROOT, "app", "src", "data")

SEV_MAP = {1: "P1", 2: "P2", 3: "P3", 4: "P4"}

# window (minutes before the primary ServiceNow ticket) + the single
# earliest anchor event_id to always pin in as the (possibly buried)
# first-symptom row, even if it falls outside the window.
SCENARIO_WINDOWS = {
    "s1-memory-leak": {"window_min": 20, "first_symptom_id": "e-0767"},
    "s2-poison-message": {"window_min": 20, "first_symptom_id": "e-1093"},
    "s3-config-change": {"window_min": 16, "first_symptom_id": "e-1086"},
    "s4-mft-truncation": {"window_min": 45, "first_symptom_id": "e-0568"},
    "s5-oracle-saturation": {"window_min": 15, "first_symptom_id": "e-2161"},
}

NOISE_PODS = {"nightly-settlement-batch"}


def sev_from_lag(lag):
    if lag >= 10_000:
        return 1
    if lag >= 1_000:
        return 2
    if lag >= 1:
        return 3
    return 4


def sev_from_http(status, count):
    if 500 <= status < 600:
        return 1
    if 400 <= status < 500:
        return 2 if count and count > 50 else 3
    return 4


def load_elk_rows(slug):
    rows = []
    path = os.path.join(DATA_DIR, slug, "elk-logs.ndjson")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            sev = d.get("event.severity", 4)
            rule_id = d.get("rule.id")
            component = d.get("service.name", "")
            rows.append({
                "ts": d["@timestamp"],
                "source": "ELK",
                "ruleId": rule_id or "—",
                "component": d.get("kubernetes.pod.name", component),
                "message": d["message"],
                "severity": SEV_MAP.get(sev, "P4"),
                "correlationId": d.get("labels.correlation_id"),
                "isNoise": component in NOISE_PODS,
            })
    return rows


def load_kafka_rows(slug):
    rows = []
    path = os.path.join(DATA_DIR, slug, "kafka-lag.csv")
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            lag = int(row["lag"])
            sev = sev_from_lag(lag)
            if sev == 4:
                continue  # healthy baseline row, not alert-worthy
            rows.append({
                "ts": row["timestamp"],
                "source": "Kafka",
                "ruleId": "KFK-LAG-004",
                "component": f"{row['consumer_group']} / {row['topic']}",
                "message": f"lag {lag:,} (partition {row['partition']}, offset {row['current_offset']})",
                "severity": SEV_MAP[sev],
                "correlationId": None,
                "isNoise": False,
            })
    return rows


def load_gw_rows(slug, filename, label, rule_id):
    rows = []
    path = os.path.join(DATA_DIR, slug, filename)
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        arr = json.load(f)
    for rec in arr:
        sev = sev_from_http(rec["status"], rec["count"])
        if sev == 4:
            continue
        rows.append({
            "ts": rec["minute"],
            "source": label,
            "ruleId": rule_id,
            "component": rec["endpoint"],
            "message": f"{rec['status']} rate, count={rec['count']} p99={rec['p99_latency_ms']}ms",
            "severity": SEV_MAP[sev],
            "correlationId": (rec.get("sample_correlation_ids") or [None])[0],
            "isNoise": False,
        })
    return rows


def load_sn_rows(slug):
    rows = []
    path = os.path.join(DATA_DIR, slug, "servicenow-incidents.json")
    with open(path, encoding="utf-8") as f:
        arr = json.load(f)
    for rec in arr:
        rows.append({
            "ts": rec["opened_at"],
            "source": "ServiceNow",
            "ruleId": rec["number"],
            "component": rec["assignment_group"],
            "message": rec["short_description"],
            "severity": "P1" if rec["priority"] <= 2 else "P2",
            "correlationId": None,
            "isNoise": False,
        })
    return rows, arr


def parse_ts(s):
    return datetime.fromisoformat(s)


def build(slug, cfg):
    all_rows = (
        load_elk_rows(slug)
        + load_kafka_rows(slug)
        + load_gw_rows(slug, "apigee-errors.json", "Apigee", "APG-5XX-012")
        + load_gw_rows(slug, "apim-errors.json", "APIM", "AZ-GW-0091")
    )
    sn_rows, sn_raw = load_sn_rows(slug)
    all_rows += sn_rows

    ticket_time = max(parse_ts(r["ts"]) for r in sn_rows)
    window_start = ticket_time - timedelta(minutes=cfg["window_min"])

    windowed = [
        r for r in all_rows
        if r.get("isNoise") or window_start <= parse_ts(r["ts"]) <= ticket_time
    ]

    # thin out high-frequency Kafka rows (one every 15s) to keep the feed
    # dense but not absurd -- keep every 4th sample per component
    kafka_seen = {}
    thinned = []
    for r in windowed:
        if r["source"] != "Kafka":
            thinned.append(r)
            continue
        key = r["component"]
        kafka_seen[key] = kafka_seen.get(key, 0) + 1
        if kafka_seen[key] % 4 == 1:
            thinned.append(r)
    windowed = thinned

    # pin the first-symptom row explicitly (may be well outside the window)
    fs_id = cfg["first_symptom_id"]
    pinned = None
    with open(os.path.join(DATA_DIR, slug, "normalised-events.json"), encoding="utf-8") as f:
        norm = {e["event_id"]: e for e in json.load(f)}
    fs = norm.get(fs_id)
    if fs:
        pinned = {
            "ts": fs["ts"],
            "source": fs["source"],
            "ruleId": "—",
            "component": fs["component"],
            "message": fs["description"],
            "severity": SEV_MAP.get(fs["severity"], "P4"),
            "correlationId": fs["correlation_id"],
            "isNoise": False,
            "isFirstSymptom": True,
        }
        windowed = [r for r in windowed if r["ts"] != fs["ts"] or r["message"] != fs["description"]]
        windowed.append(pinned)

    windowed.sort(key=lambda r: r["ts"], reverse=True)

    out_dir = os.path.join(OUT_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "alert-feed.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(windowed, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[{slug}] alert-feed rows={len(windowed)} window={cfg['window_min']}min "
          f"noise={sum(1 for r in windowed if r.get('isNoise'))} "
          f"first_symptom={'yes' if pinned else 'MISSING'} tickets={len(sn_raw)}")


def main():
    for slug, cfg in SCENARIO_WINDOWS.items():
        build(slug, cfg)


if __name__ == "__main__":
    main()
