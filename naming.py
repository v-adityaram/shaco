"""
naming.py -- single source of truth for service naming across the HIP
(Hybrid Integration Platform) synthetic estate ("Incident Response AI" POC).

Both generator/generate.py and normaliser/normalise.py import this module
(the repo root is added to sys.path by each script) so the naming can never
drift between the two halves of the pipeline.

The "three names for one thing" wrinkle (plan section 2, Conventions):

  1. the ServiceNow CI / project name          e.g. KEPLER_NEXTGEN
  2. the half-flow name (Sonar / HIPMON)       e.g. EMEA_KEPLERNG_SALESORDER_OUT_02_ESB
  3. the Kubernetes deployment / ELK alias     e.g. hip-kepler-ng-out / app-kepler-ng

The normaliser resolves all three back to the CMDB (project) name, which is
what appears as `component` in normalised events. Nothing here is real
customer data: every id, host-style name and business object is invented.
"""

CORRELATION_DATE = "20260918"  # yyyymmdd used by 24-digit exchange ids
DATE = "2026-09-18"
ZONE = "EMEA"
ENVIRONMENT = "PRD"

TEAMS = ["ESB", "MFT", "Azure/Platform", "Workato", "Kafka", "Apigee", "ETL"]

# --------------------------------------------------------------------------
# Components (CMDB name -> naming variants + owning team)
# --------------------------------------------------------------------------
# kind: project | processing_group | framework | listener | platform | host
COMPONENTS = {}


def _comp(cmdb, k8s, elk, team, kind="project"):
    COMPONENTS[cmdb] = {"k8s_prefix": k8s, "elk_alias": elk, "team": team, "kind": kind}


# --- ESB projects (TIBCO BW half-flows on Kubernetes, ns hip-cloud-esb) ----
_comp("SAPS4HANA_ASN", "hip-s4-asn-int", "app-s4-asn", "ESB")
_comp("SAPITCOMMON", "hip-sapit-common", "app-sapit", "ESB")
_comp("KEPLER_NEXTGEN", "hip-kepler-ng-out", "app-kepler-ng", "ESB")
_comp("PROCESSOUT", "hip-processout", "app-processout", "ESB")
_comp("AMAZONCOMMON", "hip-amazon-common", "app-amazon", "ESB")
_comp("SAPTR_FOM", "hip-saptr-fom", "app-saptr-fom", "ESB")
_comp("MANHATTAN_WMS", "hip-manh-wms", "app-manh", "ESB")
_comp("SFDC_CX", "hip-sfdc-cx", "app-sfdc", "ESB")
_comp("SAPCE_PI7_INBOUND", "hip-pi7-in-ce", "app-pi7-ce", "ESB")
_comp("SAPUK_PI7_INBOUND", "hip-pi7-in-uk", "app-pi7-uk", "ESB")
_comp("SAPIT_PI7_INBOUND", "hip-pi7-in-it", "app-pi7-it", "ESB")
_comp("SAPNE_PI7_INBOUND", "hip-pi7-in-ne", "app-pi7-ne", "ESB")
# --- MFT-team projects ------------------------------------------------------
_comp("ANAPLAN_BPM", "hip-mft-anaplan-bpm", "app-mft-anaplan", "MFT")
_comp("ONEREADSOFT", "hip-mft-onereadsoft", "app-mft-onereadsoft", "MFT")
_comp("FUTURMASTER", "hip-mft-futurmaster", "app-mft-futurmaster", "MFT")
# --- Apigee-team project ----------------------------------------------------
_comp("eConsent", "hip-econsent-api", "app-econsent", "Apigee")
# --- Workato IDoc-out projects (hub x IDoc type) ----------------------------
HUBS = ["CE", "UK", "IT", "NE"]
IDOC_TYPES = ["YLCD01", "YHIPDELVRY07", "YHIP-COND-A04", "YHIP-BOMMAT04"]
for _h in HUBS:
    for _t in IDOC_TYPES:
        _comp(f"EURO_COMMON_IDOC_SAP{_h}_{_t}",
              f"wkt-idoc-out-{_h.lower()}-{_t.lower()}",
              f"app-wkt-idoc-{_h.lower()}", "Workato")

# --- Kafka processing groups (one topic per group) --------------------------
PROCESSING_GROUPS = [
    "opsfin-01-neo-odes-large",
    "opsfin-01-quick",
    "opsfin-01-default",
    "sapit-01-default",
    "kepler-01-default",
    "procout-01-default",
    "amazon-01-default",
]
_PG_K8S = {
    "opsfin-01-neo-odes-large": "hip-esb-odes-large",
    "opsfin-01-quick": "hip-esb-opsfin-quick",
    "opsfin-01-default": "hip-esb-opsfin-default",
    "sapit-01-default": "hip-esb-sapit-default",
    "kepler-01-default": "hip-esb-kepler-default",
    "procout-01-default": "hip-esb-procout-default",
    "amazon-01-default": "hip-esb-amazon-default",
}
for _g in PROCESSING_GROUPS:
    _comp(_g, _PG_K8S[_g], "app-" + _PG_K8S[_g][len("hip-"):], "ESB", "processing_group")

# --- framework / platform / listener components -----------------------------
_comp("hip-fwk-transco-cache", "hip-fwk-transco-cache", "app-fwk-transco", "Azure/Platform", "framework")
_comp("AN_COMMON_PI7IDOCListner", "hip-pi7-idoc-listener", "app-pi7-listener", "ESB", "listener")
_comp("SAPCE_RFC_GATEWAY", "sapce-rfc-gw", "app-sapce-rfc", "Workato", "platform")
_comp("SAPNE_RFC_GATEWAY", "sapne-rfc-gw", "app-sapne-rfc", "Workato", "platform")
_comp("WORKATO_PLATFORM", "workato-platform", "app-workato", "Workato", "platform")
_comp("CONFLUENT_EMEA", "confluent-emea", "app-confluent", "Kafka", "platform")
_comp("APIGEE_EDGE", "apigee-gw", "app-apigee", "Apigee", "platform")
_comp("FRCPD", "frcpd-fm-db", "app-frcpd", "ETL", "platform")
_comp("SONAR-OPS", "sonar-ops", "app-sonar-ops", "ESB", "platform")
_comp("AKS-HIP-EMEA-PRD", "aks-hip-emea-prd", "app-aks-emea", "Azure/Platform", "platform")

HOSTS = {  # host name -> team (Splunk Linux host alerts; the CMDB name IS the host name)
    "FRHIPGPRMFTSI01": "MFT",
    "FRHIPGPRMFTSI02": "MFT",
    "FRHIPGPPMFTSI01": "MFT",
    "FRHIPGQAMFTSI01": "MFT",
    "SGLORHIPPMFTSI1": "MFT",
    "SGLORHIPQETLPC1": "ETL",
    "SGLORHIPPETLPC1": "ETL",
    "USAMRHIPDFTSI01": "MFT",
}
for _h, _team in HOSTS.items():
    COMPONENTS[_h] = {"k8s_prefix": _h.lower(), "elk_alias": "host-" + _h.lower(), "team": _team, "kind": "host"}

STANDING_NOISE = [
    {"host": "SGLORHIPQETLPC1", "rule_id": "SPL-CAPLINERR002", "metric": "swap_pct",
     "threshold": 90, "text": "Linux Host: SGLORHIPQETLPC1 has more than 90% swap space usage over last 30 mins"},
    {"host": "FRHIPGQAMFTSI01", "rule_id": "SPL-CAPLINERR001", "metric": "cpu_pct",
     "threshold": 98, "text": "CAPLINERR001-Linux Host - FRHIPGQAMFTSI01 has more than 98% of CPU over last 1 h"},
]

# --------------------------------------------------------------------------
# Kafka topic / consumer group naming
# --------------------------------------------------------------------------

def topic_for(group):
    return f"emea.it4it.fwk-message.process-int-{group}.v1"


def consumer_group_for(group):
    return f"hip-esb-{group}-cg"


# --------------------------------------------------------------------------
# Exchange catalogue (the unit everything keys on)
# --------------------------------------------------------------------------
# id_kind: 'n24' = yyyymmddHHMMSS + 10 digits ; 'uuid' = framework-native flow
# transco: half-flow indexes (0-based) that call hip-fwk-transco-cache
EXCHANGES = {}
HALFFLOW_TO_PROJECT = {}


def _ex(key, exchange, project, hf, src, dst, obj, oid_prefix, group, mean_ms,
        fw="4.12.3", id_kind="n24", transco=(), style="std", bvals=None, team=None):
    EXCHANGES[key] = {
        "key": key, "exchange": exchange, "project": project, "halfflows": hf,
        "source": src, "destination": dst, "object_name": obj,
        "oid_prefix": oid_prefix, "group": group, "mean_ms": mean_ms,
        "fw": fw, "id_kind": id_kind, "transco": list(transco), "style": style,
        "bvals": bvals or ["CZ01", "IT10", "FR22", "PL04", "DE07", "GB03", "ES05", "NL02"],
        "team": team or COMPONENTS[project]["team"],
    }
    for h in hf:
        HALFFLOW_TO_PROJECT[h] = project


def _hf(name, suffixes):
    return [f"{name}_{s}" for s in suffixes]


ESB4 = ["01_ESB", "02_ESB", "03_ESB", "04_ESB"]
API4 = ["01_ESB", "02_ESB", "03_ESB", "04_API"]
MFT4 = ["01_MFT", "02_ESB", "03_ESB", "04_MFT"]

# S1 focal
_ex("asn", "GLBL_SAPS4HANA_SAPS4HANA_ASN_INT", "SAPS4HANA_ASN",
    _hf("GLBL_SAPS4HANA_SAPS4HANA_ASN_INT", ESB4), "MANH_MAWM", "SAPS4HANA_NEO",
    "ASN", "18", "opsfin-01-neo-odes-large", 4200, fw="5.0.2")

# S5: 16 transco-calling flows in 4 projects (=> 32 distinct half-flows fail)
_ex("sapit_so", "EMEA_SAPIT_SALESORDER", "SAPITCOMMON",
    ["EMEA_SAPIT_SALESORDER_01_ESB_V2", "EMEA_SAPIT_SALESORDER_02_ESB",
     "EMEA_SAPIT_SALESORDER_03_ESB", "EMEA_SAPIT_SALESORDER_04_API"],
    "SFDC_CX", "SAPIT", "SALES_ORDER", "70", "sapit-01-default", 2600, transco=(0, 1))
for _k, _n, _o, _obj in [("sapit_inv", "EMEA_SAPIT_INVOICE_OUT", "SAPIT", "INVOICE"),
                         ("sapit_del", "EMEA_SAPIT_DELIVERY_STATUS", "SAPIT", "DELIVERY"),
                         ("sapit_ret", "EMEA_SAPIT_RETURNS_IN", "SAPIT", "RETURN_ORDER")]:
    _ex(_k, _n, "SAPITCOMMON", _hf(_n, API4), "SFDC_CX", _o, _obj, "80", "sapit-01-default", 2400, transco=(0, 1))
_ex("kepler_so", "EMEA_KEPLERNG_SALESORDER_OUT", "KEPLER_NEXTGEN",
    _hf("EMEA_KEPLERNG_SALESORDER_OUT", API4), "KEPLER_NG", "SAPIT", "SALES_ORDER", "71",
    "kepler-01-default", 2900, transco=(0, 1))
for _k, _n, _obj in [("kepler_ship", "EMEA_KEPLERNG_SHIPMENT_OUT", "SHIPMENT"),
                     ("kepler_cust", "EMEA_KEPLERNG_CUSTOMER_SYNC", "CUSTOMER"),
                     ("kepler_inv", "EMEA_KEPLERNG_INVOICE_OUT", "INVOICE"),
                     ("kepler_pr", "EMEA_KEPLERNG_PRICE_LIST", "PRICE_LIST"),
                     ("kepler_ret", "EMEA_KEPLERNG_RETURNS_IN", "RETURN_ORDER")]:
    _ex(_k, _n, "KEPLER_NEXTGEN", _hf(_n, API4), "KEPLER_NG", "SAPIT", _obj, "72",
        "kepler-01-default", 2700, transco=(0, 1))
_ex("procout_notif", "EURO_0004_ProcessOutNotification_to_SAPCE", "PROCESSOUT",
    [f"EURO_0004_{n:02d}_ProcessOutNotification_to_SAPCE_ESB_{n:02d}" for n in range(1, 5)],
    "PROCESSOUT", "SAPCE", "NOTIFICATION", "60", "procout-01-default", 2100, transco=(0, 1))
_ex("procout_ack", "EURO_0005_ProcessOutAck_to_SAPCE", "PROCESSOUT",
    [f"EURO_0005_{n:02d}_ProcessOutAck_to_SAPCE_ESB_{n:02d}" for n in range(1, 5)],
    "PROCESSOUT", "SAPCE", "ACKNOWLEDGEMENT", "61", "procout-01-default", 1900, transco=(0, 1))
_ex("procout_hu", "EURO_0006_ProcessOutHandlingUnit_to_SAPCE", "PROCESSOUT",
    [f"EURO_0006_{n:02d}_ProcessOutHandlingUnit_to_SAPCE_ESB_{n:02d}" for n in range(1, 5)],
    "PROCESSOUT", "SAPCE", "HANDLING_UNIT", "62", "procout-01-default", 2300, transco=(0, 1))
for _k, _n, _obj in [("amz_order", "EMEA_AMAZON_ORDER_CONFIRM", "ORDER_CONFIRMATION"),
                     ("amz_stock", "EMEA_AMAZON_STOCK_FEED", "STOCK_LEVEL"),
                     ("amz_ret", "EMEA_AMAZON_RETURN_NOTIFY", "RETURN_NOTIFICATION")]:
    _ex(_k, _n, "AMAZONCOMMON", _hf(_n, API4), "SAPIT", "AMAZON_SC", _obj, "73",
        "amazon-01-default", 2500, transco=(0, 1))

# non-transco background flows
_ex("saptr_inv", "EMEA_SAPTR_FOM_INVENTORY_SG", "SAPTR_FOM",
    ["EMEA_SAPTR_FOM_INVENTORY_SG_01_ESB", "EMEA_SAPTR_FOM_INVENTORY_SG_02_ESB",
     "EMEA_SAPTR_FOM_INVENTORY_SG_03_ESB", "EMEA_SAPTR_FOM_INVENTORY_SG_04_ESB"],
    "SAPTR", "FOM", "INVENTORY", "34", "opsfin-01-quick", 1800, id_kind="uuid", fw="5.0.2")
_ex("saptr_hier", "EMEA_FOM_TRAM_SAPTR_CONFIG_PROD_HIER", "SAPTR_FOM",
    ["EMEA_FOM_TRAM_SAPTR_CONFIG_PROD_HIER_01_ESB", "EMEA_FOM_TRAM_SAPTR_CONFIG_PROD_HIER_02_ESB",
     "EMEA_FOM_TRAM_SAPTR_CONFIG_PROD_HIER_03_ESB", "EMEA_FOM_TRAM_SAPTR_CONFIG_PROD_HIER_04_ESB"],
    "SAPTR", "FOM", "PRODUCT_HIERARCHY", "35", "opsfin-01-default", 3100)
_ex("manh_inv", "EMEA_MANH_INVENTORY_SNAPSHOT", "MANHATTAN_WMS",
    _hf("EMEA_MANH_INVENTORY_SNAPSHOT", ESB4), "MANH_MAWM", "SAPS4HANA_NEO", "STOCK_SNAPSHOT", "50",
    "opsfin-01-default", 3600)
_ex("manh_ship", "EMEA_MANH_SHIPMENT_CONFIRM", "MANHATTAN_WMS",
    _hf("EMEA_MANH_SHIPMENT_CONFIRM", ESB4), "MANH_MAWM", "SAPS4HANA_NEO", "SHIPMENT_CONFIRMATION", "51",
    "opsfin-01-quick", 2000)
_ex("sfdc_cust", "EMEA_SFDC_CUSTOMER_SYNC", "SFDC_CX",
    _hf("EMEA_SFDC_CUSTOMER_SYNC", API4), "SFDC_CX", "SAPS4HANA_NEO", "CUSTOMER", "52",
    "opsfin-01-quick", 1500, id_kind="uuid", fw="5.0.2")
_ex("econsent", "EMEA_eCONSENT_HIPESB_CustomerEnrollment", "eConsent",
    ["EMEA_eCONSENT_HIPESB_CustomerEnrollment_01_API", "EMEA_eCONSENT_HIPESB_CustomerEnrollment_02_ESB",
     "EMEA_eCONSENT_HIPESB_CustomerEnrollment_03_ESB", "EMEA_eCONSENT_HIPESB_CustomerEnrollment_04_API"],
    "ECONSENT_WEB", "SFDC_CX", "CONSENT", "53", "opsfin-01-quick", 900, id_kind="uuid", fw="5.0.2")
# file / MFT flows
_ex("bpm_fm", "GLBL_OPSF_ANAPLAN_BPM_to_FM", "ANAPLAN_BPM",
    _hf("GLBL_OPSF_ANAPLAN_BPM_to_FM", MFT4), "ANAPLAN", "FM_FRCPD", "FILE", "BPM_to_FM_",
    "opsfin-01-quick", 45000)
_ex("onereadsoft", "GLBL_APAC_AZURE_ONEREADSOFT", "ONEREADSOFT",
    _hf("GLBL_APAC_AZURE_ONEREADSOFT", MFT4), "ONEREADSOFT", "AZURE_BLOB", "FILE", "OR_EXPORT_",
    "opsfin-01-default", 21000)
_ex("futurmaster", "GLBL_FUTURMASTER_FORECAST", "FUTURMASTER",
    _hf("GLBL_FUTURMASTER_FORECAST", MFT4), "FUTURMASTER", "ANAPLAN", "FILE", "FCST_",
    "opsfin-01-default", 30000)
# PI7 inbound (S2): one project + listener per hub
for _h in HUBS:
    _ex(f"pi7_{_h.lower()}", f"EMEA_SAP{_h}_PI7_IDOC_DELVRY07_TO_MANH", f"SAP{_h}_PI7_INBOUND",
        _hf(f"EMEA_SAP{_h}_PI7_IDOC_DELVRY07_TO_MANH", ESB4), f"SAP{_h}_PI7", "MANH_MAWM",
        "DELVRY07", "0000000", "opsfin-01-quick", 2200)
# IDoc-out (S3): hub x type, half-flow 03 (idx 2) is the Workato ConfigForDocSending call
_DINTG = {"YLCD01": 2505, "YHIPDELVRY07": 2484, "YHIP-COND-A04": 2361, "YHIP-BOMMAT04": 2359}
for _hi, _h in enumerate(HUBS):
    for _t in IDOC_TYPES:
        _name = f"EURO_COMMON_IDOC_SAP{_h}_{_t}"
        _n = _DINTG[_t] + 100 * _hi
        _ex(f"idoc_{_h.lower()}_{_t.lower()}", _name, _name,
            [f"EURO_RFCT_DINTG{_n:07d}_{_t}_{i:02d}" for i in range(1, 5)],
            "MANH_MAWM", f"SAP{_h}", _t, "0000000000", "opsfin-01-default", 2600, style="idoc")

# FRCPD downstream (S4): FKF generation reads the BPM_to_FM output
_ex("frcpd_fkf", "GLBL_FRCPD_FM_FKF_GENERATION", "FRCPD",
    _hf("GLBL_FRCPD_FM_FKF_GENERATION", ESB4), "FM_FRCPD", "FRCPD", "FKF", "FKF", "opsfin-01-default", 8000)

# batch / wait-for-file (long-running INPROGRESS are normal on the real dashboard)
_ex("waitfile", "GLBL_SCHEDULER_WAITFORFILE", "ONEREADSOFT",
    ["GLBL_SCHEDULER_WAITFORFILE_01_MFT", "GLBL_SCHEDULER_WAITFORFILE_02_ESB"],
    "SCHEDULER", "ONEREADSOFT", "FILE_WATCH", "W", "opsfin-01-default", 0)
_ex("slowbatch", "GLBL_CTRLM_MASTERDATA_BATCH", "SAPTR_FOM",
    _hf("GLBL_CTRLM_MASTERDATA_BATCH", ESB4), "CONTROL-M", "SAPS4HANA_NEO", "BATCH", "B",
    "opsfin-01-default", 900000)

IDOC_KEYS = [k for k in EXCHANGES if k.startswith("idoc_")]
TRANSCO_KEYS = [k for k, v in EXCHANGES.items() if v["transco"]]

# PI7 listener names per hub
PI7_LISTENER = {"CE": "AN_COMMON_PI7IDOCListner", "UK": "AN_COMMON_PI7IDOCListner_UK",
                "IT": "AN_COMMON_PI7IDOCListner_IT", "NE": "AN_COMMON_PI7IDOCListner_NE"}
for _h, _l in PI7_LISTENER.items():
    HALFFLOW_TO_PROJECT[_l] = f"SAP{_h}_PI7_INBOUND" if _h != "CE" else "AN_COMMON_PI7IDOCListner"

# Special: standalone HIPMON "project" names for platform-level alerts
HIPMON_KAFKA_PROJECT = "KAFKA_LAG"


def halfflow_project(halfflow):
    return HALFFLOW_TO_PROJECT.get(halfflow)


def pod_name(cmdb, suffix):
    return f"{COMPONENTS[cmdb]['k8s_prefix']}-{suffix}"


def elk_index(cmdb):
    return f"{COMPONENTS[cmdb]['elk_alias']}-2026.09.18"


def team_of(cmdb):
    return COMPONENTS.get(cmdb, {}).get("team", "ESB")


def alias_map() -> dict:
    """
    {name_or_alias: cmdb_name} covering every naming variant a raw record
    might carry: the CMDB/project name itself, the Kubernetes
    deployment/pod prefix, the ELK index alias stem, and every half-flow
    name (-> its project). Consumers do longest-prefix-wins matching,
    because pod names append a hash suffix (e.g. hip-esb-odes-large-6d8f7b9c5-x2kfp).
    """
    m = {}
    for cmdb, info in COMPONENTS.items():
        m[info["k8s_prefix"]] = cmdb
        m[info["elk_alias"]] = cmdb
        m[cmdb] = cmdb
    for hf, proj in HALFFLOW_TO_PROJECT.items():
        m[hf] = proj
    return m
