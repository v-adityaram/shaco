"""
generator/scenarios.py -- declarative facts for the five HIP incident
scenarios (plan v2, section 3). All times are UTC on 2026-09-18.

This module holds ONLY facts: identity, window, the anchor signal table,
the planted contradiction, expected hypotheses, alert scope, and the anchor
specs that scripts/find_anchors.py resolves against normalised events.
Generation logic lives in generate.py.

`signals`  : the backbone table from plan section 3 (documentation + tests).
`scope`    : projects / components / processing groups that belong to the
             incident. Used by the generator (background noise never touches
             them) and by build_alert_feed.py (rulesFired relevance).
`anchors`  : declarative selectors resolved by find_anchors.py.
             Each: key, role, label, kind ('rule_hit'|'context'), and a
             `match` of {source, re (regex on description), ts_from, ts_to,
             component, pick ('first'|'last'|'all')}.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import naming  # noqa: E402

D = naming.DATE

SCENARIOS = [
    # ------------------------------------------------------------------ S1
    {
        "id": "s1",
        "slug": "s1-large-mapping-heap",
        "title": "Large-mapping half-flow exhausts its processing group",
        "incident_number": "INC10790101",
        "duplicate_incidents": ["INC10790311", "INC10790312", "INC10790313"],
        "fault_one_line": "ASN mapping half-flow payloads 3x normal exhaust heap in processing group opsfin-01-neo-odes-large",
        "user_headline": "No ASN integrated in S4 - trucks waiting",
        "focal_exchange": "GLBL_SAPS4HANA_SAPS4HANA_ASN_INT",
        "focal_component": "opsfin-01-neo-odes-large",
        "start": "04:10:00", "end": "08:30:00",
        "feed_end": "08:12:00",
        "bg_period_sec": 21,
        "hourly_report_minute": 30,
        "fault": (
            "After a large STO batch, the ASN mapping half-flow "
            "GLBL_SAPS4HANA_SAPS4HANA_ASN_INT produces payloads roughly 3x normal size. "
            "Heap in the opsfin-01-neo-odes-large processing group climbs steadily, GC "
            "thrashes, pods are OOMKilled and restart, throughput collapses and the topic backs up."
        ),
        "signals": [
            {"time": "05:10:00", "source": "Splunk", "text": "heap > 70% on hip-esb-odes-large pods - P4, nobody looks (first symptom)"},
            {"time": "05:55:00", "source": "Kafka", "text": "lag on ...process-int-opsfin-01-neo-odes-large.v1 starts to climb"},
            {"time": "06:20:00", "source": "Sonar", "text": "ASN_INT exchanges INPROGRESS at half-flow 2/4, durations 1 -> 9 min"},
            {"time": "06:35:00", "source": "Splunk", "text": "OOMKilled, pod restart 1; restart 2 at 06:52"},
            {"time": "07:05:00", "source": "HIPMON", "text": "Consumer Lag alert, P3"},
            {"time": "07:30:00", "source": "Sonar", "text": "GLBL_MSTR_HLTH_CHK reports 45,000+ InProgress"},
            {"time": "08:10:00", "source": "ServiceNow", "text": "user incident + three HIPMON auto duplicates"},
        ],
        "contradiction": {
            "fact": "ASN message inflow is LOWER than last Thursday and lag on every other processing group is zero.",
            "argues_against": "broker trouble / load-driven backlog",
            "argues_for": "payload size, not volume",
        },
        "hypotheses": {
            "top1": "Heap exhaustion from oversized ASN payloads in the large processing group",
            "top2": "Kafka broker / cluster degradation (contradicted by zero lag on all other groups)",
        },
        "scope": {
            "projects": ["SAPS4HANA_ASN", "SONAR-OPS"],
            "components": ["opsfin-01-neo-odes-large", "CONFLUENT_EMEA"],
            "incident_codes": ["PRC003", "LAG01"],
        },
        "cheapest_check": "heap and average payload size for opsfin-01-neo-odes-large (kubectl top / Sonar payload-size series)",
        "late": {
            "ts": "05:04:10", "source": "SONAR", "component": "SAPS4HANA_ASN", "severity": 3,
            "message": ("Late Sonar batch (ingest delayed 3 h): exchange 20260918050411 STO batch 3,850 STOs "
                        "delivered in one ASN message, payload 3.1x the 24 h average line-item count; "
                        "half-flow GLBL_SAPS4HANA_SAPS4HANA_ASN_INT_02_ESB mapping allocated 1.4 GB"),
        },
    },
    # ------------------------------------------------------------------ S2
    {
        "id": "s2",
        "watch": {"silence": ["EMEA_SAPCE_PI7_IDOC_DELVRY07_TO_MANH"], "heartbeat": ["AN_COMMON_PI7IDOCListner"]},
        "slug": "s2-pi7-listener-hang",
        "title": "PI7 IDoc listener hangs while its JVM stays up",
        "incident_number": "INC10790202",
        "duplicate_incidents": ["INC10790321", "INC10790322", "INC10790323"],
        "fault_one_line": "AN_COMMON_PI7IDOCListner stops consuming IDocs from SAP PI7 hub CE; nothing enters the platform",
        "user_headline": "CZ warehouse - no deliveries from SAP",
        "focal_exchange": "EMEA_SAPCE_PI7_IDOC_DELVRY07_TO_MANH",
        "focal_component": "AN_COMMON_PI7IDOCListner",
        "start": "12:30:00", "end": "17:20:00",
        "feed_end": "15:52:00",
        "bg_period_sec": 24,
        "hourly_report_minute": 0,
        "fault": (
            "The listener node that receives IDocs from SAP PI7 hub CE stops consuming "
            "while its JVM stays up. No new exchanges are created. Replays have nothing to "
            "replay against."
        ),
        "signals": [
            {"time": "13:29:48", "source": "Sonar", "text": "last IDoc exchange from PI7 hub CE created"},
            {"time": "13:30:12", "source": "Sonar", "text": "last listener heartbeat (every 60 s before)"},
            {"time": "13:35:00", "source": "Sonar", "text": "inbound exchange count from PI7 = 0 (baseline 180 per 5 min)"},
            {"time": "13:45:00", "source": "Kafka", "text": "lag on all processing groups 0; no growth anywhere"},
            {"time": "14:10:00", "source": "HIPMON", "text": "NO DATA FROM SAPCE/Pi7 IN LAST 60 minutes"},
            {"time": "14:20:00", "source": "ServiceNow", "text": "user incident: CZ warehouse - no deliveries; YODI reprocess no effect"},
            {"time": "15:49:00", "source": "ServiceNow", "text": "raised to Critical; 17:17 escalated to Major"},
        ],
        "contradiction": {
            "fact": "The listener passes its health check; JVM CPU and heap are normal and flat.",
            "argues_against": "the node is down",
            "argues_for": "it is up but not consuming",
        },
        "hypotheses": {
            "top1": "Listener node hung (heartbeat stopped, zero inbound, health check misleadingly green)",
            "top2": "Processing-group saturation as in S1 - ruled out by zero lag, flat heap, no INPROGRESS",
        },
        "scope": {
            "projects": ["SAPCE_PI7_INBOUND"],
            "components": ["AN_COMMON_PI7IDOCListner"],
            "incident_codes": ["NODATA01", "SLA01"],
        },
        "cheapest_check": "count of exchanges created in the last 15 minutes from PI7 hub CE (one Sonar query)",
        "late": {
            "ts": "13:30:20", "source": "SONAR", "component": "AN_COMMON_PI7IDOCListner", "severity": 3,
            "message": ("Late SAP-side batch (ingest delayed): PI7 hub CE outbound queue holds 214 IDocs, "
                        "delivery attempts to HIP listener endpoint since 13:30:20 time out with no ACK; "
                        "listener thread dump shows all consumer threads BLOCKED on socket read"),
        },
    },
    # ------------------------------------------------------------------ S3
    {
        "id": "s3",
        "watch": {"success": [{"exchange": "EURO_COMMON_IDOC_SAPNE_YHIPDELVRY07", "since": "09:52:00", "compare_prefix": "EURO_COMMON_IDOC_"}]},
        "slug": "s3-vendor-release",
        "title": "Vendor platform push breaks IDoc outbound to SAP",
        "incident_number": "INC10790303",
        "duplicate_incidents": ["INC10790331", "INC10790332", "INC10790333", "INC10790334"],
        "fault_one_line": "Workato platform release breaks ConfigForDocSending on every IDoc-out recipe; no HIP change record",
        "user_headline": "Shipment completed in Manhattan but not integrated to SAP",
        "focal_exchange": "EURO_COMMON_IDOC_SAPNE_YHIPDELVRY07",
        "focal_component": "WORKATO_PLATFORM",
        "start": "08:40:00", "end": "11:00:00",
        "feed_end": "10:42:00",
        "bg_period_sec": 8,
        "hourly_report_minute": 0,
        "fault": (
            "A Workato platform release changes an HTTP/RFC connector default. Every recipe "
            "that calls ConfigForDocSending fails. HIP has no change record - the release was the vendor's."
        ),
        "signals": [
            {"time": "09:40:00", "source": "Change", "text": "Vendor release notice (Workato platform push), informational, no HIP change"},
            {"time": "09:52:00", "source": "Workato", "text": "Recipe function execution error: Recipe function call failed"},
            {"time": "09:55:00", "source": "HIPMON", "text": "Failed to fetch ConfigForDocSending on SAPCE YLCD01, then SAPUK, SAPIT, SAPNE"},
            {"time": "10:05:00", "source": "Sonar", "text": "30+ IDoc-out exchanges FAILED at half-flow 3/4"},
            {"time": "10:25:00", "source": "ServiceNow", "text": "user incident: shipment completed in Manhattan but not integrated to SAP"},
            {"time": "10:40:00", "source": "ServiceNow", "text": "second user incident, different warehouse"},
        ],
        "contradiction": {
            "fact": "A minority of YHIPDELVRY07 IDocs to SAPNE still succeed and the SAP RFC gateway health check is green.",
            "argues_against": "a clean vendor-side break (looks like a flaky SAP endpoint)",
            "argues_for": "failure is on the config fetch, not the send",
        },
        "hypotheses": {
            "top1": "Vendor release regression (12 min before first failure, error on the Workato side of the RFC call)",
            "top2": "SAP RFC gateway degradation (contradicted by green gateway health and config-fetch failure)",
        },
        "scope": {
            "projects": [f"EURO_COMMON_IDOC_SAP{h}_{t}" for h in naming.HUBS for t in naming.IDOC_TYPES] + ["SONAR-OPS"],
            "components": ["WORKATO_PLATFORM", "SAPCE_RFC_GATEWAY", "SAPNE_RFC_GATEWAY"],
            "incident_codes": ["DEFAULT"],
        },
        "cheapest_check": "change/vendor-notice search for the Workato platform in the 30 min before 09:52; compare against first FAILED IDoc-out exchange",
        "late": {
            "ts": "09:47:30", "source": "Change", "component": "WORKATO_PLATFORM", "severity": 2,
            "message": ("Late vendor ticket update (posted 11:20, effective 09:47): Workato confirms platform release "
                        "2026.09.3 changed the default value of the RFC connector parameter 'config_endpoint' to empty; "
                        "customers calling ConfigForDocSending must set it explicitly. Rollback scheduled."),
        },
    },
    # ------------------------------------------------------------------ S4
    {
        "id": "s4",
        "slug": "s4-stalled-exchange",
        "title": "Silent stalled exchange after the EMEA patching window",
        "incident_number": "INC10790404",
        "duplicate_incidents": ["INC10790341", "INC10790342", "INC10790343"],
        "fault_one_line": "BPM_to_FM_0200.csv delivered by SFG but the ESB half-flow never started; exchange stuck INPROGRESS at 2/4",
        "user_headline": "FRCPD database locked, FKF not generated",
        "focal_exchange": "GLBL_OPSF_ANAPLAN_BPM_to_FM",
        "focal_component": "ANAPLAN_BPM",
        "start": "00:00:00", "end": "08:10:00",
        "feed_end": "08:02:00",
        "bg_period_sec": 26,
        "hourly_report_minute": 0,
        "fault": (
            "During the EMEA patching window the MFT connector session to the ESB drops. The 02:00 file "
            "GLBL_OPSF_ANAPLAN_BPM_to_FM is delivered by SFG with status SUCCESS, but the ESB half-flow never "
            "starts. The exchange sits INPROGRESS at 2/4 and never becomes FAILED, so no rule fires. "
            "Five hours later the downstream database locks."
        ),
        "signals": [
            {"time": "01:30:00", "source": "Change", "text": "EMEA patching window opens - MFT hosts reboot (routine, approved)"},
            {"time": "02:00:00", "source": "MFT", "text": "BPM_to_FM_0200.csv SUCCESS 4.1 MB (usual 6.8 MB); declared 128,400 rows, 77,032 present"},
            {"time": "02:00:07", "source": "Sonar", "text": "exchange starts, half-flow 1 ENTRYINFO, half-flow 2 never appears; INPROGRESS 2/4"},
            {"time": "03:00:00", "source": "Sonar", "text": "hourly critical-exchange report 03:00 -> 07:00 lists exchange under InProgress, not Failed"},
            {"time": "07:57:00", "source": "ServiceNow", "text": "user incident: FRCPD database locked, FKF not generated"},
        ],
        "contradiction": {
            "fact": "SFG status SUCCESS and every hourly Sonar report shows zero failed exchanges.",
            "argues_against": "the file transfer being the problem",
            "argues_for": None,
        },
        "hypotheses": {
            "top1": "Exchange stalled after the connector session dropped in the patching window (2/4, truncated file, no ESB entry event)",
            "top2": "Source export late or empty (contradicted by the export log showing a normal run at 01:58)",
        },
        "scope": {
            "projects": ["ANAPLAN_BPM", "FRCPD", "SONAR-OPS"],
            "components": ["FRHIPGPRMFTSI02", "FRHIPGPRMFTSI01", "SGLORHIPPETLPC1"],
            "incident_codes": ["TEC01", "COM01"],
        },
        "cheapest_check": "Sonar search on exchange.id of the 02:00 BPM_to_FM exchange: events present vs the 4 expected half-flows; compare MFT declared_rows vs actual_rows",
        "late": {
            "ts": "02:00:06", "source": "MFT", "component": "FRHIPGPRMFTSI02", "severity": 2,
            "message": ("Delayed SFG trailer for BPM_to_FM_0200.csv: ESB adapter session reset at 02:00:06 during "
                        "delivery; partial delivery acknowledged at 77,032 of 128,400 rows; delivery marked "
                        "SUCCESS by the SFG business process without row validation"),
        },
    },
    # ------------------------------------------------------------------ S5
    {
        "id": "s5",
        "slug": "s5-transco-cache",
        "title": "Shared dependency failure across unrelated flows (transco-cache)",
        "incident_number": "INC10790505",
        "duplicate_incidents": ["INC10790351", "INC10790352", "INC10790353", "INC10790354", "INC10790355"],
        "fault_one_line": "hip-fwk-transco-cache pod restart; Connection refused errors on 32 half-flows in 4 projects",
        "user_headline": "Multiple sales-order flows failing - Connection refused transco-cache",
        "focal_exchange": "EMEA_SAPIT_SALESORDER",
        "focal_component": "hip-fwk-transco-cache",
        "start": "00:00:00", "end": "01:40:00",
        "feed_end": "01:16:00",
        "bg_period_sec": 7,
        "hourly_report_minute": 0,
        "fault": (
            "The hip-fwk-transco-cache pod restarts (memory limit) during a busy window. For roughly "
            "20 minutes every half-flow that calls transcoding fails, across projects that have nothing in "
            "common but that dependency."
        ),
        "signals": [
            {"time": "00:20:00", "source": "Splunk", "text": "hip-fwk-transco-cache pod restart 1 - informational (first symptom)"},
            {"time": "00:55:03", "source": "Sonar", "text": "Unhandled Internal error ... Connection refused: hip-fwk-transco-cache...:8080 on EMEA_SAPIT_SALESORDER_01_ESB_V2"},
            {"time": "00:56:00", "source": "HIPMON", "text": "[AUTO] alerts on 30+ half-flows across SAPITCOMMON, KEPLER_NEXTGEN, PROCESSOUT, AMAZONCOMMON"},
            {"time": "01:05:00", "source": "Kafka", "text": "lag on four processing groups simultaneously"},
            {"time": "01:10:00", "source": "Apigee", "text": "5xx across nine endpoints"},
            {"time": "01:15:00", "source": "ServiceNow", "text": "six auto incidents from six different rules"},
        ],
        "contradiction": {
            "fact": "By the time anyone looks the cache pod is Running and Ready and every replay succeeds.",
            "argues_against": "the cache being the cause (looks like intermittent networking)",
            "argues_for": None,
        },
        "hypotheses": {
            "top1": "transco-cache restart / unavailability window (identical error string, restart record 35 min earlier)",
            "top2": "AKS network / DNS blip (contradicted: other services in the namespace unaffected)",
        },
        "scope": {
            "projects": ["SAPITCOMMON", "KEPLER_NEXTGEN", "PROCESSOUT", "AMAZONCOMMON", "SONAR-OPS"],
            "components": ["hip-fwk-transco-cache", "APIGEE_EDGE", "sapit-01-default", "kepler-01-default",
                           "procout-01-default", "amazon-01-default"],
            "incident_codes": ["IVK003", "TEC01", "GEN01"],
        },
        "cheapest_check": "group failed exchanges by identical event.reason; kubectl get pod / describe for hip-fwk-transco-cache (restart count, last state, Ready transition)",
        "late": {
            "ts": "00:19:41", "source": "SPLUNK", "component": "hip-fwk-transco-cache", "severity": 3,
            "message": ("Late Kubernetes event batch: container hip-fwk-transco-cache terminated OOMKilled "
                        "(memory limit 2Gi, exit code 137) at 00:19:41; readiness probe :8080 failing from 00:52:07 "
                        "while the cache rehydrated; Ready again at 01:13:41. No other pod in namespace hip-cloud-esb "
                        "reported network errors."),
        },
    },
]


def get_scenario(slug_or_id):
    for s in SCENARIOS:
        if s["slug"] == slug_or_id or s["id"] == slug_or_id:
            return s
    raise KeyError(slug_or_id)
