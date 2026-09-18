"""
generator/scenarios.py -- structured, declarative data for the five
Meridian Retail incident scenarios.

This module holds ONLY the facts of each scenario: identity, fault
description, the anchor signal sequence (the events generate.py MUST place
at the right relative offsets in the raw files), the planted contradiction,
and the expected hypotheses for later validation. It contains no generation
logic -- that lives in generate.py.

Each signal in `signals` is a dict:
    {
        "time": "HH:MM[:SS]",   # UTC, on CORRELATION_DATE (2026-09-18)
        "source": "ELK" | "Kafka" | "Apigee" | "APIM" | "ServiceNow"
                  | "DevOps" | "PartnerFeed" | "MFT",
        "text": "human-readable signal description (used as the anchor
                 message / basis for the generated record)",
    }
These are the "backbone" events; generate.py surrounds them with realistic
baseline noise and expands each into the correct raw-file record shape.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import naming  # noqa: E402

SCENARIOS = [
    {
        "id": "s1",
        "slug": "s1-memory-leak",
        "title": "Memory leak in inventory-reservation",
        "correlation_id": f"mrd-{naming.CORRELATION_DATE}-9a41c7e2",
        "fault": (
            "A slow heap leak in the inventory-reservation cache builds over "
            "roughly 90 minutes, causing GC thrash, then an OOMKill and pod "
            "restart, repeating in a crash loop."
        ),
        "primary_component": "inventory-reservation",
        "signals": [
            {"time": "08:40:00", "source": "ELK",
             "text": "ELK-R-0188 heap utilisation > 70% on inv-resv-svc -- P4, buried, first symptom"},
            {"time": "09:25:00", "source": "ELK",
             "text": "GC pause p99 climbing on inv-resv-svc, 40ms -> 900ms"},
            {"time": "09:52:00", "source": "ELK",
             "text": "ELK-R-0217 OOMKilled, pod inv-resv-svc-7d4f restart 1"},
            {"time": "09:53:00", "source": "Kafka",
             "text": "inventory-reservation-cg lag on inventory.reserve.req climbs past 12,000"},
            {"time": "09:58:00", "source": "ELK",
             "text": "pod inv-resv-svc-7d4f restart 2, then restart 3 -- crash loop"},
            {"time": "10:02:00", "source": "APIM",
             "text": "504 gateway timeouts on /internal/inventory/reserve"},
            {"time": "10:04:00", "source": "Apigee",
             "text": "502 on /v2/orders -- customer-visible"},
            {"time": "10:06:00", "source": "ServiceNow",
             "text": "INC0098451 auto-raised P1: order flow degraded"},
        ],
        "contradiction": {
            "fact": (
                "inventory-reservation handled a 40% higher peak order rate "
                "on 2026-09-09 (last Tuesday, 1,400 orders/min vs today's "
                "1,000 orders/min peak) with heap utilisation staying flat "
                "under 55% and no incident."
            ),
            "argues_against": "load-driven / volume-driven memory pressure",
            "argues_for": "time-based leak, not a volume-triggered one",
        },
        "hypotheses": {
            "top1": "Memory leak in inventory-reservation reservation cache "
                    "(linear pre-incident heap trend, no deploy in window)",
            "top2": "Upstream retry storm inflating batch sizes "
                    "(contradicted by flat order.enriched producer rate)",
        },
    },
    {
        "id": "s2",
        "slug": "s2-poison-message",
        "title": "Poison message on order.enriched",
        "correlation_id": f"mrd-{naming.CORRELATION_DATE}-3f0b6d15",
        "fault": (
            "One malformed partner B2B payload (a negative line quantity) "
            "fails deserialisation. The order-orchestrator consumer crash-"
            "loops retrying the same Kafka offset."
        ),
        "primary_component": "order-orchestrator",
        "signals": [
            {"time": "11:14:00", "source": "PartnerFeed",
             "text": "Partner B2B batch PB-4471 accepted, 1 of 380 lines malformed (negative line quantity)"},
            {"time": "11:16:00", "source": "ELK",
             "text": "Deserialisation exception in order-orchestrator, stack trace"},
            {"time": "11:16:05", "source": "ELK",
             "text": "pod ord-orch-svc restart (interval 1 of the crash loop)"},
            {"time": "11:19:05", "source": "ELK",
             "text": "pod ord-orch-svc restart, exactly 3 min after previous"},
            {"time": "11:22:05", "source": "ELK",
             "text": "pod ord-orch-svc restart, exactly 3 min after previous"},
            {"time": "11:25:05", "source": "ELK",
             "text": "pod ord-orch-svc restart, exactly 3 min after previous"},
            {"time": "11:20:00", "source": "Kafka",
             "text": "consumer offset on order.enriched STATIC at 4,481,209"},
            {"time": "11:21:00", "source": "Kafka",
             "text": "lag on order.enriched climbing, DLQ depth zero (no DLQ configured on this topic)"},
            {"time": "11:30:00", "source": "Apigee",
             "text": "502 on /v2/orders"},
            {"time": "11:33:00", "source": "ServiceNow",
             "text": "INC0098462 P1 auto-raised (order flow degraded)"},
            {"time": "11:33:02", "source": "ServiceNow",
             "text": "INC0098463 auto-raised separately by Kafka lag rule (duplicate)"},
            {"time": "11:33:05", "source": "ServiceNow",
             "text": "INC0098464 auto-raised separately by gateway 5xx rule (duplicate)"},
        ],
        "contradiction": {
            "fact": (
                "heap utilisation and CPU on order-orchestrator stay flat "
                "and normal (heap 42-48%, CPU 25-32%) throughout the entire "
                "incident window, including through all four restarts."
            ),
            "argues_against": "resource exhaustion / memory pressure",
            "argues_for": "a deterministic poisoned-offset failure, not resource-driven",
        },
        "hypotheses": {
            "top1": "Poison message on order.enriched blocking the consumer "
                    "(static offset + metronomic 3-minute restarts + deserialisation trace)",
            "top2": "Memory pressure on order-orchestrator (ruled out: heap is flat)",
        },
        "note": (
            "Symptom shape (lag climbing, restarts, 502/504) is deliberately "
            "similar to S1 from the Kafka/gateway side; the differentiator "
            "-- flat heap, static offset, regular 3-min restart interval -- "
            "is present in the data but never narrated."
        ),
    },
    {
        "id": "s3",
        "slug": "s3-config-change",
        "title": "Config change breaks internal auth",
        "correlation_id": f"mrd-{naming.CORRELATION_DATE}-b2e8f401",
        "fault": (
            "An Azure APIM policy deployed at 09:12 (CHG0044219, revision "
            "47, via release pipeline, no approval record) tightens JWT "
            "audience validation. Only pricing-svc still sends the old "
            "audience claim."
        ),
        "primary_component": "pricing-svc",
        "signals": [
            {"time": "09:12:00", "source": "DevOps",
             "text": "CHG0044219 deployed -- APIM policy revision 47, release pipeline, no approval record"},
            {"time": "09:14:00", "source": "APIM",
             "text": "401s on /internal/pricing/quote, climbing"},
            {"time": "09:15:00", "source": "ELK",
             "text": "order-orchestrator timeout waiting on pricing-svc, retry exhaustion"},
            {"time": "09:18:00", "source": "Kafka",
             "text": "order.enriched producer rate collapses near zero"},
            {"time": "09:21:00", "source": "ELK",
             "text": "order completion rate down 80%"},
            {"time": "09:24:00", "source": "Apigee",
             "text": "504 on /v2/orders/{id}/confirm"},
            {"time": "09:27:00", "source": "ServiceNow",
             "text": "INC0098470 auto-raised P1"},
        ],
        "contradiction": {
            "fact": (
                "web and mobile checkout continue completing orders "
                "successfully for cached-price items throughout the "
                "incident (pricing cache hits bypass the APIM call)."
            ),
            "argues_against": "a clean, total config break",
            "argues_for": None,
            "note": "makes the failure look partial/intermittent, sending "
                     "humans hunting for a flaky dependency instead of the "
                     "09:12 change.",
        },
        "hypotheses": {
            "top1": "APIM policy change CHG0044219 tightened JWT audience "
                    "validation, breaking pricing-svc auth (timestamp "
                    "proximity + component match, revision deployed with no "
                    "approval record)",
            "top2": "Flaky pricing-svc dependency (contradicted: failure is "
                    "isolated to the pricing audience claim, not intermittent "
                    "at the network level)",
        },
        "note": (
            "No ELK rule references CHG0044219 directly -- the correlation "
            "exists only via timestamp proximity and component match, on "
            "purpose."
        ),
    },
    {
        "id": "s4",
        "slug": "s4-mft-truncation",
        "title": "Silent MFT truncation",
        "correlation_id": f"mrd-{naming.CORRELATION_DATE}-c74a9d33",
        "fault": (
            "The 06:00 hourly WMS stock file transfers 'successfully' but "
            "is truncated at ~60% (the source export job was killed "
            "mid-write). Inventory positions go stale for three hours with "
            "no error anywhere."
        ),
        "primary_component": "inventory-reservation",
        "signals": [
            {"time": "06:00:00", "source": "MFT",
             "text": "stock_position_0600.csv transferred, status SUCCESS, 4.1 MB (usual ~6.8 MB)"},
            {"time": "06:00:05", "source": "MFT",
             "text": "trailer declared_rows=128400, actual_rows=77032 -- never validated, status stays SUCCESS"},
            {"time": "06:05:00", "source": "ELK",
             "text": "ELK-R-MFT-004 file transfer monitor: stock_position_0600.csv OK (checks status flag only)"},
            {"time": "09:12:00", "source": "ELK",
             "text": "first oversell -- reservation confirmed against stock that does not exist"},
            {"time": "09:40:00", "source": "ELK",
             "text": "oversell rate climbing, 14 orders affected"},
            {"time": "10:15:00", "source": "ServiceNow",
             "text": "INC0098480 raised MANUALLY by warehouse ops, not by a rule"},
        ],
        "contradiction": {
            "fact": (
                "the MFT job reported status SUCCESS and the ELK file-"
                "transfer monitor rule (ELK-R-MFT-004) also passed at "
                "06:05, because both only check the status flag, never "
                "declared_rows vs actual_rows."
            ),
            "argues_against": "the file transfer being the problem",
            "argues_for": None,
        },
        "hypotheses": {
            "top1": "Silent truncation of the 06:00 WMS stock file "
                    "(declared_rows=128400 != actual_rows=77032 in the "
                    "transfer trailer, despite status=SUCCESS)",
            "top2": "Demand spike causing legitimate oversell (contradicted: "
                    "oversold SKUs match exactly the tail of the truncated "
                    "file, not a volume pattern)",
        },
        "note": (
            "Tests reasoning backwards from a 09:12 symptom to a silent, "
            "hours-earlier event with no alert. The declared_rows/"
            "actual_rows mismatch must be real, checkable data in "
            "mft-transfers.csv, not a narrated fact."
        ),
    },
    {
        "id": "s5",
        "slug": "s5-oracle-saturation",
        "title": "Downstream saturation from an unrelated job",
        "correlation_id": f"mrd-{naming.CORRELATION_DATE}-e15f2a88",
        "fault": (
            "The routine month-end reporting job fin-monthend-extract opens "
            "180 connections against Oracle OMS, exhausting the pool. Every "
            "service touching OMS degrades simultaneously. The real cause: "
            "a recent index change made the job's queries slower, so it "
            "holds connections open longer than in any prior run."
        ),
        "primary_component": "oracle-oms",
        "signals": [
            {"time": "22:00:00", "source": "DevOps",
             "text": "scheduled job fin-monthend-extract starts (routine, runs every month, 14-month history with no incident)"},
            {"time": "22:08:00", "source": "ELK",
             "text": "Oracle OMS connection pool at 100%, wait queue growing"},
            {"time": "22:09:00", "source": "ELK",
             "text": "slow-query alerts across order-intake, payment-adapter, fulfilment-dispatch -- 30+ distinct rules firing"},
            {"time": "22:11:00", "source": "Kafka",
             "text": "lag on four topics simultaneously"},
            {"time": "22:12:00", "source": "Apigee",
             "text": "5xx across nine endpoints (Apigee + APIM combined)"},
            {"time": "22:14:00", "source": "ServiceNow",
             "text": "six P1/P2 incidents raised by six different rules"},
        ],
        "contradiction": {
            "fact": (
                "fin-monthend-extract has run on an identical monthly "
                "schedule for 14 months with no incident (historical run "
                "log: avg duration 42 min, avg peak connections 118, zero "
                "incidents) -- tonight's run took 71 min and peaked at 180 "
                "connections."
            ),
            "argues_against": "'the job' itself as the root cause",
            "argues_for": "the environment changed underneath an unchanged job "
                          "-- points at the IDX_ORD_STATUS index rebuild "
                          "4 days prior",
        },
        "hypotheses": {
            "top1": "Oracle OMS connection pool exhaustion caused by "
                    "fin-monthend-extract running abnormally long after the "
                    "IDX_ORD_STATUS index rebuild (2026-09-14) degraded its "
                    "query plan, holding connections open far longer than "
                    "its 14-month baseline",
            "top2": "fin-monthend-extract itself is simply too heavy "
                    "(contradicted by 14 months of identical, incident-free "
                    "runs on the same schedule)",
        },
        "note": (
            "Hardest noise-vs-cause separation: 30+ rules fire correctly, "
            "all describing symptoms on services that never touch the real "
            "cause (Oracle OMS via an index rebuild nobody flagged as "
            "risky)."
        ),
    },
]


def get_scenario(slug_or_id):
    for s in SCENARIOS:
        if s["slug"] == slug_or_id or s["id"] == slug_or_id:
            return s
    raise KeyError(slug_or_id)
