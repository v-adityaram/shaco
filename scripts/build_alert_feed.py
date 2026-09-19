#!/usr/bin/env python3
"""Builds app/src/data/<slug>/alert-feed.json for the Screen 1 "Today" view:

    { "alertRows": AlertRow[], "dashboard": SonarDashboard }

alertRows (~147 rows, newest first) are drawn from the REAL generated raw
files inside a 6-minute display window ending at the scenario's `feed_end`:
HIPMON alerts, Kafka lag rows, Splunk alerts, Workato job failures, Apigee
5xx rows and (pinned, from earlier) the latest Sonar hourly critical report.
The buried first-symptom row (isFirstSymptom, from anchors.json) and the
latest occurrence of each of the two standing-noise rules (isNoise) are
always pinned in, even when they fall outside the window. Remaining slots are
filled with quiet filler rows (ruleId '-' as an em dash, P4): normal Sonar
exchange lines, host/pod metric samples, zero-lag Kafka samples, successful
Workato jobs and low-count Apigee errors.

dashboard: KPI tiles are computed from the generated exchange records and
scaled to a realistic day (see SCALE / TOTALS); ~40 exchangeRows are the
latest Sonar state per exchange.id at feed_end (anomalous ones first, then
the most recent ordinary ones); traceFocus is the focal exchange's own trace.

Run after generate.py, normalise.py and find_anchors.py. Standard library only.
"""
import json
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "generator"))
import naming  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

DATA_DIR = os.path.join(REPO_ROOT, "data")
OUT_DIR = os.path.join(REPO_ROOT, "app", "src", "data")
UTC = timezone.utc
FILLER = "—"  # em dash: ruleId for filler rows (the UI dims these)
TARGET_ROWS = 147
WINDOW_MIN = 6
XID_RE = re.compile(r"^(\d{24}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")

# Dashboard scaling: each generated (sampled) FAILED / REPLAYED exchange line
# stands for SCALE real exchanges; the rest of the 24 h day is the estate's
# normal profile. Day totals differ slightly per scenario.
SCALE = 9
TOTALS = {"s1": 975_099, "s2": 981_340, "s3": 968_777, "s4": 972_015, "s5": 958_224}
BASE_FAIL_RATE, BASE_WARN_RATE, BASE_REPL_RATE = 0.0228, 0.0072, 0.0031
BASE_INPROG = 410
BASE_AVG_MS = 2140
HF_PER_EXCHANGE = 3.86
WAITERS = {"GLBL_SCHEDULER_WAITFORFILE"}


def pdt(s):
    return datetime.fromisoformat(s)


def hm(s):
    return datetime.strptime(f"{naming.DATE} {s}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def read_ndjson(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def sev_lag(lag):
    return "P1" if lag >= 100_000 else "P2" if lag >= 10_000 else "P3" if lag >= 1_000 else "P4"


def sev_num(n):
    return f"P{min(max(int(n), 1), 4)}"


def fmt_dur(ms):
    ms = float(ms)
    if ms < 1000:
        return f"{int(ms)} ms"
    if ms < 60_000:
        return f"{ms / 1000:.2f} s"
    if ms < 3_600_000:
        return f"{ms / 60_000:.1f} min"
    return f"{ms / 3_600_000:.1f} h"


def project_of_halfflow(hf):
    return naming.halfflow_project(hf) or hf


# --------------------------------------------------------------------------
# alertRows
# --------------------------------------------------------------------------

def in_scope(sc, project=None, component=None):
    s = sc["scope"]
    return (project in s["projects"]) or (component in s["components"])


def build_rows(sc, d, sonar, anchors, norm):
    rng = random.Random(f"feed:{sc['slug']}")
    end = hm(sc["feed_end"])
    start = end - timedelta(minutes=WINDOW_MIN)
    win = lambda dt: start <= dt <= end  # noqa: E731
    incident, filler = [], []

    def row(ts, source, rule, comp, msg, sev, corr=None, noise=False):
        return {"ts": iso(ts) if isinstance(ts, datetime) else ts, "source": source, "ruleId": rule, "component": comp,
                "message": msg, "severity": sev, "correlationId": corr, "isNoise": noise}

    # HIPMON
    for a in read_json(os.path.join(d, "hipmon-alerts.json")):
        ts = pdt(a["timestamp"])
        if win(ts):
            pr = int(a["priority"].split(" ")[0])
            incident.append(row(ts, "HIPMON", a["rule_id"], a["halfflow"], a["error_text"], sev_num(pr),
                                a.get("exchange.id") or None))
    # Kafka
    zero_by_min = []
    lag_rows = defaultdict(list)
    import csv
    with open(os.path.join(d, "kafka-lag.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            ts = pdt(r["timestamp"])
            if not win(ts):
                continue
            group = r["topic"].split("process-int-")[1].rsplit(".v1", 1)[0]
            lag = int(r["lag"])
            comp = f"process-int-{group}"
            if lag >= 1000:
                lag_rows[group].append(row(ts, "Kafka", "KFK-LAG-004", comp, f"lag {lag:,}", sev_lag(lag)))
            else:
                zero_by_min.append(row(ts, "Kafka", FILLER, comp, f"lag {lag:,}", "P4"))
    for g, rs in lag_rows.items():  # thin to every 4th sample (one a minute)
        incident.extend(rs[::4])
    # Splunk
    noise_latest = {}
    noise_ids = {n["rule_id"] for n in naming.STANDING_NOISE}
    for r in read_ndjson(os.path.join(d, "splunk-hosts.ndjson")):
        ts = pdt(r["@timestamp"])
        comp = r.get("pod") or r["host"]
        if r["kind"] == "alert":
            noise = r["rule_id"] in noise_ids
            rr = row(ts, "Splunk", r["rule_id"], comp, r["message"], sev_num(r["severity"]), None, noise)
            if noise and ts <= end:
                noise_latest[r["rule_id"]] = rr
            if win(ts) and not noise:
                incident.append(rr)
        elif win(ts) and r["kind"] in ("metric", "health", "event", "job"):
            filler.append(row(ts, "Splunk", FILLER, comp, r["message"] if r["kind"] != "metric" else
                              f"{r['metric']} {r['value']}%", "P4"))
    # Workato
    for j in read_json(os.path.join(d, "workato-jobs.json")):
        ts = pdt(j["ended_at"])
        if not win(ts):
            continue
        if j["status"] == "failed":
            incident.append(row(ts, "Workato", "WKT-JOBFAIL-001", j["recipe"], j["error"], "P3", j.get("exchange_id")))
        else:
            filler.append(row(ts, "Workato", FILLER, j["recipe"], f"job {j['job_id']} succeeded ({j['duration_ms']} ms)", "P4"))
    # Apigee
    for a in read_json(os.path.join(d, "apigee-errors.json")):
        ts = pdt(a["minute"])
        if not win(ts):
            continue
        ids = a.get("sample_exchange_ids") or [None]
        if a["status"] >= 500 and a["count"] >= 10:
            incident.append(row(ts, "Apigee", "APG-5XX-012", a["endpoint"],
                                f"{a['status']} x{a['count']} in 1 min, p99 {a['p99_latency_ms']} ms", "P2", ids[0]))
        else:
            filler.append(row(ts, "Apigee", FILLER, a["endpoint"], f"{a['status']} x{a['count']}, p99 {a['p99_latency_ms']} ms", "P4"))
    # Sonar: hourly reports (rule) + quiet exchange lines (filler)
    latest_hourly = None
    for r in sonar:
        ts = pdt(r["@timestamp"])
        if r["exchange"] == "GLBL_MSTR_HLTH_CHK":
            if r["exchange.status"] == "WARNING" and ts <= end and end - ts <= timedelta(minutes=90):
                m = re.search(r"InProgress=([\d,]+) Failed=([\d,]+)", r["message"])
                latest_hourly = row(ts, "SONAR", "SNR-HRLY-CRIT", "GLBL_MSTR_HLTH_CHK",
                                    f"{m.group(1)} InProgress, {m.group(2)} Failed", "P2")
            continue
        if not win(ts) or r["project"] == "SONAR-OPS" or r["event.code"] == "IFP_HBT001":
            continue
        if r["exchange.status"] in ("COMPLETE", "COMPLETE (F)", "WARNING") and r["event.level"] in ("EXITINFO", "INFO"):
            msg = r["message"] if r["exchange.status"] == "WARNING" else f"{r['exchange.status']} {r['duration']} ms"
            filler.append(row(ts, "SONAR", FILLER, r["halfflow"], msg, "P4", r["exchange.id"] if XID_RE.match(r["exchange.id"]) else None))
    if latest_hourly and not win(pdt(latest_hourly["ts"])):
        incident.append(latest_hourly)
    elif latest_hourly:
        incident.append(latest_hourly)

    # pinned: standing noise (latest occurrence of each rule at or before feed_end)
    noise_rows = []
    for rid, rr in noise_latest.items():
        noise_rows.append(rr)
    # pinned: first symptom from anchors.json
    fs = next(e for e in norm if e["event_id"] == anchors["first_symptom"])
    fs_sev = sev_num(fs["severity"]) if fs["kind"] == "rule_hit" else "P4"
    fs_row = row(pdt(fs["ts"]), fs["source"], fs.get("rule_id") or FILLER, fs["component"], fs["description"], fs_sev,
                 fs["correlation_id"])
    fs_row["isFirstSymptom"] = True

    rows = list(incident)
    # drop any duplicate of the first symptom already selected
    rows = [r for r in rows if not (r["ts"] == fs_row["ts"] and r["message"] == fs_row["message"])]
    pinned = [fs_row] + [n for n in noise_rows if n["ts"] not in {r["ts"] for r in rows if r["ruleId"] == n["ruleId"]}]
    # keep any in-window noise rows that were skipped above
    # cap incident rows so filler and pinned still fit
    cap = TARGET_ROWS - len(pinned) - 20
    if len(rows) > cap:
        rng.shuffle(rows)
        keep = [r for r in rows if r["source"] != "Kafka"][:cap]
        kafka = [r for r in rows if r["source"] == "Kafka"]
        room = cap - len(keep)
        rows = keep + kafka[:max(room, 0)]
    rows = rows + pinned
    need = TARGET_ROWS - len(rows)
    rng.shuffle(filler)
    zero_cap = max(0, int(need * 0.3))
    rng.shuffle(zero_by_min)
    picks = []
    nonkafka = [f for f in filler]
    picks.extend(zero_by_min[:zero_cap])
    picks.extend(nonkafka[:max(0, need - len(picks))])
    if len(picks) < need:
        picks.extend(zero_by_min[zero_cap:zero_cap + (need - len(picks))])
    rows += picks[:need]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    for r in rows:
        if r.get("correlationId") is None:
            r["correlationId"] = None
        if not r.get("isNoise"):
            r["isNoise"] = False
    return rows


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

def exchange_states(sonar, upto):
    by = defaultdict(list)
    for r in sonar:
        if XID_RE.match(r["exchange.id"]) and pdt(r["@timestamp"]) <= upto:
            by[r["exchange.id"]].append(r)
    states = []
    for xid, lines in by.items():
        lines.sort(key=lambda r: r["@timestamp"])
        last = lines[-1]
        lt = pdt(last["@timestamp"])
        status = last["exchange.status"]
        if status == "INPROGRESS":
            dur = last["duration"] + int((upto - lt).total_seconds() * 1000)
        else:
            dur = max(l["duration"] for l in lines)
        states.append({"xid": xid, "last": last, "ts": last["@timestamp"], "status": status, "dur": dur,
                       "first_ts": lines[0]["@timestamp"], "n": len(lines)})
    return states


def kpi_block(total, inprog, complete, warning, failed, replayed, avg_ms, max_ms):
    return {"exchanges": total, "inprogress": inprog, "complete": complete, "warning": warning, "failed": failed,
            "replayed": replayed, "failurePct": round(failed / total * 100, 2), "durationAvg": fmt_dur(avg_ms),
            "durationMax": fmt_dur(max_ms)}


def build_dashboard(sc, sonar, norm_late=None):
    end = hm(sc["feed_end"])
    states = exchange_states(sonar, end)
    scope_proj = set(sc["scope"]["projects"]) - {"SONAR-OPS"}
    total = TOTALS[sc["id"]]

    # deficit of expected inbound (S2): sum of baseline - count over PI7 volume records
    deficit = 0
    for r in sonar:
        if r["exchange"] == "GLBL_MSTR_VOLUME_CHK" and "PI7 hub" in r["message"] and pdt(r["@timestamp"]) <= end:
            m = re.search(r": ([\d,]+) \(baseline ([\d,]+)\)", r["message"])
            deficit += max(0, int(m.group(2).replace(",", "")) - int(m.group(1).replace(",", "")))
    total -= deficit

    # latest InProgress figure from the hourly critical report at or before feed_end
    inprog = BASE_INPROG
    for r in sonar:
        if r["exchange"] == "GLBL_MSTR_HLTH_CHK" and pdt(r["@timestamp"]) <= end:
            m = re.search(r"InProgress=([\d,]+)", r["message"])
            inprog = int(m.group(1).replace(",", ""))
    failed_lines = [s for s in states if s["status"] == "FAILED" and s["last"]["project"] in scope_proj]
    repl_lines = [s for s in states if s["status"] == "REPLAYED"]
    failed = round(total * BASE_FAIL_RATE) + len(failed_lines) * SCALE
    replayed = round(total * BASE_REPL_RATE) + len(repl_lines) * SCALE
    warning = round(total * BASE_WARN_RATE)
    complete = total - inprog - failed - warning - replayed
    stuck = [s for s in states if s["status"] == "INPROGRESS" and s["last"]["exchange"] not in WAITERS
             and s["last"]["project"] in scope_proj]
    extra_inprog = max(0, inprog - BASE_INPROG - 60) if stuck else 0
    avg_age = (sum(s["dur"] for s in stuck) / len(stuck)) if stuck else 0
    avg_ms = BASE_AVG_MS + extra_inprog * avg_age / total
    non_wait = [s for s in states if s["last"]["exchange"] not in WAITERS]
    max_ms = max(s["dur"] for s in non_wait)
    exch = kpi_block(total, inprog, complete, warning, failed, replayed, avg_ms, max_ms)
    ht = int(total * HF_PER_EXCHANGE)
    hf_failed = int(failed * 1.12)
    hf_inprog = int(inprog * 1.04)
    hf_warn = int(warning * 1.3)
    hf_repl = int(replayed * 1.05)
    hf = kpi_block(ht, hf_inprog, ht - hf_inprog - hf_failed - hf_warn - hf_repl, hf_warn, hf_failed, hf_repl,
                   BASE_AVG_MS * 0.21 + extra_inprog * avg_age / ht, max_ms)

    # ---- exchange rows (~40) ----
    def to_row(s, anomalous):
        l = s["last"]
        return {"ts": l["@timestamp"], "status": s["status"], "project": l["project"], "exchange": l["exchange"],
                "exchangeId": s["xid"], "halfflowCount": l["halfflow.count"], "halfflowMissing": l["halfflow.missing"],
                "durationMs": int(s["dur"]), "source": l["source"], "destination": l["destination"],
                "objectId": l["object.id"], "objectName": l["object.name"], "eventCode": l["event.code"],
                "businessValue": l["business.value"], "frameworkVersion": l["framework.version"],
                **({"isAnomalous": True} if anomalous else {})}

    focal_name = sc["focal_exchange"]
    anomalous = [s for s in states if s["last"]["project"] in scope_proj and s["last"]["exchange"] not in WAITERS
                 and s["status"] in ("INPROGRESS", "FAILED", "REPLAYED", "WARNING")]
    anomalous.sort(key=lambda s: s["ts"], reverse=True)
    pin = [s for s in anomalous if s["last"]["exchange"] == focal_name and s["status"] == "INPROGRESS"]
    long_running = sorted([s for s in anomalous if s["status"] == "INPROGRESS"], key=lambda s: -s["dur"])[:1]
    chosen = []
    seen = set()
    for s in long_running + anomalous:
        if s["xid"] not in seen and len(chosen) < 22:
            chosen.append(s)
            seen.add(s["xid"])
    # focal exchange (S2: last CE exchange, complete but the last one) always present
    fx_states = [s for s in states if s["last"]["exchange"] == focal_name]
    if fx_states and sc.get("watch", {}).get("silence"):  # S2: the LAST exchange from the silent source is the evidence
        last_fx = max(fx_states, key=lambda s: s["ts"])
        if last_fx["xid"] not in seen:
            chosen.append(last_fx)
            seen.add(last_fx["xid"])
    ordinary = [s for s in states if s["xid"] not in seen and s["last"]["exchange"] not in WAITERS
                and s["last"]["project"] != "SONAR-OPS"]
    ordinary.sort(key=lambda s: s["ts"], reverse=True)
    rows = [to_row(s, True) for s in chosen]
    for s in ordinary:
        if len(rows) >= 40:
            break
        rows.append(to_row(s, False))
    rows.sort(key=lambda r: r["ts"], reverse=True)

    # ---- trace focus ----
    cands = defaultdict(int)
    for r in sonar:
        if r["exchange"] == focal_name and XID_RE.match(r["exchange.id"]):
            cands[r["exchange.id"]] += 1
    fxid = max(cands, key=lambda k: (cands[k], k))
    trace = []
    for r in sorted((r for r in sonar if r["exchange.id"] == fxid), key=lambda r: r["@timestamp"]):
        trace.append({"ts": r["@timestamp"], "level": r["event.level"], "exchange": r["exchange"], "exchangeId": r["exchange.id"],
                      "halfflow": r["halfflow"], "halfflowId": r["halfflow.id"], "application": r["application"],
                      "eventCode": r["event.code"], "eventReason": r["event.reason"], "message": r["message"],
                      "businessValue": r["business.value"]})
    return {"windowLabel": "Last 24 hours", "exchangeKpis": exch, "halfflowKpis": hf, "exchangeRows": rows,
            "traceFocus": {"exchange": focal_name, "exchangeId": fxid, "rows": trace}}


def build(sc):
    d = os.path.join(DATA_DIR, sc["slug"])
    sonar = read_ndjson(os.path.join(d, "sonar-exchanges.ndjson"))
    anchors = read_json(os.path.join(d, "anchors.json"))
    norm = read_json(os.path.join(d, "normalised-events.json"))
    alert_rows = build_rows(sc, d, sonar, anchors, norm)
    dash = build_dashboard(sc, sonar)
    out_dir = os.path.join(OUT_DIR, sc["slug"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "alert-feed.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"alertRows": alert_rows, "dashboard": dash}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    by_src = defaultdict(int)
    for r in alert_rows:
        by_src[r["source"]] += 1
    k = dash["exchangeKpis"]
    print(f"[{sc['slug']}] alertRows={len(alert_rows)} noise={sum(1 for r in alert_rows if r['isNoise'])} "
          f"firstSymptom={sum(1 for r in alert_rows if r.get('isFirstSymptom'))} incidentRuleRows="
          f"{sum(1 for r in alert_rows if r['ruleId'] != FILLER and not r['isNoise'])} {dict(by_src)}")
    print(f"    KPIs exchanges={k['exchanges']:,} inprogress={k['inprogress']:,} failed={k['failed']:,} "
          f"({k['failurePct']}%) replayed={k['replayed']:,} avg={k['durationAvg']} max={k['durationMax']} "
          f"exchangeRows={len(dash['exchangeRows'])} traceRows={len(dash['traceFocus']['rows'])}")


def main():
    for sc in SCENARIOS:
        build(sc)


if __name__ == "__main__":
    main()
