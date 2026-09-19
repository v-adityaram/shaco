#!/usr/bin/env python3
"""
normaliser/normalise.py -- deterministic, mechanical normalisation layer.

Standard library only. For each scenario under data/<slug>/ this parses the
raw source files and emits

    data/<slug>/normalised-events.json      chronologically sorted, stable ids e-0001...
    data/<slug>/late-event-normalised.json  the single withheld late event (e-late-0001)
    normaliser/cmdb-aliases.json            the alias map (auditable artefact)

NormalisedEvent = { event_id, ts (ISO UTC), source, component, severity 1-4,
                    description, correlation_id, kind: rule_hit|context,
                    rule_id? (required for rule_hit), raw_ref }

kind
  rule_hit  something a rule / monitor ALREADY fired: HIPMON [AUTO] alerts,
            Splunk threshold alerts, Kafka-lag rule hits (lag >= 1,000),
            Sonar hourly critical-exchange rows that breached (InProgress >=
            1,000 or Failed >= 25), Workato job-failure alerts, Apigee 5xx
            rules (>= 10 in a minute), ServiceNow incidents (SNOW-AUTO /
            SNOW-USER).
  context   everything an analyst would pull up around the hits: Sonar
            exchange/half-flow lines, counts, metric samples, Kafka lag
            samples, MFT rows, change / vendor records, heartbeats.

Code-computed context events (the AI is never asked to find these in raw noise):
  * volume records / "0 (baseline 180)" style counts           (Sonar VOLUME_CHK)
  * silence detector: no exchange created for a watched flow   (S2)
  * heartbeat absence                                          (S2)
  * stalled-exchange summaries: INPROGRESS, missing half-flow  (S1, S4)
  * failed-exchange groups by identical event.reason            (S3, S5)
  * partial-success watch (some IDocs still succeed)            (S3)
  * Kafka 5-min lag summaries incl. "0 on all N other groups"
  * metric samples with baseline mean (first 60 min) and delta

Time handling: everything is converted to UTC. The MFT file is the one
source with LOCAL time and NO offset (FRHIPG* hosts run Europe/Paris, CEST =
UTC+2 in September); MFT_LOCAL_OFFSET below undoes that.
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "generator"))
import naming  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
NORMALISER_DIR = os.path.dirname(os.path.abspath(__file__))
UTC = timezone.utc
MFT_LOCAL_OFFSET = timedelta(hours=2)
ALIAS_MAP = naming.alias_map()
XID_RE = re.compile(r"\b(\d{24}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")
KNOWN_LONG_RUNNERS = {"GLBL_SCHEDULER_WAITFORFILE", "GLBL_CTRLM_MASTERDATA_BATCH"}
_ALIAS_KEYS = sorted(ALIAS_MAP, key=len, reverse=True)


def resolve_component(*cands):
    """CMDB name for the first candidate that maps (exact, then longest prefix)."""
    for c in cands:
        if not c:
            continue
        if c in ALIAS_MAP:
            return ALIAS_MAP[c]
        for k in _ALIAS_KEYS:
            if c.startswith(k + "-") or c.startswith(k + "_"):
                return ALIAS_MAP[k]
    for c in cands:
        if c:
            return c
    return "unknown"


def pdt(s):
    return datetime.fromisoformat(s)


def ts_iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def local_naive_to_utc(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) - MFT_LOCAL_OFFSET


def sev_from_lag(lag):
    return 1 if lag >= 50_000 else 2 if lag >= 10_000 else 3 if lag >= 1_000 else 4


def xid_or_none(s):
    return s if s and XID_RE.fullmatch(s) else None


def read_ndjson(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def read_json(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Out:
    def __init__(self):
        self.ev = []

    def add(self, ts, source, component, severity, desc, corr, kind, rule_id=None, raw_ref=None):
        assert kind in ("rule_hit", "context")
        if kind == "rule_hit":
            assert rule_id
        self.ev.append({"ts": ts, "source": source, "component": component, "severity": severity,
                        "description": desc, "correlation_id": corr, "kind": kind, "rule_id": rule_id,
                        "raw_ref": raw_ref})


# --------------------------------------------------------------------------
# Sonar
# --------------------------------------------------------------------------

def parse_sonar(o, d, sc):
    fn = "sonar-exchanges.ndjson"
    rows = read_ndjson(os.path.join(d, fn))
    for r in rows:
        r["_dt"] = pdt(r["@timestamp"])
    watch = sc.get("watch", {})

    # ---- group by exchange id for stall detection ----
    by_x = defaultdict(list)
    for i, r in enumerate(rows):
        r["_i"] = i
        by_x[r["exchange.id"]].append(r)
    end_dt = max(r["_dt"] for r in rows)

    stalled = []
    for xid, lines in by_x.items():
        if not XID_RE.fullmatch(xid):
            continue
        lines.sort(key=lambda r: r["_dt"])
        last = lines[-1]
        if last["exchange.status"] == "INPROGRESS" and last["exchange"] not in KNOWN_LONG_RUNNERS:
            stalled.append((lines[0]["_dt"], lines[-1]["_dt"], xid, lines))

    stalled_ids = {s[2] for s in stalled}
    few = len(stalled) <= 5

    # ---- per-line events ----
    for r in rows:
        ex = r["exchange"]
        xid = xid_or_none(r["exchange.id"])
        comp = resolve_component(r["project"], r["halfflow"])
        base_ref = {"file": fn, "line": r["_i"] + 1}
        st, lvl = r["exchange.status"], r["event.level"]
        if ex == "GLBL_MSTR_HLTH_CHK":
            hit = st == "WARNING"
            o.add(r["_dt"], "SONAR", "SONAR-OPS", 2 if hit else 4, r["message"], None,
                  "rule_hit" if hit else "context", "SNR-HRLY-CRIT" if hit else None, base_ref)
        elif ex == "GLBL_MSTR_VOLUME_CHK":
            m = re.match(r"(.*) in last 5 min: ([\d,]+) \(baseline ([\d,]+)\)", r["message"])
            cnt, base = int(m.group(2).replace(",", "")), int(m.group(3).replace(",", ""))
            dev = abs(cnt - base) / max(base, 1)
            hub_ce = "hub CE" in r["message"]
            if dev >= 0.3 or r["_dt"].minute % 15 == 0 or "payload" in r["message"] and r["_dt"].minute % 10 == 0:
                o.add(r["_dt"], "SONAR", "SONAR-OPS", 2 if dev >= 0.9 else 3 if dev >= 0.3 else 4, r["message"], None,
                      "context", raw_ref=base_ref)
        elif r["event.code"] == "IFP_HBT001":
            pass  # heartbeat series handled below
        elif ex in ("GLBL_MSTR_REPLAY", "GLBL_SAPS4HANA_STO_BATCH_IN"):
            o.add(r["_dt"], "SONAR", comp, 3, f"{ex}: {r['message']}", None, "context", raw_ref=base_ref)
        elif st == "FAILED":
            desc = (f"{ex} / {r['halfflow']} FAILED at halfflow {r['halfflow.missing']}: {r['event.reason']} "
                    f"[{r['object.name']} {r['object.id']}, exchange.id {r['exchange.id']}]")
            o.add(r["_dt"], "SONAR", comp, 2, desc, xid, "context", raw_ref=base_ref)
        elif st == "REPLAYED":
            o.add(r["_dt"], "SONAR", comp, 4,
                  f"{ex} / {r['halfflow']} REPLAYED: {r['message']} [exchange.id {r['exchange.id']}]", xid,
                  "context", raw_ref=base_ref)
        elif xid in stalled_ids and few:
            o.add(r["_dt"], "SONAR", comp, 3,
                  f"{ex} / {r['halfflow']} {lvl} status {st}, halfflow.count {r['halfflow.count']}, "
                  f"halfflow.missing {r['halfflow.missing']}: {r['message']} [exchange.id {r['exchange.id']}]",
                  xid, "context", raw_ref=base_ref)
        for w in watch.get("success", []):
            if ex == w["exchange"] and st == "COMPLETE" and lvl == "EXITINFO" and r["_dt"] >= pdt(f"{naming.DATE}T{w['since']}+00:00"):
                o.add(r["_dt"], "SONAR", comp, 3,
                      f"{ex} exchange COMPLETE after the failures began (IDoc {r['object.id']}, {r['destination']}) "
                      f"[exchange.id {r['exchange.id']}]", xid, "context", raw_ref=base_ref)

    # ---- stalled exchange summaries (group by exchange name + missing) ----
    if stalled:
        first = min(s[0] for s in stalled)
        t = first.replace(second=0, microsecond=0)
        step = timedelta(minutes=15 if not few else 30)
        t = t + step
        while t <= end_dt:
            groups = defaultdict(list)
            for s0, s1, xid, lines in stalled:
                age = t - s0
                if s0 <= t and age >= timedelta(minutes=10):
                    latest = [l for l in lines if l["_dt"] <= t][-1]
                    if latest["exchange.status"] == "INPROGRESS":
                        groups[(latest["exchange"], latest["halfflow.missing"])].append((s0, xid, latest))
            for (exn, miss), items in sorted(groups.items()):
                items.sort()
                oldest = t - items[0][0]
                seen_hfs = sorted({l["halfflow"] for l in items[0][2:3]})
                tm = next((v for v in naming.EXCHANGES.values() if v["exchange"] == exn), None)
                nxt = int(miss.split("/")[0])
                exp_hf = tm["halfflows"][nxt - 1] if tm and nxt - 1 < len(tm["halfflows"]) else "?"
                last_evt = items[0][2]["@timestamp"][11:19]
                if len(items) == 1:
                    desc = (f"{exn}: exchange {items[0][1]} INPROGRESS at halfflow {miss} for "
                            f"{int(oldest.total_seconds() // 3600)}h{int(oldest.total_seconds() % 3600 // 60):02d}m; "
                            f"expected half-flow {exp_hf} has NO event (last event of this exchange {last_evt} UTC); "
                            f"exchange never turned FAILED")
                else:
                    ages = sorted((t - it[0]).total_seconds() / 60 for it in items)
                    desc = (f"{exn}: {len(items)} sampled exchanges INPROGRESS at halfflow {miss}, oldest "
                            f"{ages[-1]:.0f} min, youngest {ages[0]:.0f} min; none has exited half-flow {exp_hf}; "
                            f"e.g. exchange.id {items[0][1]}")
                o.add(t, "SONAR", resolve_component(items[0][2]["project"]), 3, desc, xid_or_none(items[0][1]),
                      "context", raw_ref={"file": fn, "computed": "stalled-exchange"})
            t += step

    # ---- failed-exchange groups by identical reason (5-min buckets) ----
    fails = [r for r in rows if r["exchange.status"] == "FAILED" and r["event.reason"]]
    if fails:
        b = defaultdict(list)
        for r in fails:
            k = r["_dt"].replace(minute=(r["_dt"].minute // 5) * 5, second=0, microsecond=0) + timedelta(minutes=5)
            b[(k, r["event.reason"])].append(r)
        seen_first = {}
        for (k, reason), items in sorted(b.items()):
            if len(items) < 8:
                continue
            all_items = [r for r in fails if r["event.reason"] == reason and r["_dt"] <= k]
            hfs = {r["halfflow"] for r in all_items}
            prj = sorted({r["project"] for r in all_items})
            first = min(r["_dt"] for r in all_items)
            desc = (f"{len(items)} exchanges FAILED in the 5 min to {k:%H:%M} with identical event.reason '{reason}'; "
                    f"cumulative since {first:%H:%M:%S}: {len(all_items)} failed exchanges across {len(hfs)} distinct half-flows "
                    f"in {len(prj)} projects ({', '.join(prj[:6])})")
            o.add(k, "SONAR", "SONAR-OPS", 2, desc, None, "context", raw_ref={"file": fn, "computed": "failed-by-reason"})

    # ---- partial-success watch (S3) ----
    for w in watch.get("success", []):
        since = pdt(f"{naming.DATE}T{w['since']}+00:00")
        t = since + timedelta(minutes=15)
        while t <= end_dt:
            tgt = [r for r in rows if r["exchange"] == w["exchange"] and r["event.level"] in ("EXITINFO", "ERROR")
                   and since <= r["_dt"] <= t]
            oth = [r for r in rows if r["exchange"].startswith(w["compare_prefix"]) and r["exchange"] != w["exchange"]
                   and r["event.level"] in ("EXITINFO", "ERROR") and since <= r["_dt"] <= t]
            ok, n = sum(1 for r in tgt if r["exchange.status"] == "COMPLETE"), len(tgt)
            ok2, n2 = sum(1 for r in oth if r["exchange.status"] == "COMPLETE"), len(oth)
            o.add(t, "SONAR", resolve_component(w["exchange"]), 2,
                  f"since {since:%H:%M}: {w['exchange']} {ok} of {n} exchanges COMPLETE (still succeeding intermittently); "
                  f"all other IDoc-out flows {ok2} of {n2} COMPLETE", None, "context",
                  raw_ref={"file": fn, "computed": "partial-success"})
            t += timedelta(minutes=15)

    # ---- silence detector (S2) ----
    for exn in watch.get("silence", []):
        ls = sorted((r for r in rows if r["exchange"] == exn), key=lambda r: r["_dt"])
        if not ls:
            continue
        typical = (ls[-1]["_dt"] - ls[0]["_dt"]).total_seconds() / max(len(ls) - 1, 1)
        last = ls[-1]
        for mins in (5, 15, 30, 60, 120, 180):
            t = last["_dt"] + timedelta(minutes=mins)
            if t <= end_dt:
                o.add(t, "SONAR", resolve_component(last["project"]), 2,
                      f"no {exn} exchange created for {mins} min; last exchange {last['exchange.id']} created at "
                      f"{last['@timestamp'][11:23]} UTC (before that one every ~{typical:.0f} s)", xid_or_none(last["exchange.id"]),
                      "context", raw_ref={"file": fn, "computed": "silence"})
        o.add(last["_dt"], "SONAR", resolve_component(last["project"]), 3,
              f"last {exn} exchange created at {last['@timestamp'][11:23]} UTC [exchange.id {last['exchange.id']}]",
              xid_or_none(last["exchange.id"]), "context", raw_ref={"file": fn, "line": last["_i"] + 1})

    # ---- heartbeat series + absence (S2) ----
    for app in watch.get("heartbeat", []):
        hb = sorted((r for r in rows if r["event.code"] == "IFP_HBT001" and r["exchange"] == app), key=lambda r: r["_dt"])
        if not hb:
            continue
        for r in hb:
            if r["_dt"].minute % 10 == 0 or r is hb[-1]:
                o.add(r["_dt"], "SONAR", resolve_component(app), 4 if r is not hb[-1] else 3,
                      f"{r['message']}" + ("  [LAST heartbeat received]" if r is hb[-1] else ""), None, "context",
                      raw_ref={"file": fn, "line": r["_i"] + 1})
        for mins in (5, 30, 120):
            t = hb[-1]["_dt"] + timedelta(minutes=mins)
            if t <= end_dt:
                o.add(t, "SONAR", resolve_component(app), 2,
                      f"{app} heartbeat absent for {mins} min: last heartbeat {hb[-1]['@timestamp'][11:19]} UTC "
                      f"(expected every 60 s)", None, "context", raw_ref={"file": fn, "computed": "heartbeat-absence"})


# --------------------------------------------------------------------------
# Other sources
# --------------------------------------------------------------------------

def parse_hipmon(o, d):
    fn = "hipmon-alerts.json"
    for i, a in enumerate(read_json(os.path.join(d, fn))):
        pr = int(a["priority"].split(" ")[0])
        sev = {1: 1, 2: 1, 3: 2, 4: 3}.get(pr, 4)
        o.add(pdt(a["timestamp"]), "HIPMON", resolve_component(a["project"], a["halfflow"]), sev,
              f"{a['subject']} -- {a['error_text']} (priority {a['priority']})", xid_or_none(a.get("exchange.id")),
              "rule_hit", a["rule_id"], {"file": fn, "index": i})


def parse_splunk(o, d, sc):
    fn = "splunk-hosts.ndjson"
    rows = read_ndjson(os.path.join(d, fn))
    series = defaultdict(list)
    for i, r in enumerate(rows):
        r["_i"], r["_dt"] = i, pdt(r["@timestamp"])
        if r["kind"] == "metric" and r.get("pod"):
            series[(r["pod"], r["metric"])].append(r)
    for i, r in enumerate(rows):
        dt = r["_dt"]
        comp = resolve_component(r.get("pod"), r["host"])
        ref = {"file": fn, "line": i + 1}
        if r["kind"] == "alert":
            o.add(dt, "Splunk", comp, r["severity"], r["message"], None, "rule_hit", r["rule_id"], ref)
        elif r["kind"] == "event" or r["kind"] == "job":
            o.add(dt, "Splunk", comp, r["severity"], f"{r['host']}: {r['message']}", None, "context", raw_ref=ref)
        elif r["kind"] == "health":
            if dt.minute % 15 == 2 or not r.get("pod"):
                o.add(dt, "Splunk", comp, 4, f"{r['host']}: {r['message']}", None, "context", raw_ref=ref)
        elif r["kind"] == "metric" and r.get("pod"):
            ser = series[(r["pod"], r["metric"])]
            t0 = ser[0]["_dt"]
            base_vals = [x["value"] for x in ser if x["_dt"] < t0 + timedelta(minutes=60)]
            base = sum(base_vals) / len(base_vals)
            delta = r["value"] - base
            if dt.minute % 10 == 0 and dt.second == 0 or (abs(delta) >= max(8, 0.15 * base) and dt.minute % 6 == 0):
                extra = []
                if "gc_pause_p99_ms" in r:
                    extra.append(f"GC pause p99 {r['gc_pause_p99_ms']} ms")
                if "cpu_pct" in r:
                    extra.append(f"CPU {r['cpu_pct']}%")
                if "threads" in r:
                    extra.append(f"threads {r['threads']}")
                if r.get("restart_count") is not None:
                    extra.append(f"restarts {r['restart_count']}")
                dev = abs(delta) >= max(8, 0.15 * base)
                o.add(dt, "Splunk", comp, 3 if dev and r["value"] >= 85 else 4,
                      f"{r['metric']} {r['value']}% on {r['pod']} (baseline mean {base:.1f}% over first 60 min, "
                      f"delta {delta:+.1f}); " + ", ".join(extra), None, "context", raw_ref=ref)


def parse_kafka(o, d):
    fn = "kafka-lag.csv"
    path = os.path.join(d, fn)
    buckets = defaultdict(dict)
    with open(path, encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            dt = pdt(row["timestamp"])
            if dt.second == 0 and dt.minute % 5 == 0:
                g = row["topic"].split("process-int-")[1].rsplit(".v1", 1)[0]
                buckets[dt][g] = (int(row["lag"]), i + 2)
    prev = {}
    for dt in sorted(buckets):
        b = buckets[dt]
        hot = {g: v[0] for g, v in b.items() if v[0] >= 1000}
        nz = {g: v[0] for g, v in b.items() if v[0] > 0}
        ref = {"file": fn, "row": min(v[1] for v in b.values())}
        if nz:
            parts = []
            for g, lag in sorted(nz.items(), key=lambda kv: -kv[1]):
                p = prev.get(g, 0)
                tr = "rising" if lag > p * 1.03 + 5 else "falling" if lag < p * 0.97 - 5 else "flat"
                parts.append(f"{g} {lag:,} ({tr})")
            others = len(b) - len(nz)
            desc = (f"consumer lag: {'; '.join(parts)}; lag 0 on {'all ' if others == len(b) - 0 else ''}{others} "
                    f"other processing group{'s' if others != 1 else ''}"
                    + (f" (of {len(b)})" if others else ""))
            mx = max(nz.values())
            if hot:
                o.add(dt, "Kafka", resolve_component(max(hot, key=hot.get)), sev_from_lag(mx), desc, None, "rule_hit",
                      "KFK-LAG-004", ref)
            elif dt.minute % 15 == 0:
                o.add(dt, "Kafka", resolve_component(max(nz, key=nz.get)), 4, desc, None, "context", raw_ref=ref)
        elif dt.minute % 15 == 0:
            o.add(dt, "Kafka", "CONFLUENT_EMEA", 4, f"consumer lag 0 on all {len(b)} processing groups; no growth on any topic",
                  None, "context", raw_ref=ref)
        prev = {g: v[0] for g, v in b.items()}


def parse_workato(o, d):
    fn = "workato-jobs.json"
    for i, j in enumerate(read_json(os.path.join(d, fn))):
        if j["status"] != "failed":
            continue
        o.add(pdt(j["ended_at"]), "Workato", "WORKATO_PLATFORM", 2,
              f"Workato job {j['job_id']} FAILED, recipe '{j['recipe']}': {j['error']}", xid_or_none(j.get("exchange_id")),
              "rule_hit", "WKT-JOBFAIL-001", {"file": fn, "index": i})


def parse_apigee(o, d):
    fn = "apigee-errors.json"
    for i, a in enumerate(read_json(os.path.join(d, fn))):
        if a["status"] >= 500 and a["count"] >= 10:
            ids = a.get("sample_exchange_ids") or [None]
            o.add(pdt(a["minute"]), "Apigee", "APIGEE_EDGE", 2,
                  f"Apigee {a['status']} x{a['count']} on {a['endpoint']} in 1 min (p99 {a['p99_latency_ms']} ms)",
                  xid_or_none(ids[0]), "rule_hit", "APG-5XX-012", {"file": fn, "index": i})


def parse_mft(o, d):
    fn = "mft-transfers.csv"
    with open(os.path.join(d, fn), encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            dec, act = int(row["declared_rows"]), int(row["actual_rows"])
            mism = dec != act
            desc = (f"{row['filename']} {row['source']}->{row['target']} status={row['status']} bytes={int(row['bytes']):,} "
                    f"declared_rows={dec:,} actual_rows={act:,}")
            if mism:
                desc += f"  ** ROW COUNT MISMATCH: declared {dec:,} != actual {act:,} while status is {row['status']} **"
            o.add(local_naive_to_utc(row["start_time"]), "MFT", resolve_component(row["source"], row["target"]),
                  3 if mism else 4, desc, xid_or_none(row["exchange_id"]), "context", raw_ref={"file": fn, "row": i + 2})


def parse_servicenow(o, d):
    fn = "servicenow-incidents.json"
    for i, r in enumerate(read_json(os.path.join(d, fn))):
        prio = int(r["priority"]) if isinstance(r["priority"], int) else int(str(r["priority"])[0])
        m = XID_RE.search(r["description"]) or XID_RE.search(r["short_description"])
        desc = (f"{r['number']} ({r['channel']}, priority {prio}, {r['assignment_group']}"
                + (f", child of {r['parent']}" if r.get("parent") else "") + f"): {r['short_description']} -- {r['description']}")
        o.add(pdt(r["opened_at"]), "ServiceNow", "HIP-INCIDENT-L2",
              1 if prio <= 1 else 2 if prio == 2 else 3, desc[:420], m.group(1) if m else None, "rule_hit",
              "SNOW-AUTO" if r["channel"] == "auto" else "SNOW-USER", {"file": fn, "index": i})
        for u in r.get("updates", []):
            o.add(pdt(u["ts"]), "ServiceNow", "HIP-INCIDENT-L2", 2,
                  f"{r['number']} {u['field']} changed to '{u['value']}'", None, "context", raw_ref={"file": fn, "index": i})
        for n in r.get("work_notes", []):
            o.add(pdt(n["ts"]), "ServiceNow", "HIP-INCIDENT-L2", 4, f"{r['number']} work note: {n['note']}", None,
                  "context", raw_ref={"file": fn, "index": i})


def parse_changes(o, d):
    fn = "change-records.json"
    for i, c in enumerate(read_json(os.path.join(d, fn))):
        vendor = c["type"] == "Vendor Notice"
        desc = (f"{c['change_number']} ({c['type']}): {c['description']} [component {c['component']}, implementer "
                f"{c['implementer']}, approval: {c['approval_state']}]")
        sev = 2 if vendor else 3 if "patching" in c["description"].lower() else 4
        o.add(pdt(c["implemented_at"]), "Change", resolve_component(c["component"]), sev, desc, None, "context",
              raw_ref={"file": fn, "index": i})


def parse_late(d):
    rows = read_ndjson(os.path.join(d, "late-evidence.ndjson"))
    if not rows:
        return None
    r = rows[0]
    src = {"SONAR": "SONAR", "SPLUNK": "Splunk", "Change": "Change", "MFT": "MFT"}.get(r["source"], r["source"])
    return {"event_id": "e-late-0001", "ts": ts_iso(pdt(r["@timestamp"])), "source": src,
            "component": resolve_component(r["component"]), "severity": r["severity"], "description": r["message"],
            "correlation_id": r.get("correlation_id"), "kind": "context", "rule_id": None,
            "raw_ref": {"file": "late-evidence.ndjson", "line": 1}}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

SRC_ORDER = {"Change": 0, "Splunk": 1, "SONAR": 2, "Kafka": 3, "Workato": 4, "Apigee": 5, "MFT": 6, "HIPMON": 7, "ServiceNow": 8}


def normalise_scenario(sc):
    d = os.path.join(DATA_DIR, sc["slug"])
    o = Out()
    parse_sonar(o, d, sc)
    parse_hipmon(o, d)
    parse_splunk(o, d, sc)
    parse_kafka(o, d)
    parse_workato(o, d)
    parse_apigee(o, d)
    parse_mft(o, d)
    parse_servicenow(o, d)
    parse_changes(o, d)
    evs = sorted(enumerate(o.ev), key=lambda p: (p[1]["ts"], SRC_ORDER.get(p[1]["source"], 9), p[0]))
    out = []
    for n, (_, e) in enumerate(evs, start=1):
        out.append({"event_id": f"e-{n:04d}", "ts": ts_iso(e["ts"]), "source": e["source"], "component": e["component"],
                    "severity": e["severity"], "description": e["description"], "correlation_id": e["correlation_id"],
                    "kind": e["kind"], "rule_id": e["rule_id"], "raw_ref": e["raw_ref"]})
    for e in out:
        if e["rule_id"] is None:
            del e["rule_id"]
    with open(os.path.join(d, "normalised-events.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    late = parse_late(d)
    if late is None:
        raise SystemExit(f"[{sc['slug']}] no late-evidence.ndjson")
    if late["rule_id"] is None:
        del late["rule_id"]
    with open(os.path.join(d, "late-event-normalised.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(late, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out, late


def main():
    with open(os.path.join(NORMALISER_DIR, "cmdb-aliases.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(ALIAS_MAP, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    for sc in SCENARIOS:
        evs, late = normalise_scenario(sc)
        hits = sum(1 for e in evs if e["kind"] == "rule_hit")
        by_src = defaultdict(int)
        for e in evs:
            by_src[e["source"]] += 1
        print(f"[{sc['slug']}] events={len(evs)} rule_hit={hits} context={len(evs) - hits} "
              f"range={evs[0]['ts']} -> {evs[-1]['ts']} {dict(sorted(by_src.items()))} late={late['ts']}")


if __name__ == "__main__":
    main()
