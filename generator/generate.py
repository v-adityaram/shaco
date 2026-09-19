#!/usr/bin/env python3
"""
generator/generate.py -- deterministic raw-signal generator for the
"Incident Response AI" POC (HIP estate, plan v2 section 7).

Standard library only. Each scenario has its own seeded RNG
(random.Random("<SEED>:<slug>")) so output is byte-identical across runs.
Writes into data/<slug>/:

    sonar-exchanges.ndjson   Sonar field names (@timestamp, exchange.status, ...)
    kafka-lag.csv            15 s buckets, one row per processing-group topic
    splunk-hosts.ndjson      host/pod metrics + threshold alerts + events
    hipmon-alerts.json       [AUTO] rule hits
    workato-jobs.json        recipe job records
    apigee-errors.json       per-minute error aggregates
    mft-transfers.csv        LOCAL time, NO offset (FRHIPG* hosts run CEST = UTC+2)
    servicenow-incidents.json
    change-records.json      (+ vendor-notice records, six unrelated chaff changes)
    late-evidence.ndjson     withheld until the "inject delayed log" closer

Sonar lines are a SAMPLED exchange log (1 line per background exchange);
per-5-minute GLBL_MSTR_VOLUME_CHK records carry the true volumes. The
decisive evidence for every scenario is real, checkable data in these
files. This module does no diagnosis.
"""

import csv
import io
import json
import math
import os
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naming  # noqa: E402
from naming import EXCHANGES  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
SEED = 20260918
UTC = timezone.utc
MFT_LOCAL_OFFSET = timedelta(hours=2)  # FRHIPG* MFT hosts: Europe/Paris, CEST in September

SPECIAL = {"waitfile", "slowbatch", "bpm_fm", "onereadsoft", "futurmaster", "frcpd_fkf"}
CRITICAL = {k for k in EXCHANGES if k.startswith(("idoc_", "pi7_", "sapit_", "kepler_", "procout_", "amz_"))}
CRITICAL |= {"asn", "bpm_fm", "manh_ship"}

BG_FAILS = [
    ("MAP002", "Mapping error: required field 'Plant' missing in source payload", 1),
    ("TEC01", "Timeout waiting for response from target after 60000 ms", 2),
    ("COM01", "Unable to connect to target: Read timed out", 3),
    ("PRC003", "Duplicate message detected for business key", 1),
    ("RTG003", "No route found for message", 0),
    ("GEN01", "HTTP 503 from target", 3),
    ("IVK003", "Invoke failed: SOAP fault from target service", 2),
]

APIGEE_ENDPOINTS = ["/hip/v1/salesorders", "/hip/v1/customers", "/hip/v1/shipments", "/hip/v1/orders/confirm",
                    "/hip/v1/stock", "/hip/v1/invoices", "/hip/v1/deliveries", "/hip/v1/consent/enrol",
                    "/hip/v1/returns", "/hip/v1/asn"]

CHAFF = [
    ("KEPLER_NEXTGEN", "Renew TLS certificate on hip-kepler-ng-out ingress", "Standard", "Re-import previous certificate"),
    ("SGLORHIPPETLPC1", "Extend Control-M calendar for month-end ETL jobs", "Standard", "Restore previous calendar"),
    ("eConsent", "Apigee proxy eConsent v3: quota policy update (200 -> 250 rpm)", "Normal", "Revert proxy revision"),
    ("USAMRHIPDFTSI01", "Purge old SFG archive on dev MFT host", "Standard", "n/a"),
    ("MANHATTAN_WMS", "Manhattan EMEA scheduled stock report time change", "Standard", "Restore previous schedule"),
    ("FRHIPGQAMFTSI01", "OS patch level update on QA MFT host", "Normal", "Snapshot restore"),
    ("CONFLUENT_EMEA", "Rotate Schema Registry API keys", "Standard", "Re-issue previous keys"),
    ("SAPTR_FOM", "Deploy mapping v3.4.1 minor fix for FOM inventory SG flow", "Normal", "Redeploy v3.4.0"),
    ("FRHIPGPPMFTSI01", "Renew Splunk forwarder certificate", "Standard", "Re-import previous certificate"),
    ("SFDC_CX", "Decommission legacy half-flow EMEA_LEGACY_ORDERS_01_ESB", "Normal", "Redeploy archived EAR"),
    ("AKS-HIP-EMEA-PRD", "Autoscaler max nodes 12 -> 14 for the batch node pool", "Standard", "Revert autoscaler config"),
    ("WORKATO_PLATFORM", "Enable new recipe 'Salesforce Case Sync' in sandbox project", "Standard", "Disable recipe"),
]
CHAFF_AVOID = {"s5": {"AKS-HIP-EMEA-PRD"}, "s3": {"WORKATO_PLATFORM"}, "s4": {"FRHIPGPPMFTSI01", "USAMRHIPDFTSI01"}}


# --------------------------------------------------------------------------
# Time / formatting helpers
# --------------------------------------------------------------------------

def T(hms, date=naming.DATE):
    if hms.count(":") == 1:
        hms += ":00"
    return datetime.strptime(f"{date} {hms}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+00:00"


def iso_s(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def local_naive(dt):
    return (dt + MFT_LOCAL_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


def secs(n):
    return timedelta(seconds=n)


def interp(nodes, t):
    """nodes: [(datetime, value)] ascending; linear interpolation, clamped."""
    if t <= nodes[0][0]:
        return nodes[0][1]
    for (t0, v0), (t1, v1) in zip(nodes, nodes[1:]):
        if t <= t1:
            f = (t - t0).total_seconds() / max(1.0, (t1 - t0).total_seconds())
            return v0 + (v1 - v0) * f
    return nodes[-1][1]


# --------------------------------------------------------------------------
# Generator context
# --------------------------------------------------------------------------

class G:
    def __init__(self, sc):
        self.sc = sc
        self.rng = random.Random(f"{SEED}:{sc['slug']}")
        self.start = T(sc["start"])
        self.end = T(sc["end"])
        self.sonar, self.hipmon, self.splunk = [], [], []
        self.kafka, self.workato, self.apigee, self.mft = [], [], [], []
        self.snow, self.changes, self.late = [], [], []
        self.scope_projects = set(sc["scope"]["projects"])
        self.scope_components = set(sc["scope"]["components"])
        self.incident_codes = set(sc["scope"]["incident_codes"])
        self.last_alert = {}
        self.job_seq = 0
        self.mft_seq = 0
        self.pods = {}

    # ---- ids --------------------------------------------------------------
    def make_id(self, t0, kind):
        if kind == "uuid":
            h = f"{self.rng.getrandbits(128):032x}"
            return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"
        return t0.strftime("%Y%m%d%H%M%S") + f"{self.rng.randrange(10**10):010d}"

    def make_oid(self, tm, t0):
        r = self.rng
        if tm["object_name"] == "FILE":
            return f"{tm['oid_prefix']}{t0:%H%M}.csv"
        if tm["style"] == "idoc":
            return f"{r.randrange(10**15, 10**16):016d}"
        return f"{tm['oid_prefix']}{r.randrange(10**8):08d}"

    def pod(self, cmdb, n=3):
        if cmdb not in self.pods:
            r = random.Random(f"{SEED}:{self.sc['slug']}:pod:{cmdb}")
            self.pods[cmdb] = [
                f"{naming.COMPONENTS[cmdb]['k8s_prefix']}-{r.getrandbits(36):09x}-{''.join(r.choice('bcdfghjklmnpqrstvwxz2456789') for _ in range(5))}"
                for _ in range(n)]
        return self.pods[cmdb]

    # ---- exchanges ----------------------------------------------------------
    def new_x(self, tm, t_end, dur_ms=None, t0=None):
        r = self.rng
        if dur_ms is None:
            dur_ms = max(90, int(r.lognormvariate(math.log(max(tm["mean_ms"], 200)), 0.45)))
        if t0 is None:
            t0 = t_end - timedelta(milliseconds=dur_ms)
        return {"tm": tm, "xid": self.make_id(t0, tm["id_kind"]), "oid": self.make_oid(tm, t0),
                "bval": r.choice(tm["bvals"]), "t0": t0, "dur": dur_ms}

    def sline(self, x, ts, hf, level, status, code, reason, msg, dur, seen=None, missing=None):
        tm = x["tm"]
        nhf = len(tm["halfflows"])
        if seen is None:
            seen, missing = nhf, f"0/{nhf}"
        hfname = tm["halfflows"][hf] if hf is not None else tm["exchange"]
        hfi = 0 if hf is None else hf
        clean = x["xid"].replace("-", "")
        rec = {
            "@timestamp": iso(ts), "exchange.status": status, "event.level": level,
            "project": tm["project"], "exchange": tm["exchange"], "exchange.id": x["xid"],
            "halfflow": hfname, "halfflow.id": f"{clean[-12:]}{hfi + 1:02d}",
            "halfflow.count": seen, "halfflow.missing": missing,
            "application": naming.COMPONENTS[tm["project"]]["k8s_prefix"],
            "event.code": code, "event.reason": reason, "message": msg, "duration": int(dur),
            "source": tm["source"], "destination": tm["destination"],
            "object.id": x["oid"], "object.name": tm["object_name"],
            "business.value": x["bval"], "framework.version": tm["fw"],
            "_index": "sonar-" + naming.elk_index(tm["project"]),
        }
        self.sonar.append(rec)
        return rec

    def complete_line(self, x, ts=None, status="COMPLETE"):
        ts = ts or x["t0"] + timedelta(milliseconds=x["dur"])
        nhf = len(x["tm"]["halfflows"])
        return self.sline(x, ts, nhf - 1, "EXITINFO", status, "IFP_PUB002", "",
                          f"Exchange completed: {x['tm']['object_name']} {x['oid']}", x["dur"])

    def full_trace(self, x, status="COMPLETE"):
        """ENTRYINFO/EXITINFO per half-flow (+ an INFO mapping line)."""
        tm = x["tm"]
        nhf = len(tm["halfflows"])
        step = x["dur"] / nhf
        for i in range(nhf):
            a = x["t0"] + timedelta(milliseconds=step * i)
            b = x["t0"] + timedelta(milliseconds=step * (i + 1))
            last = i == nhf - 1
            self.sline(x, a, i, "ENTRYINFO", "INPROGRESS", "IFP_PUB001", "",
                       f"Half-flow {i + 1}/{nhf} started", int(step * i), i + 1, f"{i + 2}/{nhf}" if i + 1 < nhf else f"{nhf}/{nhf}")
            if i == 1:
                self.sline(x, a + timedelta(milliseconds=step / 3), i, "INFO", "INPROGRESS", "IFP_MAP001", "",
                           f"Mapping applied: {tm['object_name']} {x['oid']}", int(step * i + step / 3), i + 1, f"{i + 2}/{nhf}")
            self.sline(x, b, i, "EXITINFO", status if last else "INPROGRESS", "IFP_PUB002", "",
                       f"Half-flow {i + 1}/{nhf} completed", int(step * (i + 1)),
                       i + 1, "0/%d" % nhf if last else f"{i + 2}/{nhf}")

    def fail_line(self, x, ts, hf, code, reason, msg=None, dur=None, level_code="IFP_RTG001"):
        nhf = len(x["tm"]["halfflows"])
        dur = dur if dur is not None else int((ts - x["t0"]).total_seconds() * 1000)
        return self.sline(x, ts, hf, "ERROR", "FAILED", level_code, reason,
                          msg or reason, dur, hf + 1, f"{hf + 1}/{nhf}")

    # ---- HIPMON ---------------------------------------------------------------
    def hip(self, ts, project, hf, code, err, xid, priority="3 - High"):
        style = "std"
        for tm in EXCHANGES.values():
            if tm["project"] == project and hf in tm["halfflows"]:
                style = tm["style"]
                break
        if style == "idoc":
            subject = f"[AUTO]|{project} | {hf}|DEFAULT"
        else:
            subject = f"[AUTO]|{project}|{hf}|{code}|ETP_{code}"
        self.hipmon.append({
            "timestamp": iso_s(ts), "rule_id": f"HIPMON-{code}", "subject": subject,
            "priority": priority, "project": project, "halfflow": hf,
            "error_text": err, "exchange.id": xid, "zone": naming.ZONE, "environment": naming.ENVIRONMENT,
        })

    def alert_failure(self, x, hf, code, err, t, dedup_min=8, delay=(4, 40), priority="3 - High", min_ts=None):
        hfname = x["tm"]["halfflows"][hf]
        key = hfname
        if min_ts is not None and t < min_ts:
            return
        last = self.last_alert.get(key)
        if last is not None and (t - last) < timedelta(minutes=dedup_min):
            return
        self.last_alert[key] = t
        at = t + secs(self.rng.uniform(*delay))
        if at < self.end:
            code_ = code if x["tm"]["style"] != "idoc" else "DEFAULT"
            self.hip(at, x["tm"]["project"], hfname, code_, err, x["xid"], priority)

    # ---- Splunk ---------------------------------------------------------------
    def splunk_rec(self, ts, host, kind, message, rule_id=None, metric=None, value=None, threshold=None,
                   pod=None, restart_count=None, severity=4, **extra):
        rec = {"@timestamp": iso_s(ts), "host": host, "kind": kind, "severity": severity, "message": message}
        if rule_id:
            rec["rule_id"] = rule_id
        if metric:
            rec["metric"] = metric
            rec["value"] = value
        if threshold is not None:
            rec["threshold"] = threshold
        if pod:
            rec["pod"] = pod
        if restart_count is not None:
            rec["restart_count"] = restart_count
        rec.update(extra)
        self.splunk.append(rec)

    # ---- Workato / Apigee / MFT --------------------------------------------------
    def workato_job(self, ts_end, recipe, status, dur_ms, error=None, xid=None, recipe_id=None):
        self.job_seq += 1
        self.workato.append({
            "job_id": f"WJ{self.job_seq:07d}", "recipe": recipe,
            "recipe_id": recipe_id or (10000 + (abs(hash_str(recipe)) % 89999)),
            "status": status, "started_at": iso_s(ts_end - timedelta(milliseconds=dur_ms)),
            "ended_at": iso_s(ts_end), "duration_ms": int(dur_ms),
            "error": error, "exchange_id": xid,
        })

    def mft_row(self, t0, dur_s, filename, src, tgt, status, nbytes, declared, actual, xid):
        self.mft_seq += 1
        self.mft.append({
            "transfer_id": f"SFG{self.mft_seq:06d}-{xid[:14].replace('-', '')}", "filename": filename,
            "source": src, "target": tgt, "start_time": local_naive(t0),
            "end_time": local_naive(t0 + secs(dur_s)), "status": status, "bytes": nbytes,
            "declared_rows": declared, "actual_rows": actual, "exchange_id": xid,
        })

    # ---- ServiceNow / change ------------------------------------------------------
    def incident(self, number, ts, short, desc, prio, channel, parent=None, notes=None, updates=None,
                 group="TECH FNDN - WW - HIP INCIDENT L2", state="In Progress", rule=None):
        self.snow.append({
            "number": number, "opened_at": iso_s(ts), "short_description": short, "description": desc,
            "priority": prio, "assignment_group": group, "state": state, "parent": parent,
            "opened_by": "HIPMON" if channel == "auto" else "Service Desk (user-raised)",
            "channel": channel, "rule": rule,
            "work_notes": [{"ts": iso_s(a), "note": b} for a, b in (notes or [])],
            "updates": [{"ts": iso_s(a), "field": b, "value": c} for a, b, c in (updates or [])],
        })

    def change(self, number, ts, ctype, component, desc, implementer, approval, rollback, extra=None):
        rec = {"change_number": number, "type": ctype, "implemented_at": iso_s(ts), "component": component,
               "description": desc, "implementer": implementer, "approval_state": approval,
               "rollback_plan": rollback}
        if extra:
            rec.update(extra)
        self.changes.append(rec)


def hash_str(s):
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) % 1000003
    return h


# --------------------------------------------------------------------------
# Shared baseline builders
# --------------------------------------------------------------------------

def default_weights():
    w = {}
    for k in EXCHANGES:
        if k in SPECIAL:
            continue
        if k.startswith("idoc_"):
            w[k] = 0.15
        elif k.startswith("pi7_"):
            w[k] = 0.4
        else:
            w[k] = 1.0
    return w


def gen_bg(g, weights, hook=None, period=None, skip_keys=()):
    """Background exchanges as a sampled Sonar log. `hook(x, t)` may turn one
    into a scenario fault: returns None or a dict {kind: FAILED|STUCK|...}."""
    r = g.rng
    period = period or g.sc["bg_period_sec"]
    keys = [k for k in weights if k not in skip_keys and weights[k] > 0]
    wts = [weights[k] for k in keys]
    t = g.start
    while True:
        t += secs(r.expovariate(1.0 / period))
        if t >= g.end:
            break
        key = r.choices(keys, wts)[0]
        tm = EXCHANGES[key]
        res = hook(tm, t) if hook else None
        if res and res.get("skip"):
            continue
        kind = res["kind"] if res else None
        dur = res.get("dur") if res else None
        x = g.new_x(tm, t, dur_ms=dur)
        if kind == "FAILED":
            hf = res["hf"]
            g.fail_line(x, t, hf, res["code"], res["reason"], res.get("msg"))
            if res.get("alert", True):
                g.alert_failure(x, hf, res["code"], res["reason"], t, res.get("dedup", 8),
                                min_ts=res.get("alert_min_ts"))
            g.on_failed = getattr(g, "on_failed", [])
            g.on_failed.append((t, x, hf, res))
            continue
        if kind == "STUCK":
            stuck_lines(g, x, t, res)
            continue
        # normal completion; occasional in-flight pair, warnings, F-completions
        roll = r.random()
        if roll < 0.035 and x["dur"] > 800:
            g.sline(x, x["t0"] + secs(0.4), 1, "ENTRYINFO", "INPROGRESS", "IFP_PUB001", "",
                    "Half-flow 2/4 started", 400, 2, "2/4")
            g.complete_line(x)
        elif roll < 0.045:
            g.complete_line(x, status="COMPLETE (F)")
        elif roll < 0.055:
            g.sline(x, t, 3, "INFO", "WARNING", "IFP_MAP001", "Optional field missing, default applied",
                    "Optional field missing in payload; default applied", x["dur"], 4, "0/4")
        else:
            g.complete_line(x)
        # background failures on non-critical, out-of-scope flows only
        if (key not in CRITICAL and tm["project"] not in g.scope_projects and r.random() < 0.05):
            pool = [f for f in BG_FAILS if f[0] not in g.incident_codes]
            code, reason, hf = r.choice(pool)
            hf = min(hf, len(tm["halfflows"]) - 1)
            x2 = g.new_x(tm, t + secs(r.uniform(1, 30)))
            g.fail_line(x2, x2["t0"] + timedelta(milliseconds=x2["dur"]), hf, code, reason)
            g.alert_failure(x2, hf, code, reason, x2["t0"] + timedelta(milliseconds=x2["dur"]), dedup_min=25)


def stuck_lines(g, x, t, res):
    """Exchange stuck INPROGRESS at half-flow 2/4 (hf1 exited, hf2 entered, no exit)."""
    g.sline(x, t, 0, "EXITINFO", "INPROGRESS", "IFP_PUB002", "", "Half-flow 1/4 completed", 1200, 1, "2/4")
    g.sline(x, t + secs(0.3), 1, "ENTRYINFO", "INPROGRESS", "IFP_PUB001", "", "Half-flow 2/4 started (mapping)",
            1500, 2, "2/4")
    age = g.rng.uniform(60, 540)
    if t + secs(age) < g.end:
        g.sline(x, t + secs(age), 1, "INFO", "INPROGRESS", "IFP_MON001", "",
                f"Exchange in progress for {age / 60:.1f} min; half-flow 2/4 has not exited",
                int(age * 1000), 2, "2/4")
    g.stuck = getattr(g, "stuck", [])
    g.stuck.append((t, x))


def gen_special_flows(g, with_bpm=True, bpm_hours=(0, 2, 4, 6, 8), bad_bpm=None):
    """wait-for-file / slow batches (normal long-running INPROGRESS) + scheduled MFT feeds."""
    r = g.rng
    # wait-for-file exchanges that stay INPROGRESS at 1/2 (normal on the real dashboard)
    tm = EXCHANGES["waitfile"]
    for i in range(8):
        t0 = g.start - secs(r.uniform(600, 40000))
        x = g.new_x(tm, t0, dur_ms=1, t0=t0)
        x["oid"] = f"WATCH_{r.choice(['ONEREAD', 'FCST', 'BPM', 'TITAN', 'WISE'])}_{r.randrange(100, 999)}"
        ts = g.start + secs(r.uniform(0, 90))
        g.sline(x, ts, 0, "ENTRYINFO", "INPROGRESS", "IFP_PUB001", "", "Waiting for file", 0, 1, "1/2")
        x["t0"] = t0
        g.sonar[-1]["duration"] = int((ts - t0).total_seconds() * 1000)
    # slow batches: INPROGRESS then COMPLETE 10-90 min later
    tm = EXCHANGES["slowbatch"]
    t = g.start + secs(r.uniform(60, 900))
    while t < g.end:
        d = int(r.uniform(600, 5400) * 1000)
        x = g.new_x(tm, t + timedelta(milliseconds=d), dur_ms=d, t0=t)
        g.sline(x, t, 1, "ENTRYINFO", "INPROGRESS", "IFP_PUB001", "", "Half-flow 2/4 started (batch)", 900, 2, "2/4")
        if t + timedelta(milliseconds=d) < g.end:
            g.complete_line(x)
        t += secs(r.uniform(1800, 3600))
    # onereadsoft hourly (:05) and futurmaster hourly (:35) single-line + MFT rows
    h = g.start.replace(minute=0, second=0)
    while h < g.end:
        for mm, key, fname, size in ((5, "onereadsoft", "OR_EXPORT_%H%M.csv", 3_400_000),
                                     (35, "futurmaster", "FCST_%H%M.csv", 4_050_000)):
            t0 = h + timedelta(minutes=mm, seconds=r.uniform(0, 20))
            if g.start <= t0 < g.end - secs(60):
                tm = EXCHANGES[key]
                x = g.new_x(tm, t0 + secs(30), dur_ms=30000, t0=t0)
                x["oid"] = t0.strftime(fname)
                rows = 40000 + r.randrange(2000)
                g.mft_row(t0, 3 + r.randrange(4), x["oid"], "SGLORHIPPMFTSI1" if key == "onereadsoft" else "FRHIPGPPMFTSI01",
                          "AZURE_BLOB" if key == "onereadsoft" else "ANAPLAN", "SUCCESS",
                          size + r.randrange(60000), rows, rows, x["xid"])
                g.complete_line(x)
        h += timedelta(hours=1)
    # BPM_to_FM: normal runs at even hours; the bad one is supplied by S4 code
    if with_bpm:
        for hh in bpm_hours:
            t0 = T(f"{hh:02d}:00:0{r.randrange(3, 8)}")
            if not (g.start <= t0 < g.end - secs(120)):
                continue
            if bad_bpm and hh == bad_bpm:
                continue
            tm = EXCHANGES["bpm_fm"]
            x = g.new_x(tm, t0 + secs(46), dur_ms=46000, t0=t0)
            x["oid"] = f"BPM_to_FM_{hh:02d}00.csv"
            g.mft_row(t0 - secs(4), 5, x["oid"], "FRHIPGPRMFTSI02", "FM_FRCPD", "SUCCESS", 6_800_000 + r.randrange(40000),
                      128400, 128400, x["xid"])
            g.full_trace(x)


def flines(g, x, base, rows):
    """rows: (offset_s, hf, level, status, code, reason, msg, seen, missing)."""
    for off, hf, level, status, code, reason, msg, seen, missing in rows:
        ts = base + timedelta(seconds=off)
        g.sline(x, ts, hf, level, status, code, reason, msg, int((ts - x["t0"]).total_seconds() * 1000), seen, missing)


def gen_hourly_reports(g, inprog_fn, extra_fn=None, critical_failed_fn=None):
    """SONAR-OPS hourly critical-exchange report. WARNING (= rule SNR-HRLY-CRIT
    fired) only when InProgress >= 1000 or Failed >= 25."""
    r = g.rng
    minute = g.sc["hourly_report_minute"]
    h = g.start.replace(minute=minute, second=0)
    if h < g.start:
        h += timedelta(hours=1)
    tm = {"exchange": "GLBL_MSTR_HLTH_CHK", "project": "SONAR-OPS", "halfflows": ["GLBL_MSTR_HLTH_CHK"],
          "source": "SONAR", "destination": "OPS", "object_name": "HOURLY_REPORT", "fw": "5.0.2"}
    while h <= g.end:
        base_inprog = r.randint(310, 520)
        inprog, listing_in = inprog_fn(h, base_inprog)
        failed_lines = [s for s in g.sonar if s["exchange.status"] == "FAILED"
                        and h - timedelta(hours=1) <= dt_of(s) <= h
                        and EXCHANGES_BY_NAME.get(s["exchange"], {}).get("key") in CRITICAL]
        failed = len(failed_lines)
        if critical_failed_fn:
            failed = critical_failed_fn(h, failed)
        top_failed = ""
        if failed:
            cnt = {}
            for s in failed_lines:
                cnt[s["project"]] = cnt.get(s["project"], 0) + 1
            top = sorted(cnt.items(), key=lambda kv: -kv[1])[:3]
            top_failed = "; top Failed: " + ", ".join(f"{k} ({v})" for k, v in top) if top else ""
        hit = inprog >= 1000 or failed >= 25
        msg = (f"[SONAR-OPS][PRD] HLTH_CHK {h:%H:%M}Z critical exchanges: InProgress={inprog:,} Failed={failed:,} "
               f"Warning={r.randint(3, 19)}; InProgress: {listing_in}{top_failed}")
        x = {"tm": tm, "xid": f"hlth-{h:%H%M}", "oid": f"HLTH_{h:%H%M}", "bval": "EMEA", "t0": h, "dur": 900}
        g.sline(x, h, 0, "INFO", "WARNING" if hit else "COMPLETE", "SNR_HRLY001", "", msg, 900, 1, "0/1")
        h += timedelta(hours=1)


EXCHANGES_BY_NAME = {v["exchange"]: v for v in EXCHANGES.values()}


def dt_of(rec):
    return datetime.fromisoformat(rec["@timestamp"])


def gen_volume_records(g, series):
    """series: list of (label, fn(bucket_end) -> (count, baseline, extra_text))."""
    tm = {"exchange": "GLBL_MSTR_VOLUME_CHK", "project": "SONAR-OPS", "halfflows": ["GLBL_MSTR_VOLUME_CHK"],
          "source": "SONAR", "destination": "OPS", "object_name": "VOLUME_CHECK", "fw": "5.0.2"}
    t = g.start.replace(minute=(g.start.minute // 5) * 5, second=0) + timedelta(minutes=5)
    while t <= g.end:
        for label, fn in series:
            count, baseline, extra = fn(t)
            x = {"tm": tm, "xid": f"vol-{label}-{t:%H%M}", "oid": label, "bval": "EMEA", "t0": t, "dur": 300}
            g.sline(x, t + secs(1), 0, "INFO", "COMPLETE", "SNR_CNT001", "",
                    f"{label} in last 5 min: {count:,} (baseline {baseline:,}){extra}", 300, 1, "0/1")
        t += timedelta(minutes=5)


def gen_kafka(g, lag_fn):
    """lag_fn(group, t) -> lag (int). One row per group per 15 s."""
    r = random.Random(f"{SEED}:{g.sc['slug']}:kafka")
    groups = naming.PROCESSING_GROUPS
    base = {gr: 4_000_000 + i * 1_137_000 for i, gr in enumerate(groups)}
    rate = {gr: 320 + 40 * i for i, gr in enumerate(groups)}
    prev_cur = {}
    t = g.start
    n = 0
    while t <= g.end:
        for gr in groups:
            end_off = base[gr] + rate[gr] * n
            lag = int(max(0, lag_fn(gr, t)))
            cur = end_off - lag
            if gr in prev_cur and cur < prev_cur[gr]:
                cur = prev_cur[gr]
            prev_cur[gr] = cur
            g.kafka.append([iso_s(t), naming.consumer_group_for(gr), naming.topic_for(gr), 0, cur, end_off, end_off - cur])
        t += secs(15)
        n += 1


def gen_apigee_baseline(g, hook=None):
    r = random.Random(f"{SEED}:{g.sc['slug']}:apigee")
    t = g.start.replace(second=0)
    while t < g.end:
        for _ in range(r.randint(1, 3)):
            ep = r.choice(APIGEE_ENDPOINTS)
            st = r.choice([401, 404, 404, 429, 500, 502])
            cnt = r.randint(1, 4)
            g.apigee.append({"minute": iso_s(t), "endpoint": ep, "status": st, "count": cnt,
                             "p99_latency_ms": r.randint(180, 900), "sample_exchange_ids": []})
        if hook:
            hook(t)
        t += timedelta(minutes=1)


def gen_workato_baseline(g):
    r = random.Random(f"{SEED}:{g.sc['slug']}:workato")
    recipes = ["Salesforce Case Sync", "Anaplan Forecast Publish", "3PL Shipment Status Poll", "Customer Master Enrich",
               "Warehouse Capacity Notify", "Returns Label Generator"]
    t = g.start
    while t < g.end:
        t += secs(r.expovariate(1 / 40))
        if t < g.end:
            g.workato_job(t, r.choice(recipes), "succeeded", r.randint(400, 6000))


def gen_noise_hosts(g):
    """Standing noise (both non-prod, unrelated) + routine host metrics."""
    r = random.Random(f"{SEED}:{g.sc['slug']}:hosts")
    for n_i, nz in enumerate(naming.STANDING_NOISE):
        period = 47 if n_i == 0 else 61
        t = g.start + timedelta(minutes=9 + n_i * 13)
        while t < g.end:
            val = r.randint(nz["threshold"] + 1, 99) if nz["metric"] == "cpu_pct" else r.randint(91, 97)
            g.splunk_rec(t, nz["host"], "alert", nz["text"], rule_id=nz["rule_id"], metric=nz["metric"],
                         value=val, threshold=nz["threshold"], severity=4)
            t += timedelta(minutes=period + r.randint(-4, 4))
    for host in ("SGLORHIPQETLPC1", "FRHIPGQAMFTSI01", "FRHIPGPPMFTSI01", "SGLORHIPPMFTSI1", "SGLORHIPPETLPC1"):
        t = g.start
        while t < g.end:
            g.splunk_rec(t, host, "metric", f"{host} host metrics", metric="cpu_pct", value=r.randint(8, 46),
                         swap_pct=r.randint(60, 88) if host == "SGLORHIPQETLPC1" else r.randint(4, 22),
                         fs_pct=r.randint(41, 58))
            t += timedelta(minutes=1)


def gen_chaff_changes(g, sid, k=6):
    r = random.Random(f"{SEED}:{g.sc['slug']}:chaff")
    pool = [c for c in CHAFF if c[0] not in CHAFF_AVOID.get(sid, set())]
    picks = r.sample(pool, k)
    for i, (comp, desc, ctype, rb) in enumerate(picks):
        ts = g.start + secs(r.randint(0, int((g.end - g.start).total_seconds())))
        g.change(f"CHG{4400100 + int(sid[1]) * 100 + i:07d}", ts, ctype, comp, desc, f"{naming.team_of(comp)} team",
                 "Approved", rb)


def finish_snow_noise(g):
    pass


# --------------------------------------------------------------------------
# Scenario 1 -- large-mapping heap exhaustion
# --------------------------------------------------------------------------

def build_s1(g):
    r = g.rng
    sc = g.sc
    lag_nodes = [(T("05:55:00"), 0), (T("06:20:00"), 3100), (T("06:35:00"), 9400), (T("06:52:00"), 15800),
                 (T("07:05:00"), 22600), (T("07:30:00"), 44700), (T("08:10:00"), 71300), (T("08:30:00"), 82900)]
    target = "opsfin-01-neo-odes-large"

    def lag_fn(gr, t):
        if gr != target:
            return 0
        v = interp(lag_nodes, t)
        if v <= 0:
            return 0
        return v + (int(t.timestamp()) % 7) * 11

    gen_kafka(g, lag_fn)

    def hook(tm, t):
        if tm["key"] != "asn":
            return None
        if t >= T("06:14:00"):
            return {"kind": "STUCK"}
        if t >= T("05:00:00"):
            f = 1 + (t - T("05:00:00")).total_seconds() / 60 * 0.12
            return {"kind": None, "dur": int(tm["mean_ms"] * f * r.uniform(0.8, 1.3))}
        return None

    w = default_weights()
    w["asn"] = 6
    gen_bg(g, w, hook)
    gen_special_flows(g)

    # focal trace: one ASN exchange stuck INPROGRESS at half-flow 2/4 (14 trace rows)
    fx = g.new_x(EXCHANGES["asn"], T("06:41:11"), dur_ms=1, t0=T("06:41:10"))
    P, I, E, X = "INPROGRESS", "INFO", "ENTRYINFO", "EXITINFO"
    flines(g, fx, T("06:41:10"), [
        (0.0, 0, E, P, "IFP_PUB001", "", "Half-flow 1/4 started: STO ASN message received from SAPS4HANA_NEO", 1, "1/4"),
        (0.35, 0, I, P, "IFP_MAP001", "", "Payload received: 3.24 MB, 41,872 line items (24 h average 1.05 MB)", 1, "1/4"),
        (1.2, 0, X, P, "IFP_PUB002", "", "Half-flow 1/4 completed", 1, "2/4"),
        (1.3, 1, E, P, "IFP_PUB001", "", "Half-flow 2/4 started (mapping ASN_TO_S4 v2.14)", 2, "2/4"),
        (1.5, 1, I, P, "IFP_MAP001", "", "Mapping: loading source tree, 41,872 line items", 2, "2/4"),
        (9.0, 1, I, P, "IFP_MON002", "", "GC: full GC pause 812 ms, heap 92% of container limit", 2, "2/4"),
        (21.0, 1, I, P, "IFP_MON002", "", "GC: full GC pause 1,140 ms, heap 95% of container limit", 2, "2/4"),
        (38.0, 1, I, P, "IFP_MAP001", "", "Mapping segment 6/40 processed", 2, "2/4"),
        (61.0, 1, I, P, "IFP_MON002", "", "GC overhead: 41% of the last 60 s spent in GC", 2, "2/4"),
        (150.0, 1, I, P, "IFP_MAP001", "", "Mapping segment 7/40 processed", 2, "2/4"),
        (180.0, 1, I, P, "IFP_MON001", "", "Exchange in progress for 3.0 min; half-flow 2/4 has not exited", 2, "2/4"),
        (300.0, 1, I, P, "IFP_MON001", "", "Exchange in progress for 5.0 min; half-flow 2/4 has not exited", 2, "2/4"),
        (420.0, 1, I, P, "IFP_MON001", "", "Exchange in progress for 7.0 min; half-flow 2/4 has not exited", 2, "2/4"),
        (540.0, 1, I, P, "IFP_MON001", "", "Exchange in progress for 9.0 min; half-flow 2/4 has not exited", 2, "2/4"),
    ])
    g.stuck = getattr(g, "stuck", [])
    g.stuck.append((T("06:41:10"), fx))

    # STO batch INFO line (the trigger)
    tm = EXCHANGES["saptr_inv"]
    sto = {"tm": {"exchange": "GLBL_SAPS4HANA_STO_BATCH_IN", "project": "SAPS4HANA_ASN",
                  "halfflows": ["GLBL_SAPS4HANA_STO_BATCH_IN_01_ESB"], "source": "SAPS4HANA_S4",
                  "destination": "SAPS4HANA_NEO", "object_name": "STO_BATCH", "fw": "5.0.2"},
           "xid": "20260918045211" + f"{r.randrange(10**10):010d}", "oid": "STO_BATCH_3850", "bval": "CZ01",
           "t0": T("04:52:11"), "dur": 38000}
    g.sline(sto, T("04:52:49"), 0, "INFO", "COMPLETE", "IFP_PUB002", "",
            "STO batch released from S4: 3,850 stock transport orders, ASN generation requested", 38000, 1, "0/1")

    # volume: ASN inflow lower than last Thursday; avg payload grows
    def vol_asn(t):
        thu = int(171 + 9 * math.sin(t.minute / 9.0))
        today = int(thu * (0.68 + 0.04 * math.sin(t.minute / 5.0)))
        return today, thu, f" [same 5-min window last Thursday: {thu}]"

    def vol_kb(t):
        base = 38 + (t.minute % 4)
        if t >= T("05:00:00"):
            base = 38 + (t - T("05:00:00")).total_seconds() / 60 * 0.9
            base = min(base, 121)
        return int(base), 40, " KB"

    gen_volume_records(g, [("ASN_INT inflow", vol_asn), ("ASN_INT avg payload", vol_kb)])

    def inprog(h, base):
        lag = interp(lag_nodes, h)
        n = int(lag) + (512 if h == T("07:30:00") else base)
        if lag > 0:
            return n, f"GLBL_SAPS4HANA_SAPS4HANA_ASN_INT ({int(lag):,}) at half-flow 2/4, GLBL_SCHEDULER_WAITFORFILE ({base - 60})"
        return n, f"GLBL_SCHEDULER_WAITFORFILE ({n - 60}), GLBL_CTRLM_MASTERDATA_BATCH (3)"

    gen_hourly_reports(g, inprog)

    # ---- Splunk: heap on hip-esb-odes-large pods -------------------------------
    pods = g.pod(target, 3)
    restarts = {p: 0 for p in pods}
    heap0 = T("04:25:00")
    t = g.start
    while t <= g.end:
        for i, p in enumerate(pods):
            if t < T("06:35:00"):
                v = 55 + max(0, (t - heap0).total_seconds() / 60) * (0.333 if t >= heap0 else 0) + i * 0.7
                rc = 0
            elif t < T("06:52:00"):
                v = 30 + (t - T("06:35:00")).total_seconds() / 60 * 3.6 + i
                rc = 1 if i == 0 else 0
            else:
                v = min(99, 58 + (t - T("06:52:00")).total_seconds() / 60 * 2.5 + i)
                rc = 2 if i == 0 else 0
            v = min(99.0, v + r.uniform(-0.6, 0.6))
            gc = 40 if v < 70 else int(40 + (v - 70) * 30)
            if t >= T("06:52:00"):
                gc = int(900 + r.uniform(0, 400))
            g.splunk_rec(t, pods[i], "metric", f"heap {v:.1f}% gc_pause_p99 {gc}ms", metric="heap_pct", value=round(v, 1),
                         pod=p, restart_count=rc, deployment="hip-esb-odes-large", gc_pause_p99_ms=gc,
                         cpu_pct=int(30 + v / 3))
        t += timedelta(minutes=1)
    g.splunk_rec(T("05:10:08"), pods[0], "alert", "heap > 70% on hip-esb-odes-large pods (71.2%)",
                 rule_id="SPL-HEAP001", metric="heap_pct", value=71.2, threshold=70, pod=pods[0],
                 deployment="hip-esb-odes-large", severity=4)
    g.splunk_rec(T("06:35:12"), pods[0], "alert", f"OOMKilled: container exceeded memory limit, pod {pods[0]} restart 1",
                 rule_id="SPL-OOM001", pod=pods[0], restart_count=1, deployment="hip-esb-odes-large", severity=3)
    g.splunk_rec(T("06:52:30"), pods[0], "alert", f"OOMKilled: pod {pods[0]} restart 2 (crash loop)",
                 rule_id="SPL-OOM001", pod=pods[0], restart_count=2, deployment="hip-esb-odes-large", severity=3)

    # ---- HIPMON: lag + PRC003 on stuck ASN exchanges --------------------------
    for at in ("07:05:00", "07:35:00", "08:05:00"):
        g.hip(T(at) + secs(r.randint(3, 30)), naming.HIPMON_KAFKA_PROJECT,
                 naming.topic_for(target), "LAG01",
                 f"Consumer lag on {naming.topic_for(target)} above 20,000 and rising", "")
    stuck = getattr(g, "stuck", [])
    for i, (t, x) in enumerate(sorted(stuck, key=lambda s: s[0])):
        at = t + timedelta(minutes=30)
        if at >= T("07:05:00") and at < g.end:
            g.hip(at + secs(r.randint(0, 20)), x["tm"]["project"], x["tm"]["halfflows"][1], "PRC003",
                     "Exchange in progress > 30 min at half-flow 2/4 (processing timeout)", x["xid"])

    # ---- ServiceNow -------------------------------------------------------------
    first_stuck = sorted(stuck, key=lambda s: s[0])[-1][1]["xid"]
    hm = [a for a in g.hipmon if a["rule_id"] == "HIPMON-PRC003"]
    ex_ids = [a["exchange.id"] for a in hm[:3]]
    g.incident(sc["incident_number"], T("08:10:14"), "No ASN integrated in S4 - trucks waiting",
               f"Warehouse reports no ASN integrated in S4 since this morning; trucks waiting at the gate. "
               f"Example exchange {ex_ids[0]} (GLBL_SAPS4HANA_SAPS4HANA_ASN_INT) shows INPROGRESS. Replay attempted by L1.",
               1, "user", notes=[(T("08:24:00"), "L1: replay of 5 ASN exchanges attempted, exchanges remain INPROGRESS at 2/4."),
                                 (T("08:31:00"), "Escalated to L2; bridge opened.")])
    dup = sc["duplicate_incidents"]
    g.incident(dup[0], T("08:10:41"), "[AUTO]|KAFKA_LAG|" + naming.topic_for(target) + "|LAG01|ETP_LAG01",
               "Consumer lag above threshold on " + naming.topic_for(target), 3, "auto", parent=sc["incident_number"], rule="HIPMON-LAG01")
    g.incident(dup[1], T("08:11:02"), f"[AUTO]|SAPS4HANA_ASN|GLBL_SAPS4HANA_SAPS4HANA_ASN_INT_02_ESB|PRC003|ETP_PRC003",
               f"Exchange {ex_ids[1]} in progress > 30 min at half-flow 2/4", 3, "auto", parent=sc["incident_number"], rule="HIPMON-PRC003")
    g.incident(dup[2], T("08:11:30"), "[SONAR-OPS][PRD] HLTH_CHK critical exchanges: InProgress above threshold",
               "Hourly critical exchange report 07:30Z: InProgress=45,212", 3, "auto", parent=sc["incident_number"], rule="SNR-HRLY-CRIT")

    # ---- Apigee: mild extra 5xx on /hip/v1/asn after 07:30 ---------------------
    for m in range(0, 60):
        t = T("07:30:00") + timedelta(minutes=m)
        if t < g.end:
            g.apigee.append({"minute": iso_s(t), "endpoint": "/hip/v1/asn", "status": 504, "count": r.randint(2, 9),
                             "p99_latency_ms": r.randint(9000, 15000), "sample_exchange_ids": [first_stuck]})

    gen_workato_baseline(g)
    gen_noise_hosts(g)
    gen_chaff_changes(g, "s1")
    gen_late(g)


# --------------------------------------------------------------------------
# Scenario 2 -- PI7 listener hang
# --------------------------------------------------------------------------

def build_s2(g):
    r = g.rng
    sc = g.sc
    gen_kafka(g, lambda gr, t: 0)
    w = default_weights()
    for k in ("pi7_ce",):
        w.pop(k, None)
    w["pi7_uk"] = w["pi7_it"] = w["pi7_ne"] = 1.2
    gen_bg(g, w, None)
    gen_special_flows(g)

    # PI7 hub CE inbound: sampled exchanges every ~20 s until 13:29:48.3, heartbeats at :12 every 60 s
    tm = EXCHANGES["pi7_ce"]
    last = T("13:29:48") + timedelta(milliseconds=310)
    t = g.start
    ce_ids = []
    while t < last:
        t += secs(r.expovariate(1 / 20.0))
        if t >= last:
            break
        x = g.new_x(tm, t)
        g.complete_line(x)
        ce_ids.append(x)
    x = g.new_x(tm, last, dur_ms=2300)
    g.full_trace(x)
    flines(g, x, x["t0"], [
        (0.05, 0, "INFO", "INPROGRESS", "IFP_MAP001", "", "IDoc DELVRY07 received from SAP PI7 hub CE via AN_COMMON_PI7IDOCListner", 1, "1/4"),
        (0.9, 1, "INFO", "INPROGRESS", "IFP_MAP001", "", "Enrichment: plant CZ01 resolved to Manhattan site", 2, "2/4"),
        (1.6, 2, "INFO", "INPROGRESS", "IFP_MAP001", "", "Message published to Manhattan inbound queue", 3, "3/4"),
        (2.2, 3, "INFO", "INPROGRESS", "IFP_MAP001", "", "Acknowledged by Manhattan (ACK 200)", 4, "4/4"),
    ])
    last_ce = x
    # full trace of a few CE exchanges for the trace panel
    for ts in ("13:12:31", "13:22:05"):
        xx = g.new_x(tm, T(ts), dur_ms=2300)
        g.full_trace(xx)
    hb = T("12:30:12")
    listener_tm = {"exchange": "AN_COMMON_PI7IDOCListner", "project": "SAPCE_PI7_INBOUND",
                   "halfflows": ["AN_COMMON_PI7IDOCListner"], "source": "SAPCE_PI7", "destination": "HIP",
                   "object_name": "LISTENER_HEARTBEAT", "fw": "4.12.3", "bvals": ["CE"]}
    n_cons = 0
    while hb <= T("13:30:12"):
        n_cons += r.randint(9, 15)
        hx = {"tm": listener_tm, "xid": f"hb-{hb:%H%M%S}", "oid": "HB", "bval": "CE", "t0": hb, "dur": 5}
        g.sline(hx, hb, 0, "INFO", "COMPLETE", "IFP_HBT001", "",
                f"AN_COMMON_PI7IDOCListner heartbeat: connected to PI7 hub CE, consumed={n_cons} since start, queue=0",
                5, 1, "0/1")
        hb += secs(60)

    def vol(hub, base):
        def f(t):
            if hub == "CE":
                if t <= T("13:30:00"):
                    return base + r.randint(-6, 6), base, ""
                return 0, base, ""
            return base + r.randint(-5, 5), base, ""
        return f

    series = []
    for hub, base in (("CE", 180), ("UK", 120), ("IT", 96), ("NE", 64)):
        series.append((f"inbound exchanges from PI7 hub {hub}", vol(hub, base)))
    gen_volume_records(g, series)

    gen_hourly_reports(g, lambda h, base: (base, f"GLBL_SCHEDULER_WAITFORFILE ({base - 60}), GLBL_CTRLM_MASTERDATA_BATCH (3)"))

    # L1 replay attempt: nothing to replay
    rp = {"tm": {"exchange": "GLBL_MSTR_REPLAY", "project": "SONAR-OPS", "halfflows": ["GLBL_MSTR_REPLAY"],
                 "source": "SONAR", "destination": "OPS", "object_name": "REPLAY_REQUEST", "fw": "5.0.2"},
          "xid": "replay-yodi-1", "oid": "YODI", "bval": "CZ01", "t0": T("14:35:00"), "dur": 800}
    g.sline(rp, T("14:35:04"), 0, "INFO", "COMPLETE", "IFP_RPL001", "",
            "Replay (YODI reprocess) requested by L1 for object.name=DELVRY07 status in (FAILED,INPROGRESS) since 13:30: 0 exchanges matched, nothing to replay",
            800, 1, "0/1")

    # ---- Splunk: listener JVM flat, health green ---------------------------------
    lp = g.pod("AN_COMMON_PI7IDOCListner", 2)
    t = g.start
    while t <= g.end:
        for p in lp:
            g.splunk_rec(t, p, "metric", "listener JVM metrics", metric="heap_pct", value=round(41 + r.uniform(-1.2, 1.4), 1),
                         pod=p, restart_count=0, deployment="hip-pi7-idoc-listener", cpu_pct=int(9 + r.uniform(0, 5)),
                         threads=88 + r.randint(-2, 3))
        t += timedelta(minutes=1)
    t = g.start + secs(150)
    while t <= g.end:
        g.splunk_rec(t, lp[0], "health", "GET /actuator/health -> 200 UP (jms, disk, ping); listener JVM heap 42%, CPU 11%",
                     pod=lp[0], deployment="hip-pi7-idoc-listener", health="UP")
        t += timedelta(minutes=5)

    # ---- HIPMON: NO DATA (+ hourly repeats) --------------------------------------
    for at in [f"{h:02d}:{m:02d}:00" for h in range(14, 18) for m in range(10 if h == 14 else 0, 60, 10)]:
        if T(at) < g.end:
            g.hip(T(at) + secs(r.randint(2, 30)), "SAPCE_PI7_INBOUND", "EMEA_SAPCE_PI7_IDOC_DELVRY07_TO_MANH_01_ESB",
                     "NODATA01", "NO DATA FROM SAPCE/Pi7 IN LAST 60 minutes", "")

    for at in [f"{h:02d}:{m:02d}:00" for h in range(14, 18) for m in range(15 if h == 14 else 0, 60, 30)]:
        if T(at) < g.end:
            g.hip(T(at) + secs(r.randint(2, 30)), "MANHATTAN_WMS", "EMEA_MANH_DELIVERY_RECEIPT_MONITOR_01_ESB", "SLA01",
                  "No delivery IDoc received from SAP hub CE for warehouse CZ01 within 45 min SLA", "")

    # ---- ServiceNow --------------------------------------------------------------
    lx = last_ce["xid"]
    g.incident(sc["incident_number"], T("14:20:31"), "CZ warehouse - no deliveries from SAP",
               "CZ warehouse (Manhattan) reports no deliveries received from SAP since about 13:30. Warehouse is blocked. "
               f"Last delivery visible: exchange {lx} (EMEA_SAPCE_PI7_IDOC_DELVRY07_TO_MANH). Reprocess (YODI) attempted, no effect.",
               2, "user", notes=[(T("14:35:00"), "L1: YODI reprocess attempted; Sonar shows 0 exchanges to replay."),
                                 (T("14:50:00"), "Escalated to L2.")],
               updates=[(T("15:49:00"), "priority", "1 - Critical"), (T("17:17:00"), "priority", "Major incident declared")])
    dup = sc["duplicate_incidents"]
    g.incident(dup[0], T("14:12:20"), "[AUTO]|SAPCE_PI7_INBOUND|EMEA_SAPCE_PI7_IDOC_DELVRY07_TO_MANH_01_ESB|NODATA01|ETP_NODATA01",
               "NO DATA FROM SAPCE/Pi7 IN LAST 60 minutes", 3, "auto", parent=sc["incident_number"], rule="HIPMON-NODATA01")
    g.incident(dup[1], T("14:41:10"), "PL warehouse - deliveries from SAP not arriving",
               "Second warehouse reporting the same symptom: no deliveries from SAP hub CE.", 3, "user", parent=sc["incident_number"])
    g.incident(dup[2], T("15:05:44"), "SK warehouse - no delivery notifications", "No delivery notifications from SAP CE hub since early afternoon.",
               3, "user", parent=sc["incident_number"])

    gen_apigee_baseline(g)
    gen_workato_baseline(g)
    gen_noise_hosts(g)
    gen_chaff_changes(g, "s2")
    gen_late(g)


# --------------------------------------------------------------------------
# Scenario 3 -- vendor release
# --------------------------------------------------------------------------

def build_s3(g):
    r = g.rng
    sc = g.sc
    gen_kafka(g, lambda gr, t: 0)
    FAIL0 = T("09:52:00")
    hub_alert_start = {"CE": T("09:55:10"), "UK": T("09:57:20"), "IT": T("09:59:05"), "NE": T("10:01:30")}
    ERR_A = "Recipe function execution error: Recipe function call failed"
    ERR_B = "SAP RFC Error: Failed to fetch ConfigForDocSending"

    def hook(tm, t):
        if not tm["key"].startswith("idoc_") or t < FAIL0:
            return None
        hub = tm["key"].split("_")[1].upper()
        p_fail = 0.62 if tm["key"] == "idoc_ne_yhipdelvry07" else 0.97
        if r.random() >= p_fail:
            return None
        return {"kind": "FAILED", "hf": 2, "code": "DEFAULT", "reason": ERR_B,
                "msg": f"{ERR_B} (Workato recipe {tm['exchange']})", "alert_min_ts": hub_alert_start[hub], "dedup": 8}

    w = default_weights()
    for k in naming.IDOC_KEYS:
        w[k] = 2.5
    w["idoc_ne_yhipdelvry07"] = 5.0
    gen_bg(g, w, hook)
    gen_special_flows(g)

    # explicit first alerts per hub (YLCD01) so the 09:55 CE, then UK, IT, NE sequence is exact
    for hub, ts in hub_alert_start.items():
        tm = EXCHANGES[f"idoc_{hub.lower()}_ylcd01"]
        x = g.new_x(tm, ts - secs(6))
        g.fail_line(x, ts - secs(6), 2, "DEFAULT", ERR_B, f"{ERR_B} (Workato recipe {tm['exchange']})")
        g.last_alert.pop(tm["halfflows"][2], None)
        g.hip(ts, tm["project"], tm["halfflows"][2], "DEFAULT", ERR_B, x["xid"])
        g.last_alert[tm["halfflows"][2]] = ts
        g.on_failed = getattr(g, "on_failed", [])
        g.on_failed.append((ts - secs(6), x, 2, {}))
    # full trace of a failing exchange (trace panel) and a successful YHIPDELVRY07 -> SAPNE one
    tm = EXCHANGES["idoc_ne_yhipdelvry07"]
    fx = g.new_x(tm, T("10:14:22"), dur_ms=6200)
    P, I, E, X = "INPROGRESS", "INFO", "ENTRYINFO", "EXITINFO"
    RB = "SAP RFC Error: Failed to fetch ConfigForDocSending"
    flines(g, fx, fx["t0"], [
        (0.0, 0, E, P, "IFP_PUB001", "", "Half-flow 1/4 started: delivery confirmation from Manhattan", 1, "1/4"),
        (0.3, 0, I, P, "IFP_MAP001", "", "IDoc YHIPDELVRY07 built for SAPNE", 1, "1/4"),
        (0.8, 0, X, P, "IFP_PUB002", "", "Half-flow 1/4 completed", 1, "2/4"),
        (0.9, 1, E, P, "IFP_PUB001", "", "Half-flow 2/4 started", 2, "2/4"),
        (1.4, 1, X, P, "IFP_PUB002", "", "Half-flow 2/4 completed", 2, "3/4"),
        (1.5, 2, E, P, "IFP_PUB001", "", "Half-flow 3/4 started: call Workato recipe 'IDoc Out - YHIPDELVRY07 to SAPNE'", 3, "3/4"),
        (1.6, 2, I, P, "IFP_INV001", "", "Workato invoke attempt 1/3", 3, "3/4"),
        (2.4, 2, "ERROR", P, "IFP_RTG001", RB, RB + " (attempt 1/3)", 3, "3/4"),
        (2.6, 2, I, P, "IFP_INV001", "", "Retry 1/3 in 1 s", 3, "3/4"),
        (3.7, 2, "ERROR", P, "IFP_RTG001", RB, RB + " (attempt 2/3)", 3, "3/4"),
        (3.9, 2, I, P, "IFP_INV001", "", "Retry 2/3 in 2 s", 3, "3/4"),
        (6.2, 2, "ERROR", "FAILED", "IFP_RTG001", RB, RB + " (Workato recipe " + tm["exchange"] + ")", 3, "3/4"),
    ])
    g.on_failed = getattr(g, "on_failed", [])

    # ---- Workato jobs for every IDoc exchange line ---------------------------------
    for s in list(g.sonar):
        ex = EXCHANGES_BY_NAME.get(s["exchange"])
        if (not ex or not ex["key"].startswith("idoc_") or s["event.level"] not in ("EXITINFO", "ERROR")
                or s["exchange.status"] not in ("FAILED", "COMPLETE")):
            continue
        ts = dt_of(s)
        xid = s["exchange.id"]
        recipe = f"IDoc Out - {ex['object_name']} to {ex['destination']}"
        if s["exchange.status"] == "FAILED":
            g.workato_job(ts, recipe, "failed", r.randint(900, 4200),
                          ERR_A if r.random() < 0.6 else ERR_B, xid)
        else:
            g.workato_job(ts, recipe, "succeeded", r.randint(700, 3000), None, xid)
    # first Workato failure at exactly 09:52 (recipe function call failed)
    tmc = EXCHANGES["idoc_ce_ylcd01"]
    x0 = g.new_x(tmc, FAIL0 + secs(3))
    g.fail_line(x0, FAIL0 + secs(3), 2, "DEFAULT", ERR_B, f"{ERR_B} (Workato recipe {tmc['exchange']})")
    g.workato_job(FAIL0 + secs(3), "IDoc Out - YLCD01 to SAPCE", "failed", 1800, ERR_A, x0["xid"])

    gen_hourly_reports(g, lambda h, base: (base, f"GLBL_SCHEDULER_WAITFORFILE ({base - 60}), GLBL_CTRLM_MASTERDATA_BATCH (3)"))

    # ---- Splunk: RFC gateway health green ------------------------------------------
    for hm in ("09:50:00", "10:10:00", "10:30:00", "10:50:00"):
        if T(hm) < g.end:
            g.splunk_rec(T(hm), "SAPNE_RFC_GATEWAY", "health",
                         "SAPNE RFC gateway health check OK: gateway reachable, 0 refused connections, sync RFC round-trip 41 ms",
                         deployment="sapne-rfc-gw", health="OK")
            g.splunk_rec(T(hm) + secs(15), "SAPCE_RFC_GATEWAY", "health",
                         "SAPCE RFC gateway health check OK: gateway reachable, 0 refused connections, sync RFC round-trip 38 ms",
                         deployment="sapce-rfc-gw", health="OK")

    # ---- Change: vendor notice (NO HIP change) -------------------------------------
    g.change("VND-WKT-2026-09-0917", T("09:40:00"), "Vendor Notice", "WORKATO_PLATFORM",
             "Workato platform release 2026.09.3 rolled to EMEA tenants: connector defaults updated, no customer action announced.",
             "Workato (vendor)", "n/a - vendor release, no HIP change record", "n/a - vendor managed",
             {"informational": True})

    # ---- ServiceNow ----------------------------------------------------------------
    fx1 = [s for s in g.sonar if s["exchange.status"] == "FAILED" and dt_of(s) >= T("10:20:00")]
    xa = fx1[0]["exchange.id"] if fx1 else ""
    xb = fx1[5]["exchange.id"] if len(fx1) > 5 else xa
    dup = sc["duplicate_incidents"]
    g.incident(sc["incident_number"], T("10:25:12"), "Shipment completed in Manhattan but not integrated to SAP",
               f"Shipment completed in Manhattan (CZ warehouse) but no delivery IDoc reached SAP. Exchange {xa} FAILED at half-flow 3/4.",
               2, "user", notes=[(T("10:40:00"), "L1: replay attempted for 3 exchanges, failed again with the same error.")])
    g.incident(dup[0], T("10:40:20"), "Shipment confirmation not integrated to SAP - PL warehouse",
               f"Second warehouse, same symptom. Example exchange {xb}.", 2, "user", parent=sc["incident_number"])
    hm = sorted(g.hipmon, key=lambda a: a["timestamp"])
    g.incident(dup[1], T("10:03:12"), hm[0]["subject"], hm[0]["error_text"] + f" (exchange.id {hm[0]['exchange.id']})", 3, "auto", parent=sc["incident_number"], rule=hm[0]["rule_id"])
    g.incident(dup[2], T("10:05:40"), hm[1]["subject"], hm[1]["error_text"] + f" (exchange.id {hm[1]['exchange.id']})", 3, "auto", parent=sc["incident_number"], rule=hm[1]["rule_id"])
    g.incident(dup[3], T("10:07:02"), hm[2]["subject"], hm[2]["error_text"] + f" (exchange.id {hm[2]['exchange.id']})", 3, "auto", parent=sc["incident_number"], rule=hm[2]["rule_id"])

    gen_apigee_baseline(g)
    gen_workato_baseline(g)
    gen_noise_hosts(g)
    gen_chaff_changes(g, "s3")
    gen_late(g)


# --------------------------------------------------------------------------
# Scenario 4 -- silent stalled exchange
# --------------------------------------------------------------------------

def build_s4(g):
    r = g.rng
    sc = g.sc
    gen_kafka(g, lambda gr, t: 0)
    w = default_weights()
    gen_bg(g, w, None)
    gen_special_flows(g, bad_bpm=2)

    # ---- the 02:00 file ---------------------------------------------------------
    tm = EXCHANGES["bpm_fm"]
    t0 = T("02:00:04")
    x = g.new_x(tm, t0 + secs(3), dur_ms=3000, t0=t0)
    x["oid"] = "BPM_to_FM_0200.csv"
    g.mft_row(T("02:00:03"), 3, "BPM_to_FM_0200.csv", "FRHIPGPRMFTSI02", "FM_FRCPD", "SUCCESS", 4_100_000 + 3312,
              128400, 77032, x["xid"])
    # exchange starts, hf1 only; NO half-flow-2 event ever
    g.sline(x, T("02:00:07"), 0, "ENTRYINFO", "INPROGRESS", "IFP_PUB001", "", "Half-flow 1/4 started: file BPM_to_FM_0200.csv received from SFG",
            0, 1, "2/4")
    g.sline(x, T("02:00:09"), 0, "EXITINFO", "INPROGRESS", "IFP_PUB002", "", "Half-flow 1/4 completed: file handed to ESB adapter",
            2100, 1, "2/4")
    flines(g, x, T("02:00:07"), [
        (0.2, 0, "INFO", "INPROGRESS", "IFP_MAP001", "", "SFG business process BPM_to_FM_0200 delivered file, size 4,103,312 bytes", 1, "2/4"),
        (0.4, 0, "INFO", "INPROGRESS", "IFP_MAP001", "", "Connector session ESB-adapter-2: file accepted, spooling to HIP staging", 1, "2/4"),
        (0.9, 0, "INFO", "INPROGRESS", "IFP_MAP001", "", "Staging complete: 4,103,312 bytes written", 1, "2/4"),
        (1.3, 0, "INFO", "INPROGRESS", "IFP_MAP001", "", "Exchange event published to ESB adapter queue hip.mft.in.anaplan", 1, "2/4"),
        (1.8, 0, "INFO", "INPROGRESS", "IFP_MAP001", "", "Publish acknowledged by MFT adapter (no consumer response awaited)", 1, "2/4"),
    ])
    g.stalled_x = x

    # ---- export log (Control-M job) normal at 01:58 --------------------------------
    g.splunk_rec(T("01:58:12"), "SGLORHIPPETLPC1", "job",
                 "Control-M job ANAPLAN_BPM_EXPORT ended OK: file BPM_to_FM_0200.csv written, 128400 rows, trailer OK",
                 rows=128400, job="ANAPLAN_BPM_EXPORT", job_status="OK")

    # ---- patching window (routine, approved) ----------------------------------------
    g.change("CHG0044901", T("01:30:00"), "Standard", "FRHIPGPRMFTSI02",
             "EMEA monthly patching window: OS patching and reboot of MFT hosts FRHIPGPRMFTSI01/02 (01:30-02:15)",
             "MFT team", "Approved", "Boot previous kernel; restore snapshot")
    for hh, hm in (("FRHIPGPRMFTSI01", "01:32:10"), ("FRHIPGPRMFTSI02", "01:38:40")):
        g.splunk_rec(T(hm), hh, "event", f"{hh} reboot for patching (uptime reset)", severity=4, uptime_min=0)
    g.splunk_rec(T("01:41:05"), "FRHIPGPRMFTSI02", "event",
                 "SFG ESB adapter: 0 of 4 sessions active after reboot, reconnect attempt 3", severity=3)
    g.splunk_rec(T("02:14:22"), "FRHIPGPRMFTSI02", "event",
                 "SFG ESB adapter: 4 of 4 sessions re-established", severity=4)
    g.splunk_rec(T("02:15:00"), "FRHIPGPRMFTSI02", "event", "Patching complete on FRHIPGPRMFTSI02 (uptime 36 min)", severity=4)

    # ---- hourly reports: exchange listed under InProgress only ----------------------
    def inprog(h, base):
        listing = f"GLBL_SCHEDULER_WAITFORFILE ({base - 60}), GLBL_CTRLM_MASTERDATA_BATCH (3)"
        n = base
        if h > T("02:00:09"):
            age = h - T("02:00:07")
            listing += f", GLBL_OPSF_ANAPLAN_BPM_to_FM (1, oldest {int(age.total_seconds() // 3600)}h{int(age.total_seconds() % 3600 // 60):02d}m)"
            n += 1
        return n, listing

    gen_hourly_reports(g, inprog, critical_failed_fn=lambda h, n: 0)

    # ---- downstream: FRCPD DB lock ---------------------------------------------------
    fk = EXCHANGES["frcpd_fkf"]
    lock_ids = []
    for ts in ("07:41:10", "07:47:32", "07:52:05", "07:55:40"):
        xx = g.new_x(fk, T(ts), dur_ms=3_600_000)
        g.fail_line(xx, T(ts), 1, "TEC01", "Database lock: unable to acquire lock on FM_STAGING_TBL (waited 3600 s)",
                    "ORA-00054: resource busy and acquire with NOWAIT specified; FKF generation blocked by session holding FM_STAGING_TBL")
        lock_ids.append(xx)
    g.hip(T("07:52:20"), "FRCPD", fk["halfflows"][1], "TEC01",
             "Database lock: unable to acquire lock on FM_STAGING_TBL (waited 3600 s)", lock_ids[0]["xid"])
    g.hip(T("07:56:05"), "FRCPD", fk["halfflows"][1], "TEC01",
             "Database lock: unable to acquire lock on FM_STAGING_TBL (waited 3600 s)", lock_ids[2]["xid"])
    g.hip(T("07:58:30"), "FRCPD", fk["halfflows"][2], "COM01",
             "FKF file not generated: upstream FM staging incomplete", lock_ids[3]["xid"])
    g.splunk_rec(T("07:49:00"), "SGLORHIPPETLPC1", "alert", "FRCPD FM database session lock wait > 3000 s",
                 rule_id="SPL-DBLOCK001", severity=3)

    # ---- ServiceNow --------------------------------------------------------------------
    dup = sc["duplicate_incidents"]
    g.incident(sc["incident_number"], T("07:57:20"), "FRCPD database locked, FKF not generated",
               "FRCPD database is locked and the FKF file was not generated this morning. FM load appears incomplete.",
               2, "user", notes=[(T("08:05:00"), "L1: FM DBA confirmed lock held by the 07:30 FM load; load input looks incomplete.")])
    g.incident(dup[0], T("07:59:10"), "[AUTO]|FRCPD|GLBL_FRCPD_FM_FKF_GENERATION_02_ESB|TEC01|ETP_TEC01",
               f"Database lock: unable to acquire lock on FM_STAGING_TBL (exchange.id {lock_ids[0]['xid']})", 3, "auto", parent=sc["incident_number"], rule="HIPMON-TEC01")
    g.incident(dup[1], T("08:00:05"), "[AUTO]|FRCPD|GLBL_FRCPD_FM_FKF_GENERATION_03_ESB|COM01|ETP_COM01",
               f"FKF file not generated: upstream FM staging incomplete (exchange.id {lock_ids[3]['xid']})", 3, "auto", parent=sc["incident_number"], rule="HIPMON-COM01")
    g.incident(dup[2], T("08:02:40"), "CAPLINERR-DBLOCK FRCPD FM database session lock wait",
               "Splunk rule SPL-DBLOCK001 fired: lock wait > 3000 s", 3, "auto", parent=sc["incident_number"], rule="SPL-DBLOCK001")

    gen_apigee_baseline(g)
    gen_workato_baseline(g)
    gen_noise_hosts(g)
    gen_chaff_changes(g, "s4")
    gen_late(g)


# --------------------------------------------------------------------------
# Scenario 5 -- transco-cache
# --------------------------------------------------------------------------

def build_s5(g):
    r = g.rng
    sc = g.sc
    F0 = T("00:55:03")
    F1 = T("01:13:41")
    ERR = "Connection refused: hip-fwk-transco-cache.hip-cloud-esb.svc.cluster.local:8080"
    MSG = ("Unhandled Internal error. TranscoInvoke failed: java.net.ConnectException: " + ERR)
    codes = {"SAPITCOMMON": ["IVK003", "IVK003", "TEC01"], "KEPLER_NEXTGEN": ["TEC01", "IVK003", "GEN01"],
             "PROCESSOUT": ["GEN01", "IVK003", "TEC01"], "AMAZONCOMMON": ["IVK003", "GEN01", "TEC01"]}

    kl_nodes = [(T("01:04:30"), 0), (T("01:06:00"), 900), (T("01:10:00"), 4200), (T("01:14:00"), 6800),
                (T("01:18:00"), 3000), (T("01:24:00"), 0)]
    peak = {"sapit-01-default": 1.0, "kepler-01-default": 0.8, "procout-01-default": 0.55, "amazon-01-default": 0.4}

    def lag_fn(gr, t):
        if gr not in peak:
            return 0
        return interp(kl_nodes, t) * peak[gr] + (int(t.timestamp()) % 5) * 3

    gen_kafka(g, lag_fn)

    def hook(tm, t):
        if not tm["transco"] or not (F0 <= t < F1):
            return None
        if r.random() > 0.9:
            return None
        hf = r.choice(tm["transco"])
        return {"kind": "FAILED", "hf": hf, "code": r.choice(codes[tm["project"]]), "reason": ERR, "msg": MSG,
                "alert_min_ts": T("00:56:00"), "dedup": 6}

    w = default_weights()
    for k in naming.TRANSCO_KEYS:
        w[k] = 1.6
    gen_bg(g, w, hook)
    gen_special_flows(g)
    g.on_failed = getattr(g, "on_failed", [])

    # guarantee every one of the 32 transco half-flows fails at least once
    plan = [(k, hf) for k in naming.TRANSCO_KEYS for hf in EXCHANGES[k]["transco"]]
    r.shuffle(plan)
    span = (F1 - F0).total_seconds() - 90
    for i, (k, hf) in enumerate(plan):
        tm = EXCHANGES[k]
        ts = F0 + secs(5 + span * (i / len(plan)) + r.uniform(0, 10))
        if k == "sapit_so" and hf == 0:
            ts = F0  # the first error, exactly 00:55:03
        x = g.new_x(tm, ts)
        code = r.choice(codes[tm["project"]])
        if k == "sapit_so" and hf == 0:
            x["t0"] = ts - secs(5.6)
            P = "INPROGRESS"
            flines(g, x, x["t0"], [
                (0.0, 0, "ENTRYINFO", P, "IFP_PUB001", "", "Half-flow 1/4 started: sales order from SFDC_CX", 1, "1/4"),
                (0.4, 0, "INFO", P, "IFP_MAP001", "", "Sales order mapped for SAPIT", 1, "1/4"),
                (1.0, 0, "INFO", P, "IFP_INV001", "", "TranscoInvoke: calling hip-fwk-transco-cache (plant/material transcoding), attempt 1/3", 1, "1/4"),
                (1.6, 0, "ERROR", P, "IFP_RTG001", ERR, MSG + " (attempt 1/3)", 1, "1/4"),
                (2.0, 0, "INFO", P, "IFP_INV001", "", "TranscoInvoke retry 1/3 in 1 s", 1, "1/4"),
                (3.2, 0, "ERROR", P, "IFP_RTG001", ERR, MSG + " (attempt 2/3)", 1, "1/4"),
                (3.5, 0, "INFO", P, "IFP_INV001", "", "TranscoInvoke retry 2/3 in 1 s", 1, "1/4"),
                (4.7, 0, "ERROR", P, "IFP_RTG001", ERR, MSG + " (attempt 3/3)", 1, "1/4"),
                (4.9, 0, "INFO", P, "IFP_INV001", "", "TranscoInvoke retries exhausted, routing exchange to error handler", 1, "1/4"),
                (5.3, 0, "INFO", P, "IFP_PUB001", "", "Exchange written to error queue hip.error.sapit for replay", 1, "1/4"),
            ])
        g.fail_line(x, ts, hf, code, ERR, MSG)
        g.alert_failure(x, hf, code, ERR, ts, dedup_min=6, min_ts=T("00:56:00"), delay=(45, 90) if ts < T("00:56:00") else (4, 40))
        g.on_failed.append((ts, x, hf, {}))

    # ---- replays succeed after the pod is Ready --------------------------------------
    failed = sorted(g.on_failed, key=lambda f: f[0])
    rt = T("01:16:20")
    for i, (ts, x, hf, res) in enumerate(failed):
        at = rt + secs(i * 5.5 + r.uniform(0, 3))
        if at >= g.end:
            break
        tm = x["tm"]
        nhf = len(tm["halfflows"])
        g.sline(x, at, nhf - 1, "EXITINFO", "REPLAYED", "IFP_RPL001", "",
                "Replay successful: exchange completed after replay (originally failed with Connection refused)",
                int(2000 + r.uniform(0, 1500)), nhf, f"0/{nhf}")
    g.replayed = len(failed)

    # volumes + hourly
    gen_volume_records(g, [("transco-calling exchanges", lambda t: (int(4300 + 60 * math.sin(t.minute)), 4300, ""))])

    def crit_failed(h, n):
        return n

    def inprog(h, base):
        return base, f"GLBL_SCHEDULER_WAITFORFILE ({base - 60}), GLBL_CTRLM_MASTERDATA_BATCH (3)"

    gen_hourly_reports(g, inprog)

    # ---- Splunk: transco-cache pod ------------------------------------------------------
    tp = g.pod("hip-fwk-transco-cache", 1)[0]
    t = g.start
    while t <= g.end:
        if t < T("00:20:00"):
            v, rc = 58 + (t - g.start).total_seconds() / 60 * 1.9, 0
        else:
            v, rc = 22 + (t - T("00:20:00")).total_seconds() / 60 * 0.7, 1
        v = min(96, v + r.uniform(-0.8, 0.8))
        g.splunk_rec(t, tp, "metric", f"memory {v:.1f}% of limit", metric="mem_pct", value=round(v, 1), pod=tp,
                     restart_count=rc, deployment="hip-fwk-transco-cache", cpu_pct=int(18 + r.uniform(0, 12)))
        t += timedelta(minutes=1)
    g.splunk_rec(T("00:20:06"), tp, "alert", f"pod {tp} restarted (restart 1): container terminated, exit code 137",
                 rule_id="SPL-PODRST001", pod=tp, restart_count=1, deployment="hip-fwk-transco-cache", severity=4)
    g.splunk_rec(T("01:14:10"), tp, "event",
                 f"pod {tp} Running and Ready=True (last transition 01:13:41), restartCount=1, uptime 54m",
                 pod=tp, restart_count=1, deployment="hip-fwk-transco-cache", severity=4, ready=True)
    g.splunk_rec(T("01:30:00"), tp, "event",
                 f"pod {tp} Running and Ready=True, restartCount=1, uptime 70m", pod=tp, restart_count=1,
                 deployment="hip-fwk-transco-cache", severity=4, ready=True)
    for hm in ("00:40:00", "01:05:00", "01:25:00"):
        g.splunk_rec(T(hm), "AKS-HIP-EMEA-PRD", "event",
                     "namespace hip-cloud-esb: 41/41 non-cache pods Ready; node network errors 0; CoreDNS p99 4 ms; "
                     "no ConnectionRefused from any non-transco service", severity=4)

    # ---- Apigee 5xx across nine endpoints ---------------------------------------------------
    def apg(t):
        if T("01:08:00") <= t <= T("01:18:00"):
            frac = 1.0 - abs((t - T("01:12:00")).total_seconds()) / 480.0
            for ep in APIGEE_ENDPOINTS[:9]:
                g.apigee.append({"minute": iso_s(t), "endpoint": ep, "status": 503,
                                 "count": max(3, int(r.randint(30, 90) * frac)), "p99_latency_ms": r.randint(8000, 15000),
                                 "sample_exchange_ids": [failed[r.randrange(len(failed))][1]["xid"]]})

    gen_apigee_baseline(g, hook=apg)

    # ---- ServiceNow: six auto incidents from six different rules ----------------------------------
    hm = sorted(g.hipmon, key=lambda a: a["timestamp"])
    pick = {}
    for a in hm:
        pick.setdefault(a["rule_id"], a)
    dup = sc["duplicate_incidents"]
    six = [
        (sc["incident_number"], T("01:15:04"), pick["HIPMON-IVK003"]["subject"], pick["HIPMON-IVK003"]["error_text"], "HIPMON-IVK003"),
        (dup[0], T("01:15:18"), pick["HIPMON-TEC01"]["subject"], pick["HIPMON-TEC01"]["error_text"], "HIPMON-TEC01"),
        (dup[1], T("01:15:31"), pick["HIPMON-GEN01"]["subject"], pick["HIPMON-GEN01"]["error_text"], "HIPMON-GEN01"),
        (dup[2], T("01:15:47"), "KFK-LAG-004 consumer lag on sapit-01-default / kepler-01-default / procout-01-default / amazon-01-default",
         "Consumer lag rule fired on four processing groups simultaneously", "KFK-LAG-004"),
        (dup[3], T("01:16:02"), "APG-5XX-012 Apigee 5xx rate across nine endpoints", "5xx rate above threshold on nine EMEA endpoints", "APG-5XX-012"),
        (dup[4], T("01:16:20"), "[SONAR-OPS][PRD] HLTH_CHK critical exchanges: Failed above threshold",
         "Hourly critical exchange report 01:00Z: Failed above threshold", "SNR-HRLY-CRIT"),
    ]
    for i, (num, ts, short, desc, rule) in enumerate(six):
        if rule in pick:
            desc = f"{desc} (exchange.id {pick[rule]['exchange.id']})"
        g.incident(num, ts, short, desc, 3 if i else 2, "auto", parent=None if i == 0 else sc["incident_number"], rule=rule,
                   notes=[(T("01:24:00"), "L1: replayed failed exchanges; replay succeeded (went into warning as per design).")] if i == 0 else None)

    gen_workato_baseline(g)
    gen_noise_hosts(g)
    gen_chaff_changes(g, "s5")
    gen_late(g)


BUILDERS = {"s1": build_s1, "s2": build_s2, "s3": build_s3, "s4": build_s4, "s5": build_s5}


def gen_late(g):
    late = g.sc["late"]
    rec = {"@timestamp": iso_s(T(late["ts"])), "source": late["source"], "component": late["component"],
           "severity": late["severity"], "message": late["message"], "correlation_id": None,
           "delayed_ingest": True}
    g.late.append(rec)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_ndjson(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def write_scenario(g):
    d = os.path.join(DATA_DIR, g.sc["slug"])
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    g.sonar.sort(key=lambda s: s["@timestamp"])
    g.hipmon.sort(key=lambda s: s["timestamp"])
    g.splunk.sort(key=lambda s: s["@timestamp"])
    g.workato.sort(key=lambda s: s["ended_at"])
    g.apigee.sort(key=lambda s: (s["minute"], s["endpoint"], s["status"]))
    g.mft.sort(key=lambda s: s["start_time"])
    g.snow.sort(key=lambda s: s["opened_at"])
    g.changes.sort(key=lambda s: s["implemented_at"])
    write_ndjson(os.path.join(d, "sonar-exchanges.ndjson"), g.sonar)
    write_csv(os.path.join(d, "kafka-lag.csv"),
              ["timestamp", "consumer_group", "topic", "partition", "current_offset", "log_end_offset", "lag"], g.kafka)
    write_ndjson(os.path.join(d, "splunk-hosts.ndjson"), g.splunk)
    write_json(os.path.join(d, "hipmon-alerts.json"), g.hipmon)
    write_json(os.path.join(d, "workato-jobs.json"), g.workato)
    write_json(os.path.join(d, "apigee-errors.json"), g.apigee)
    cols = ["transfer_id", "filename", "source", "target", "start_time", "end_time", "status", "bytes",
            "declared_rows", "actual_rows", "exchange_id"]
    write_csv(os.path.join(d, "mft-transfers.csv"), cols, [[m[c] for c in cols] for m in g.mft])
    write_json(os.path.join(d, "servicenow-incidents.json"), g.snow)
    write_json(os.path.join(d, "change-records.json"), g.changes)
    write_ndjson(os.path.join(d, "late-evidence.ndjson"), g.late)
    return d


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for sc in SCENARIOS:
        g = G(sc)
        BUILDERS[sc["id"]](g)
        d = write_scenario(g)
        print(f"[{sc['slug']}] sonar={len(g.sonar)} hipmon={len(g.hipmon)} (sonar+hipmon={len(g.sonar) + len(g.hipmon)}) "
              f"splunk={len(g.splunk)} kafka={len(g.kafka)} workato={len(g.workato)} apigee={len(g.apigee)} "
              f"mft={len(g.mft)} snow={len(g.snow)} changes={len(g.changes)}")


if __name__ == "__main__":
    main()
