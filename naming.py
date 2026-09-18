"""
naming.py -- single source of truth for service naming across the Meridian
Retail synthetic estate ("Incident Response AI" POC).

Both generator/generate.py and normaliser/normalise.py import this module
(repo root is added to sys.path by each script) so that the CMDB name <->
Kubernetes pod/deployment name <-> ELK index alias mapping can never drift
out of sync between the two halves of the pipeline.

The realistic wrinkle this encodes: the CMDB name (used in ServiceNow,
change records, and as the normalised `component`) differs from both the
Kubernetes deployment/pod prefix (used in `kubernetes.pod.name`) and the
ELK index alias (used in the raw `_index` field of ELK documents).
"""

CORRELATION_DATE = "20260918"  # yyyymmdd shared by every scenario's correlation id

# Six core services + two edge gateways.
#   k8s_prefix -- Kubernetes deployment/pod name prefix (pods get a random
#                 4-hex-char suffix appended, e.g. "inv-resv-svc-7d4f")
#   elk_alias  -- ELK index alias stem (raw ELK docs live under
#                 "<elk_alias>-*", e.g. "app-invresv-*")
SERVICES = {
    "order-intake": {
        "k8s_prefix": "ord-intake-svc",
        "elk_alias": "app-ordintake",
        "team": "Order Platform",
    },
    "order-orchestrator": {
        "k8s_prefix": "ord-orch-svc",
        "elk_alias": "app-ordorch",
        "team": "Order Platform",
    },
    "inventory-reservation": {
        "k8s_prefix": "inv-resv-svc",
        "elk_alias": "app-invresv",
        "team": "Inventory & Fulfilment",
    },
    "pricing-svc": {
        "k8s_prefix": "pricing-svc",
        "elk_alias": "app-pricing",
        "team": "Order Platform",
    },
    "payment-adapter": {
        "k8s_prefix": "pay-adapter-svc",
        "elk_alias": "app-payadapt",
        "team": "Inventory & Fulfilment",
    },
    "fulfilment-dispatch": {
        "k8s_prefix": "fulfil-disp-svc",
        "elk_alias": "app-fulfildisp",
        "team": "Inventory & Fulfilment",
    },
    "apigee-edge": {
        "k8s_prefix": "apigee-gw",
        "elk_alias": "app-apigee",
        "team": "Channel Engineering",
    },
    "azure-apim": {
        "k8s_prefix": "apim-gw",
        "elk_alias": "app-apim",
        "team": "Integration",
    },
}

CORE_SERVICE_NAMES = [
    "order-intake",
    "order-orchestrator",
    "inventory-reservation",
    "pricing-svc",
    "payment-adapter",
    "fulfilment-dispatch",
]

GATEWAY_NAMES = ["apigee-edge", "azure-apim"]


def pod_name(cmdb_service: str, hash_suffix: str) -> str:
    return f"{SERVICES[cmdb_service]['k8s_prefix']}-{hash_suffix}"


def elk_index(cmdb_service: str) -> str:
    return f"{SERVICES[cmdb_service]['elk_alias']}-2026.09.18"


def alias_map() -> dict:
    """
    Return {prefix_or_alias: cmdb_name} covering every naming variant a raw
    record might carry: the k8s pod/deployment prefix, the ELK index alias
    stem, and the CMDB name itself (identity, for records that already use
    it, e.g. ServiceNow/change records/Kafka/MFT/Apigee/APIM aggregates).
    Longest-prefix-wins matching is expected of consumers, since pod names
    append a random hash suffix (e.g. "inv-resv-svc-7d4f").
    """
    m = {}
    for cmdb, info in SERVICES.items():
        m[info["k8s_prefix"]] = cmdb
        m[info["elk_alias"]] = cmdb
        m[cmdb] = cmdb
    return m
