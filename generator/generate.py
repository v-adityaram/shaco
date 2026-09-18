#!/usr/bin/env python3
"""
generator/generate.py -- deterministic raw-signal generator for the
"Incident Response AI" POC (Meridian Retail synthetic estate).

Standard library only. Fixed random seed -> byte-identical output across
runs. For each scenario in generator/scenarios.py, writes 8 raw files into
data/<slug>/:

    elk-logs.ndjson
    kafka-lag.csv
    apigee-errors.json
    apim-errors.json
    mft-transfers.csv
    servicenow-incidents.json
    change-records.json
    late-evidence.ndjson

This module is deliberately mechanical: it encodes scenario facts into
realistic raw-file shapes plus surrounding baseline noise. No "diagnosis"
or hypothesis ranking happens here -- that is out of scope for the
generator and normaliser layers.
"""

import csv
import io
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import naming  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")

DATE = "2026-09-18"
IST_OFFSET = timedelta(hours=5, minutes=30)

random.seed(42)
rng = random.Random(42)

# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------

def t(hms, date=DATE):
    """'HH:MM:SS' on `date` -> aware UTC datetime."""
    dt = datetime.strptime(f"{date} {hms}", "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def iso_utc(dt):
    """Aware UTC datetime -> ISO-8601 string with explicit +00:00 offset."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def iso_ist_naive(dt_utc):
    """Aware UTC datetime -> naive local IST string, NO offset suffix
    (the deliberate MFT wrinkle)."""
    local = dt_utc + IST_OFFSET
    return local.strftime("%Y-%m-%d %H:%M:%S")


def minutes(n):
    return timedelta(minutes=n)


def seconds(n):
    return timedelta(seconds=n)


def rand_hex(n=4):
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


# --------------------------------------------------------------------------
# Generic record builders
# --------------------------------------------------------------------------

NOISE_MESSAGES = [
    "health check OK",
    "readiness probe OK",
    "cache refresh completed",
    "config reload no-op, no changes detected",
    "connection pool stats: healthy",
    "session cache hit ratio {r:.2f}",
    "scheduled heartbeat",
    "batch processed {n} records",
    "metrics flush OK",
    "GC minor collection, pause {p}ms",
]

NOISE_BATCH_COMPONENT = "nightly-settlement-batch"
NOISE_BATCH_POD_PREFIX = "settle-batch-job"


def elk_doc(ts_dt, service_cmdb, level, severity, message,
            rule_id=None, rule_name=None, correlation_id=None,
            pod_hash=None, extra=None, index_service=None):
    """Build one raw ELK ndjson-style document."""
    info = naming.SERVICES.get(service_cmdb)
    if info is not None:
        pod = naming.pod_name(service_cmdb, pod_hash or rand_hex())
        index = naming.elk_index(index_service or service_cmdb)
    else:
        # non-catalogued component (batch job, oracle-oms, partner feed, etc.)
        pod = f"{NOISE_BATCH_POD_PREFIX}-{pod_hash or rand_hex()}" if service_cmdb == NOISE_BATCH_COMPONENT else None
        index = f"app-{service_cmdb.replace('_', '').replace('-', '')}-2026.09.18"
    doc = {
        "@timestamp": iso_utc(ts_dt),
        "log.level": level,
        "service.name": service_cmdb,
        "kubernetes.pod.name": pod,
        "_index": index,
        "rule.id": rule_id,
        "rule.name": rule_name,
        "event.severity": severity,
        "message": message,
        "labels.correlation_id": correlation_id,
    }
    if extra:
        doc.update(extra)
    return doc


def kafka_row(ts_dt, cg, topic, partition, current_offset, log_end_offset):
    return {
        "timestamp": iso_utc(ts_dt),
        "consumer_group": cg,
        "topic": topic,
        "partition": partition,
        "current_offset": current_offset,
        "log_end_offset": log_end_offset,
        "lag": max(0, log_end_offset - current_offset),
    }


def gw_agg(endpoint, status, count, p99, correlation_ids):
    return {
        "endpoint": endpoint,
        "status": status,
        "count": count,
        "p99_latency_ms": p99,
        "sample_correlation_ids": correlation_ids,
    }


def mft_row(transfer_id, filename, source, target, start_utc, end_utc,
            status, byte_size, declared_rows, actual_rows):
    return {
        "transfer_id": transfer_id,
        "filename": filename,
        "source": source,
        "target": target,
        "start_time": iso_ist_naive(start_utc),
        "end_time": iso_ist_naive(end_utc),
        "status": status,
        "bytes": byte_size,
        "declared_rows": declared_rows,
        "actual_rows": actual_rows,
    }


def sn_ticket(number, opened_at, short_desc, desc, priority, group, state,
              work_notes, opened_by):
    return {
        "number": number,
        "opened_at": iso_utc(opened_at),
        "short_description": short_desc,
        "description": desc,
        "priority": priority,
        "assignment_group": group,
        "state": state,
        "work_notes": work_notes,
        "opened_by": opened_by,
    }


def change_record(number, ctype, implemented_at, component, desc,
                   implementer, approval_state, rollback_plan, extra=None):
    rec = {
        "change_number": number,
        "type": ctype,
        "implemented_at": iso_utc(implemented_at),
        "component": component,
        "description": desc,
        "implementer": implementer,
        "approval_state": approval_state,
        "rollback_plan": rollback_plan,
    }
    if extra:
        rec.update(extra)
    return rec


# --------------------------------------------------------------------------
# Baseline noise
# --------------------------------------------------------------------------

def baseline_elk_noise(start_dt, end_dt, interval_seconds, services,
                        exclude_windows=None):
    """Heartbeat/INFO noise: one line per service, per interval tick,
    staggered within the tick, across [start_dt, end_dt)."""
    out = []
    cursor = start_dt
    while cursor < end_dt:
        for svc in services:
            msg_template = rng.choice(NOISE_MESSAGES)
            msg = msg_template.format(
                r=rng.uniform(0.85, 0.98), n=rng.randint(40, 400), p=rng.randint(5, 45)
            )
            level = "INFO" if rng.random() > 0.03 else "DEBUG"
            out.append(elk_doc(
                cursor + seconds(rng.randint(0, max(1, interval_seconds - 1))),
                svc, level, 4, msg,
            ))
        cursor += seconds(interval_seconds)
    return out


def two_noise_alerts(window_start, window_end):
    """The two pure-noise alerts from an unrelated nightly batch job."""
    mid = window_start + (window_end - window_start) / 3
    later = window_start + (window_end - window_start) * 2 / 3
    return [
        elk_doc(mid, NOISE_BATCH_COMPONENT, "WARN", 3,
                "settlement batch retry 2/5, transient upstream timeout (unrelated job)",
                rule_id="ELK-R-0401", rule_name="batch-retry-threshold"),
        elk_doc(later, NOISE_BATCH_COMPONENT, "WARN", 3,
                "settlement batch queue depth 340, above soft threshold (unrelated job)",
                rule_id="ELK-R-0402", rule_name="batch-queue-depth"),
    ]


# ==========================================================================
# S1 -- memory leak in inventory-reservation
# ==========================================================================

def gen_s1(scn):
    cid = scn["correlation_id"]
    svc = "inventory-reservation"
    pod_hash = "7d4f"
    win_start, win_end = t("07:40:00"), t("10:40:00")

    elk = baseline_elk_noise(win_start, win_end, 75,
                              naming.CORE_SERVICE_NAMES + naming.GATEWAY_NAMES)
    elk += two_noise_alerts(win_start, win_end)

    # pre-incident heap climbing slowly (07:40 -> 08:40), normal-looking
    heap = 44.0
    cur = t("07:40:00")
    while cur < t("08:40:00"):
        heap += rng.uniform(0.35, 0.55)
        elk.append(elk_doc(cur, svc, "INFO", 4,
                            f"container.memory.usage.pct {heap:.1f}%",
                            pod_hash=pod_hash,
                            extra={"container.memory.usage.pct": round(heap, 1)}))
        cur += minutes(5)

    # contradiction: last-Tuesday volume comparison (capacity report)
    elk.append(elk_doc(t("08:00:00"), "order-intake", "INFO", 4,
                        "weekly capacity report: peak order rate today trending "
                        "1,000/min; last Tuesday (2026-09-09) peak was 1,400/min "
                        "(+40%) with inventory-reservation heap flat under 55%, "
                        "no incident",
                        extra={"comparison.date": "2026-09-09",
                               "comparison.peak_orders_per_min": 1400,
                               "today.peak_orders_per_min": 1000,
                               "comparison.peak_heap_pct": 54.2}))

    # order.enriched producer rate stays flat (rules out retry storm)
    for m in range(0, 150, 15):
        elk.append(elk_doc(win_start + minutes(m), "order-orchestrator", "INFO", 4,
                            f"order.enriched producer rate {rng.randint(820, 890)} msg/min (flat baseline)",
                            extra={"kafka.producer.rate_per_min": rng.randint(820, 890)}))

    # 08:40 buried first symptom
    elk.append(elk_doc(t("08:40:00"), svc, "WARN", 4,
                        "heap utilisation 71.2% on inv-resv-svc, above soft threshold",
                        rule_id="ELK-R-0188", rule_name="heap-utilisation-high",
                        correlation_id=cid, pod_hash=pod_hash,
                        extra={"container.memory.usage.pct": 71.2}))

    # 08:40 -> 09:52 continued climb
    heap = 71.2
    cur = t("08:45:00")
    while cur < t("09:52:00"):
        heap += rng.uniform(0.6, 1.1)
        elk.append(elk_doc(cur, svc, "WARN" if heap > 85 else "INFO", 4 if heap < 90 else 3,
                            f"container.memory.usage.pct {heap:.1f}%",
                            correlation_id=cid, pod_hash=pod_hash,
                            extra={"container.memory.usage.pct": round(heap, 1)}))
        cur += minutes(4)

    # 09:25 GC pause degradation
    elk.append(elk_doc(t("09:25:00"), svc, "WARN", 3,
                        "GC pause p99 climbing: 40ms -> 900ms over last 10 samples",
                        rule_id="ELK-R-0190", rule_name="gc-pause-p99",
                        correlation_id=cid, pod_hash=pod_hash,
                        extra={"gc.pause_p99_ms.start": 40, "gc.pause_p99_ms.now": 900}))
    for m, ms in [(9, 120), (14, 260), (19, 480), (24, 700), (27, 900)]:
        elk.append(elk_doc(t("09:25:00") + minutes(m), svc, "WARN", 3,
                            f"GC pause p99 {ms}ms", correlation_id=cid, pod_hash=pod_hash,
                            extra={"gc.pause_p99_ms": ms}))

    # 09:52 OOMKill restart 1
    elk.append(elk_doc(t("09:52:00"), svc, "ERROR", 1,
                        "OOMKilled: container exceeded memory limit, pod inv-resv-svc-7d4f restart 1",
                        rule_id="ELK-R-0217", rule_name="oomkilled-pod-restart",
                        correlation_id=cid, pod_hash=pod_hash,
                        extra={"kubernetes.container.restart_count": 1}))

    # Kafka lag climbing 09:53 onward
    kafka = []
    cur = win_start
    off = 8_400_000
    while cur < t("09:53:00"):
        off += rng.randint(180, 260)
        kafka.append(kafka_row(cur, "inventory-reservation-cg", "inventory.reserve.req", 0,
                                off, off + rng.randint(5, 40)))
        cur += seconds(15)
    lag = 400
    end_off = off
    while cur < t("10:15:00"):
        end_off += rng.randint(20, 60)          # producer still emitting
        consumed = rng.randint(0, 15)            # consumer barely keeping up (crash loop)
        off = min(off + consumed, end_off)
        lag = end_off - off
        kafka.append(kafka_row(cur, "inventory-reservation-cg", "inventory.reserve.req", 0,
                                off, end_off))
        cur += seconds(15)
    while cur < win_end:
        off += rng.randint(150, 220)
        end_off = off + rng.randint(5, 30)
        kafka.append(kafka_row(cur, "inventory-reservation-cg", "inventory.reserve.req", 0,
                                off, end_off))
        cur += seconds(15)

    # 09:58 restart 2, then restart 3 -- crash loop
    elk.append(elk_doc(t("09:58:00"), svc, "ERROR", 1,
                        "OOMKilled: pod inv-resv-svc-7d4f restart 2, crash loop detected",
                        rule_id="ELK-R-0217", rule_name="oomkilled-pod-restart",
                        correlation_id=cid, pod_hash=pod_hash,
                        extra={"kubernetes.container.restart_count": 2}))
    elk.append(elk_doc(t("09:59:30"), svc, "ERROR", 1,
                        "OOMKilled: pod inv-resv-svc-7d4f restart 3, crash loop detected",
                        rule_id="ELK-R-0217", rule_name="oomkilled-pod-restart",
                        correlation_id=cid, pod_hash=pod_hash,
                        extra={"kubernetes.container.restart_count": 3}))

    # APIM / Apigee aggregates
    apim = []
    apigee = []
    cur = win_start
    m = 0
    while cur < win_end:
        if cur < t("10:02:00"):
            apim.append({"minute": iso_utc(cur), **gw_agg(
                "/internal/inventory/reserve", 200, rng.randint(140, 210), rng.randint(30, 70), [])})
        else:
            apim.append({"minute": iso_utc(cur), **gw_agg(
                "/internal/inventory/reserve", 504, rng.randint(60, 220), rng.randint(4800, 5200),
                [cid])})
        if cur < t("10:04:00"):
            apigee.append({"minute": iso_utc(cur), **gw_agg(
                "/v2/orders", 200, rng.randint(300, 420), rng.randint(80, 140), [])})
        else:
            apigee.append({"minute": iso_utc(cur), **gw_agg(
                "/v2/orders", 502, rng.randint(90, 260), rng.randint(3000, 4200), [cid])})
        cur += minutes(1)
        m += 1

    # MFT baseline (normal, unrelated to this scenario)
    mft = normal_mft_baseline(win_start, win_end)

    # ServiceNow
    sn = [
        sn_ticket("INC0098451", t("10:06:00"),
                  "Order flow degraded -- inventory-reservation",
                  "Auto-raised: elevated 5xx on /v2/orders correlated with "
                  "inv-resv-svc restarts.",
                  1, "Inventory & Fulfilment", "In Progress",
                  ["Auto-correlated with ELK-R-0217 (OOMKilled) and Apigee 502 spike."],
                  "rule-engine"),
        sn_ticket("INC0098452", t("10:07:10"),
                  "Kafka consumer lag critical -- inventory-reservation-cg",
                  "Auto-raised: lag on inventory.reserve.req exceeded 12,000.",
                  2, "Inventory & Fulfilment", "In Progress",
                  ["Duplicate of INC0098451 -- same root incident."],
                  "rule-engine"),
        sn_ticket("INC0098453", t("10:07:45"),
                  "APIM 504 spike -- /internal/inventory/reserve",
                  "Auto-raised by gateway monitoring rule AZ-GW-0091.",
                  2, "Integration", "In Progress",
                  ["Duplicate of INC0098451 -- same root incident."],
                  "rule-engine"),
    ]

    # change records: routine chaff only, nothing causal
    cr = routine_chaff_changes(win_start, win_end, exclude_components={svc})

    late = elk_doc(t("10:24:00"), svc, "WARN", 2,
                    "late signal: pod eviction record shows no memory limit change "
                    "in last 30 days and no recent deploy -- rules out config/deploy "
                    "as the trigger, consistent with a slow leak",
                    correlation_id=cid, pod_hash=pod_hash,
                    extra={"kubernetes.deploy.last_change_days_ago": 34})

    elk.sort(key=lambda d: d["@timestamp"])
    kafka.sort(key=lambda r: r["timestamp"])
    apim.sort(key=lambda r: r["minute"])
    apigee.sort(key=lambda r: r["minute"])
    return {
        "elk": elk, "kafka": kafka, "apigee": apigee, "apim": apim,
        "mft": mft, "servicenow": sn, "change_records": cr, "late": late,
    }


# ==========================================================================
# S2 -- poison message on order.enriched
# ==========================================================================

def gen_s2(scn):
    cid = scn["correlation_id"]
    svc = "order-orchestrator"
    pod_hash = "b91c"
    win_start, win_end = t("10:14:00"), t("12:00:00")

    elk = baseline_elk_noise(win_start, win_end, 44,
                              naming.CORE_SERVICE_NAMES + naming.GATEWAY_NAMES)
    elk += two_noise_alerts(win_start, win_end)

    # contradiction: heap/cpu flat throughout (checkable, periodic)
    cur = win_start
    while cur < win_end:
        heap = rng.uniform(42.0, 48.0)
        cpu = rng.uniform(25.0, 32.0)
        elk.append(elk_doc(cur, svc, "INFO", 4,
                            f"container.memory.usage.pct {heap:.1f}%, cpu {cpu:.1f}%",
                            pod_hash=pod_hash,
                            extra={"container.memory.usage.pct": round(heap, 1),
                                   "container.cpu.usage.pct": round(cpu, 1)}))
        cur += minutes(6)

    # 11:14 partner feed batch accepted, 1 malformed line
    elk.append(elk_doc(t("11:14:00"), "order-intake", "WARN", 3,
                        "Partner B2B batch PB-4471 accepted: 380 lines, 1 malformed "
                        "(negative line quantity, SKU MRD-88213 qty=-4)",
                        rule_id="ELK-R-0305", rule_name="partner-feed-line-validation",
                        correlation_id=cid,
                        extra={"partner.batch_id": "PB-4471", "partner.lines_total": 380,
                               "partner.lines_malformed": 1}))

    # 11:16 deserialisation exception with stack trace
    stack = (
        "com.meridian.order.enrich.DeserializationException: negative "
        "quantity not allowed for field 'lineQty' (value=-4)\n"
        "\tat com.meridian.order.enrich.LineItemDeserializer.deserialize(LineItemDeserializer.java:88)\n"
        "\tat com.meridian.order.enrich.OrderEnrichedConsumer.onMessage(OrderEnrichedConsumer.java:142)\n"
        "\tat org.apache.kafka.clients.consumer.internals.ConsumerCoordinator.invokeConsumer(ConsumerCoordinator.java:602)"
    )
    elk.append(elk_doc(t("11:16:00"), svc, "ERROR", 1,
                        f"Deserialisation exception consuming order.enriched offset 4481209: {stack}",
                        rule_id="ELK-R-0310", rule_name="deserialisation-exception",
                        correlation_id=cid, pod_hash=pod_hash,
                        extra={"kafka.topic": "order.enriched", "kafka.offset": 4481209}))

    # metronomic restarts every 3 min exactly
    for i, tm in enumerate(["11:16:05", "11:19:05", "11:22:05", "11:25:05"], start=1):
        elk.append(elk_doc(t(tm), svc, "ERROR", 1,
                            f"pod ord-orch-svc-{pod_hash} restart {i}: consumer re-attempted "
                            f"offset 4481209 after deserialisation failure",
                            rule_id="ELK-R-0217", rule_name="pod-restart-loop",
                            correlation_id=cid, pod_hash=pod_hash,
                            extra={"kubernetes.container.restart_count": i}))

    # Kafka: current_offset STATIC at 4481209 from 11:20 onward -- decisive
    kafka = []
    cur = win_start
    off = 4_478_900
    while cur < t("11:20:00"):
        off += rng.randint(15, 45)
        kafka.append(kafka_row(cur, "order-enriched-cg", "order.enriched", 0,
                                off, off + rng.randint(0, 10)))
        cur += seconds(15)
    STATIC_OFFSET = 4481209
    end_off = STATIC_OFFSET
    while cur < win_end:
        end_off += rng.randint(8, 30)  # producer keeps writing new messages
        kafka.append(kafka_row(cur, "order-enriched-cg", "order.enriched", 0,
                                STATIC_OFFSET, end_off))
        cur += seconds(15)
    # DLQ topic exists but is never used (no DLQ configured for this topic)
    cur = win_start
    while cur < win_end:
        kafka.append(kafka_row(cur, "order-enriched-cg", "order.enriched.DLQ", 0, 0, 0))
        cur += minutes(1)

    apim = normal_apim_baseline(win_start, win_end, "/internal/order/enrich")

    apigee = []
    cur = win_start
    while cur < win_end:
        if cur < t("11:30:00"):
            apigee.append({"minute": iso_utc(cur), **gw_agg(
                "/v2/orders", 200, rng.randint(280, 400), rng.randint(80, 140), [])})
        else:
            apigee.append({"minute": iso_utc(cur), **gw_agg(
                "/v2/orders", 502, rng.randint(80, 240), rng.randint(3200, 4400), [cid])})
        cur += minutes(1)

    mft = normal_mft_baseline(win_start, win_end)

    sn = [
        sn_ticket("INC0098462", t("11:33:00"),
                  "Order flow degraded -- order-orchestrator",
                  "Auto-raised: deserialisation exceptions and restart loop on order-orchestrator.",
                  1, "Order Platform", "In Progress",
                  ["Auto-correlated with ELK-R-0310 (deserialisation exception)."],
                  "rule-engine"),
        sn_ticket("INC0098463", t("11:33:02"),
                  "Kafka consumer lag critical -- order-enriched-cg",
                  "Auto-raised by Kafka lag monitoring rule.",
                  1, "Order Platform", "In Progress",
                  ["Duplicate of INC0098462 -- same root incident, raised by a different rule."],
                  "rule-engine"),
        sn_ticket("INC0098464", t("11:33:05"),
                  "Gateway 502 spike -- /v2/orders",
                  "Auto-raised by Apigee 5xx rule.",
                  1, "Channel Engineering", "In Progress",
                  ["Duplicate of INC0098462 -- same root incident, raised by a different rule."],
                  "rule-engine"),
    ]

    cr = routine_chaff_changes(win_start, win_end, exclude_components={svc})

    late = elk_doc(t("11:48:00"), "order-intake", "WARN", 2,
                    "late signal: partner feed schema audit confirms PB-4471 line 214 "
                    "carries lineQty=-4, a return-credit line mis-mapped by the partner's "
                    "export -- upstream partner bug confirmed, not a Meridian-side defect",
                    correlation_id=cid,
                    extra={"partner.batch_id": "PB-4471", "partner.offending_line": 214})

    elk.sort(key=lambda d: d["@timestamp"])
    kafka.sort(key=lambda r: r["timestamp"])
    apim.sort(key=lambda r: r["minute"])
    apigee.sort(key=lambda r: r["minute"])
    return {
        "elk": elk, "kafka": kafka, "apigee": apigee, "apim": apim,
        "mft": mft, "servicenow": sn, "change_records": cr, "late": late,
    }


# ==========================================================================
# S3 -- config change breaks internal auth
# ==========================================================================

def gen_s3(scn):
    cid = scn["correlation_id"]
    svc = "pricing-svc"
    win_start, win_end = t("08:12:00"), t("09:57:00")

    elk = baseline_elk_noise(win_start, win_end, 44,
                              naming.CORE_SERVICE_NAMES + naming.GATEWAY_NAMES)
    elk += two_noise_alerts(win_start, win_end)

    # contradiction: cached-price checkouts keep succeeding (partial failure)
    cur = t("09:14:00")
    while cur < win_end:
        elk.append(elk_doc(cur, "order-intake", "INFO", 4,
                            "checkout confirmed using cached price data "
                            "(pricing cache hit, no live APIM call)",
                            extra={"pricing.cache_hit": True}))
        cur += minutes(7)

    elk.append(elk_doc(t("09:15:00"), svc, "ERROR", 2,
                        "order-orchestrator request timeout waiting on pricing-svc, "
                        "retry exhaustion after 3 attempts",
                        rule_id="ELK-R-0450", rule_name="upstream-timeout-retry-exhaustion",
                        correlation_id=cid))
    elk.append(elk_doc(t("09:21:00"), "order-orchestrator", "ERROR", 2,
                        "order completion rate down 80% vs 15-min rolling baseline",
                        rule_id="ELK-R-0455", rule_name="order-completion-rate-drop",
                        correlation_id=cid,
                        extra={"order.completion_rate_pct_of_baseline": 20}))

    apim = []
    cur = win_start
    while cur < win_end:
        if cur < t("09:14:00"):
            apim.append({"minute": iso_utc(cur), **gw_agg(
                "/internal/pricing/quote", 200, rng.randint(150, 220), rng.randint(30, 60), [])})
        else:
            apim.append({"minute": iso_utc(cur), **gw_agg(
                "/internal/pricing/quote", 401, rng.randint(90, 240), rng.randint(40, 90), [cid])})
        cur += minutes(1)

    apigee = []
    cur = win_start
    while cur < win_end:
        if cur < t("09:24:00"):
            apigee.append({"minute": iso_utc(cur), **gw_agg(
                "/v2/orders/{id}/confirm", 200, rng.randint(200, 320), rng.randint(90, 150), [])})
        else:
            apigee.append({"minute": iso_utc(cur), **gw_agg(
                "/v2/orders/{id}/confirm", 504, rng.randint(70, 200), rng.randint(4900, 5400), [cid])})
        # cached-path endpoint keeps returning 200s the whole time (partial failure evidence)
        apigee.append({"minute": iso_utc(cur), **gw_agg(
            "/v2/checkout/cached", 200, rng.randint(60, 120), rng.randint(40, 80), [])})
        cur += minutes(1)

    mft = normal_mft_baseline(win_start, win_end)

    # Kafka: order.enriched producer rate collapses near zero from 09:18
    kafka = []
    cur = win_start
    off = 5_200_000
    while cur < t("09:18:00"):
        off += rng.randint(150, 220)
        kafka.append(kafka_row(cur, "order-enriched-cg", "order.enriched", 0,
                                off, off + rng.randint(0, 15)))
        cur += seconds(15)
    while cur < win_end:
        off += rng.randint(0, 3)  # producer rate near zero
        kafka.append(kafka_row(cur, "order-enriched-cg", "order.enriched", 0,
                                off, off + rng.randint(0, 3)))
        cur += seconds(15)

    sn = [
        sn_ticket("INC0098470", t("09:27:00"),
                  "Order flow degraded -- pricing-svc auth failures",
                  "Auto-raised: 401 spike on /internal/pricing/quote correlated with "
                  "order completion rate drop.",
                  1, "Integration", "In Progress",
                  ["Auto-correlated with APIM 401 rule and ELK-R-0455."],
                  "rule-engine"),
    ]

    # CHG0044219 is the real cause (no approval record) + 6 unrelated chaff changes
    cr = [
        change_record("CHG0044219", "normal", t("09:12:00"), "azure-apim",
                       "APIM policy revision 47: tighten JWT audience validation on "
                       "internal service-to-service routes, deployed via release pipeline",
                       "release-pipeline-svc-account",
                       "no approval record on file",
                       "revert policy to revision 46",
                       extra={"revision": 47}),
    ]
    cr += routine_chaff_changes(win_start, win_end, exclude_components={svc, "azure-apim"},
                                 count=6)

    late = elk_doc(t("09:44:00"), "azure-apim", "WARN", 2,
                    "late signal: APIM policy diff for revision 47 shows "
                    "expected_audience changed from 'meridian-internal' to "
                    "'meridian-internal-v2'; pricing-svc token issuer still mints "
                    "the old 'meridian-internal' audience claim",
                    correlation_id=cid,
                    extra={"apim.policy_revision": 47,
                           "apim.expected_audience_old": "meridian-internal",
                           "apim.expected_audience_new": "meridian-internal-v2"})

    elk.sort(key=lambda d: d["@timestamp"])
    kafka.sort(key=lambda r: r["timestamp"])
    apim.sort(key=lambda r: r["minute"])
    apigee.sort(key=lambda r: r["minute"])
    return {
        "elk": elk, "kafka": kafka, "apigee": apigee, "apim": apim,
        "mft": mft, "servicenow": sn, "change_records": cr, "late": late,
    }


# ==========================================================================
# S4 -- silent MFT truncation
# ==========================================================================

def gen_s4(scn):
    cid = scn["correlation_id"]
    svc = "inventory-reservation"
    win_start, win_end = t("05:00:00"), t("10:45:00")

    elk = baseline_elk_noise(win_start, win_end, 144,
                              naming.CORE_SERVICE_NAMES + naming.GATEWAY_NAMES)
    elk += two_noise_alerts(win_start, win_end)

    # 06:05 file-transfer monitor rule passes (checks status flag only) -- part of contradiction
    elk.append(elk_doc(t("06:05:00"), svc, "INFO", 4,
                        "ELK-R-MFT-004 file transfer monitor: stock_position_0600.csv "
                        "status=SUCCESS (rule checks transfer status flag only, does not "
                        "validate declared_rows vs actual_rows)",
                        rule_id="ELK-R-MFT-004", rule_name="mft-file-transfer-monitor",
                        correlation_id=cid))

    # 09:12 first oversell
    elk.append(elk_doc(t("09:12:00"), svc, "ERROR", 2,
                        "reservation confirmed for SKU MRD-30217 qty 6 -- exceeds "
                        "available stock position (stale WMS data)",
                        rule_id="ELK-R-0512", rule_name="oversell-detected",
                        correlation_id=cid,
                        extra={"oversell.sku": "MRD-30217", "oversell.qty_over": 6}))
    # 09:40 oversell rate climbing, 14 orders
    elk.append(elk_doc(t("09:40:00"), svc, "ERROR", 1,
                        "oversell rate climbing: 14 orders affected in last 30 min, "
                        "all against stock positions sourced from stock_position_0600.csv",
                        rule_id="ELK-R-0512", rule_name="oversell-detected",
                        correlation_id=cid,
                        extra={"oversell.orders_affected": 14,
                               "oversell.source_file": "stock_position_0600.csv"}))
    # a few more discrete oversell lines between 09:12 and 09:40 for realism
    for m, n in [(18, 3), (25, 6), (33, 9)]:
        elk.append(elk_doc(t("09:12:00") + minutes(m), svc, "ERROR", 2,
                            f"oversell rate climbing: {n} orders affected so far",
                            rule_id="ELK-R-0512", rule_name="oversell-detected",
                            correlation_id=cid,
                            extra={"oversell.orders_affected": n}))

    apim = normal_apim_baseline(win_start, win_end, "/internal/inventory/reserve")
    apigee = normal_apigee_baseline(win_start, win_end, "/v2/orders")

    kafka = normal_kafka_baseline(win_start, win_end, "inventory-reservation-cg",
                                   "inventory.reserve.req", start_offset=9_100_000)

    # MFT: baseline hourly transfers, with 06:00 truncated
    mft = []
    hour = 0
    for hh in range(5, 11):
        start_u = t(f"{hh:02d}:00:00")
        if hh == 6:
            end_u = start_u + seconds(38)
            mft.append(mft_row(
                f"MFT-WMS-{hh:02d}00", "stock_position_0600.csv", "OMS-EXPORT-01",
                "WMS-INBOUND", start_u, end_u, "SUCCESS",
                4_137_216, 128400, 77032,
            ))
        else:
            end_u = start_u + seconds(rng.randint(40, 70))
            declared = rng.randint(126000, 130000)
            mft.append(mft_row(
                f"MFT-WMS-{hh:02d}00", f"stock_position_{hh:02d}00.csv", "OMS-EXPORT-01",
                "WMS-INBOUND", start_u, end_u, "SUCCESS",
                rng.randint(6_600_000, 7_000_000), declared, declared,
            ))
        # hourly 3PL dispatch manifest, unrelated, always fine
        dm_start = start_u + minutes(15)
        dm_end = dm_start + seconds(rng.randint(20, 40))
        rows = rng.randint(800, 1400)
        mft.append(mft_row(
            f"MFT-3PL-{hh:02d}15", f"dispatch_manifest_{hh:02d}15.csv",
            "FULFIL-DISPATCH-EXPORT", "3PL-CARRIER-GW",
            dm_start, dm_end, "SUCCESS",
            rng.randint(180_000, 420_000), rows, rows,
        ))
        hour += 1

    sn = [
        sn_ticket("INC0098480", t("10:15:00"),
                  "Multiple oversells traced to WMS stock file -- manual escalation",
                  "Warehouse ops manually raised after noticing repeated oversells "
                  "on SKUs replenished via the 06:00 stock file. Not triggered by any "
                  "monitoring rule -- transfer status showed SUCCESS.",
                  1, "Inventory & Fulfilment", "In Progress",
                  ["Opened manually by warehouse ops, not rule-triggered.",
                   "Suspect 06:00 stock_position file -- requesting MFT team re-check trailer counts."],
                  "warehouse.ops@meridianretail.com"),
    ]

    cr = routine_chaff_changes(win_start, win_end, exclude_components={svc})

    late = elk_doc(t("10:35:00"), "inventory-reservation", "ERROR", 1,
                    "late signal: OMS export job log for 06:00 run shows exit code 137 "
                    "(SIGKILL) at 51,368 of 128,400 rows written -- export was killed "
                    "mid-write by a host memory-pressure eviction on OMS-EXPORT-01",
                    correlation_id=cid,
                    extra={"export.exit_code": 137, "export.rows_written_at_kill": 51368,
                           "export.host": "OMS-EXPORT-01"})

    elk.sort(key=lambda d: d["@timestamp"])
    kafka.sort(key=lambda r: r["timestamp"])
    apim.sort(key=lambda r: r["minute"])
    apigee.sort(key=lambda r: r["minute"])
    mft.sort(key=lambda r: r["start_time"])
    return {
        "elk": elk, "kafka": kafka, "apigee": apigee, "apim": apim,
        "mft": mft, "servicenow": sn, "change_records": cr, "late": late,
    }


# ==========================================================================
# S5 -- downstream saturation from an unrelated job
# ==========================================================================

def gen_s5(scn):
    cid = scn["correlation_id"]
    win_start, win_end = t("21:00:00"), t("22:45:00")

    elk = baseline_elk_noise(win_start, win_end, 44,
                              naming.CORE_SERVICE_NAMES + naming.GATEWAY_NAMES)
    elk += two_noise_alerts(win_start, win_end)

    history_runs = [
        {"month": f"2025-{mm:02d}" if mm <= 12 else f"2026-{mm-12:02d}",
         "duration_min": rng.randint(36, 48), "peak_connections": rng.randint(95, 130),
         "incident": False}
        for mm in range(8, 22)  # 14 months of history ending just before this run
    ]
    elk.append(elk_doc(t("22:00:00"), "oracle-oms", "INFO", 4,
                        "fin-monthend-extract run #171 started (routine, monthly schedule, "
                        "14-month history with no incident)",
                        extra={"job.name": "fin-monthend-extract",
                               "job.run_number": 171,
                               "job.history_runs": history_runs}))

    elk.append(elk_doc(t("22:08:00"), "oracle-oms", "ERROR", 1,
                        "Oracle OMS connection pool at 100% (180/180), wait queue growing",
                        rule_id="ELK-R-0601", rule_name="oracle-pool-saturation",
                        correlation_id=cid,
                        extra={"oracle.pool.used": 180, "oracle.pool.max": 180,
                               "oracle.pool.wait_queue_depth": rng.randint(40, 90)}))

    affected = ["order-intake", "payment-adapter", "fulfilment-dispatch"]
    rule_n = 500
    cur = t("22:09:00")
    for i in range(32):
        svc = affected[i % 3]
        elk.append(elk_doc(cur + seconds(i * 2), svc, "ERROR", 2,
                            f"slow query against Oracle OMS: {rng.randint(2200, 9800)}ms "
                            f"(baseline <150ms)",
                            rule_id=f"ELK-R-{rule_n + i:04d}", rule_name="slow-query-oracle-oms",
                            correlation_id=cid,
                            extra={"query.duration_ms": rng.randint(2200, 9800)}))

    kafka = []
    for topic, cg, start_off in [
        ("order.created", "order-intake-cg", 7_100_000),
        ("order.enriched", "order-enriched-cg", 6_900_000),
        ("inventory.reserve.req", "inventory-reservation-cg", 9_050_000),
        ("fulfilment.dispatch", "fulfilment-dispatch-cg", 3_300_000),
    ]:
        kafka += normal_kafka_baseline(win_start, t("22:11:00"), cg, topic, start_offset=start_off)
        cur = t("22:11:00")
        off = start_off + 5000
        while cur < win_end:
            off += rng.randint(0, 8)
            kafka.append(kafka_row(cur, cg, topic, 0, off, off + rng.randint(800, 3500)))
            cur += seconds(15)

    nine_endpoints = [
        "/v2/orders", "/v2/orders/{id}/confirm", "/v2/checkout", "/v2/inventory/status",
        "/internal/pricing/quote", "/internal/inventory/reserve", "/internal/payment/authorize",
        "/internal/fulfilment/dispatch", "/v2/orders/{id}/status",
    ]
    apigee, apim = [], []
    cur = win_start
    while cur < win_end:
        for idx, ep in enumerate(nine_endpoints):
            gw = apigee if ep.startswith("/v2") else apim
            if cur < t("22:12:00"):
                gw.append({"minute": iso_utc(cur), **gw_agg(ep, 200, rng.randint(40, 160),
                                                              rng.randint(40, 120), [])})
            else:
                gw.append({"minute": iso_utc(cur), **gw_agg(ep, 503, rng.randint(30, 140),
                                                              rng.randint(4000, 9000), [cid])})
        cur += minutes(1)

    mft = normal_mft_baseline(win_start, win_end)

    sn = []
    priorities = [1, 1, 2, 2, 1, 2]
    rules = ["oracle-pool-saturation", "slow-query-order-intake", "slow-query-payment-adapter",
              "slow-query-fulfilment-dispatch", "gateway-5xx-spike", "kafka-lag-critical"]
    base = t("22:14:00")
    for i, (p, r) in enumerate(zip(priorities, rules)):
        sn.append(sn_ticket(
            f"INC00985{20 + i}", base + seconds(i * 5),
            f"Order flow degraded -- raised by {r}",
            f"Auto-raised by rule '{r}'. Multiple services degraded simultaneously "
            f"following Oracle OMS connection pool saturation.",
            p, "Infra & DBA" if "oracle" in r or "query" in r else "Order Platform",
            "In Progress",
            [f"Auto-correlated: Oracle OMS pool saturation at 22:08 precedes this alert by "
             f"{6 + i} min.", "Possible duplicate of other P1/P2 tickets opened same minute."],
            "rule-engine",
        ))

    # index change 4 days prior (real cause) + routine chaff
    cr = [
        change_record("CHG0044108", "standard", t("22:00:00") - timedelta(days=4),
                       "oracle-oms",
                       "Rebuilt index IDX_ORD_STATUS on ORDERS table to address an "
                       "unrelated slow dashboard query",
                       "dba-team-oracle",
                       "approved",
                       "drop and recreate previous index definition",
                       extra={"unremarkable_at_the_time": True}),
    ]
    cr += routine_chaff_changes(win_start, win_end, exclude_components={"oracle-oms"}, count=5)

    late = elk_doc(t("22:31:00"), "oracle-oms", "WARN", 2,
                    "late signal: query plan for fin-monthend-extract's primary SELECT "
                    "now uses a full index scan on IDX_ORD_STATUS (cost 41,200) vs a "
                    "range scan pre-2026-09-14 (cost 1,800) -- explains why this run held "
                    "connections 68% longer than the 14-month average",
                    correlation_id=cid,
                    extra={"query_plan.cost_before": 1800, "query_plan.cost_after": 41200,
                           "index_change.date": "2026-09-14"})

    elk.sort(key=lambda d: d["@timestamp"])
    kafka.sort(key=lambda r: r["timestamp"])
    apim.sort(key=lambda r: r["minute"])
    apigee.sort(key=lambda r: r["minute"])
    return {
        "elk": elk, "kafka": kafka, "apigee": apigee, "apim": apim,
        "mft": mft, "servicenow": sn, "change_records": cr, "late": late,
    }


# --------------------------------------------------------------------------
# Shared baseline helpers used across scenarios
# --------------------------------------------------------------------------

def normal_mft_baseline(win_start, win_end):
    rows = []
    hh = win_start.hour
    cursor = win_start.replace(minute=0, second=0, microsecond=0)
    idx = 0
    while cursor < win_end:
        start_u = cursor
        end_u = start_u + seconds(rng.randint(35, 70))
        rows_n = rng.randint(126000, 130000)
        rows.append(mft_row(
            f"MFT-WMS-BL-{idx:04d}", f"stock_position_{cursor.strftime('%H%M')}.csv",
            "OMS-EXPORT-01", "WMS-INBOUND", start_u, end_u, "SUCCESS",
            rng.randint(6_600_000, 7_000_000), rows_n, rows_n,
        ))
        idx += 1
        cursor += minutes(60)
    return rows


def normal_apim_baseline(win_start, win_end, endpoint):
    out = []
    cur = win_start
    while cur < win_end:
        out.append({"minute": iso_utc(cur), **gw_agg(
            endpoint, 200, rng.randint(120, 220), rng.randint(30, 70), [])})
        cur += minutes(1)
    return out


def normal_apigee_baseline(win_start, win_end, endpoint):
    out = []
    cur = win_start
    while cur < win_end:
        out.append({"minute": iso_utc(cur), **gw_agg(
            endpoint, 200, rng.randint(200, 380), rng.randint(70, 140), [])})
        cur += minutes(1)
    return out


def normal_kafka_baseline(win_start, win_end, cg, topic, start_offset):
    out = []
    cur = win_start
    off = start_offset
    while cur < win_end:
        off += rng.randint(80, 180)
        out.append(kafka_row(cur, cg, topic, 0, off, off + rng.randint(0, 25)))
        cur += seconds(15)
    return out


CHAFF_COMPONENTS = [
    ("payment-adapter", "bumped connection timeout from 3s to 5s"),
    ("fulfilment-dispatch", "scaled replica count 3 -> 4 for peak-hour headroom"),
    ("order-intake", "rotated internal service TLS certificate"),
    ("apigee-edge", "adjusted rate limit on /v2/catalog from 500 to 800 rpm"),
    ("redis-session-cache", "applied routine maintenance patch"),
    ("fulfilment-dispatch", "updated 3PL carrier lookup table"),
    ("order-orchestrator", "bumped log level from WARN to INFO for debugging"),
    ("pricing-svc", "refreshed promo rules cache TTL from 300s to 600s"),
]


def routine_chaff_changes(win_start, win_end, exclude_components=None, count=6):
    exclude_components = exclude_components or set()
    candidates = [c for c in CHAFF_COMPONENTS if c[0] not in exclude_components]
    rng.shuffle(candidates)
    out = []
    span = (win_end - win_start).total_seconds()
    for i in range(min(count, len(candidates))):
        comp, desc = candidates[i]
        when = win_start + timedelta(seconds=rng.uniform(0, span))
        out.append(change_record(
            f"CHG00441{50 + i:02d}", "standard", when, comp, desc,
            f"{comp}-team-eng", "approved",
            "redeploy previous revision via pipeline rollback",
        ))
    return out


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------

GENERATORS = {"s1": gen_s1, "s2": gen_s2, "s3": gen_s3, "s4": gen_s4, "s5": gen_s5}


def write_ndjson(path, docs):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False))
            f.write("\n")


def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for scn in SCENARIOS:
        out = GENERATORS[scn["id"]](scn)
        out_dir = os.path.join(DATA_DIR, scn["slug"])
        os.makedirs(out_dir, exist_ok=True)

        write_ndjson(os.path.join(out_dir, "elk-logs.ndjson"), out["elk"])
        write_csv(os.path.join(out_dir, "kafka-lag.csv"), out["kafka"],
                  ["timestamp", "consumer_group", "topic", "partition",
                   "current_offset", "log_end_offset", "lag"])
        write_json(os.path.join(out_dir, "apigee-errors.json"), out["apigee"])
        write_json(os.path.join(out_dir, "apim-errors.json"), out["apim"])
        write_csv(os.path.join(out_dir, "mft-transfers.csv"), out["mft"],
                  ["transfer_id", "filename", "source", "target", "start_time",
                   "end_time", "status", "bytes", "declared_rows", "actual_rows"])
        write_json(os.path.join(out_dir, "servicenow-incidents.json"), out["servicenow"])
        write_json(os.path.join(out_dir, "change-records.json"), out["change_records"])
        write_ndjson(os.path.join(out_dir, "late-evidence.ndjson"), [out["late"]])

        print(f"[{scn['slug']}] elk={len(out['elk'])} kafka={len(out['kafka'])} "
              f"apigee_min={len(out['apigee'])} apim_min={len(out['apim'])} "
              f"mft={len(out['mft'])} servicenow={len(out['servicenow'])} "
              f"change_records={len(out['change_records'])}")


if __name__ == "__main__":
    main()
