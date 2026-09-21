#!/usr/bin/env python3
"""Extracts a real 48h window of June 2026 HIP incidents for the "Live"
mode, redacting every person-identifying field and converting absolute
timestamps into an offset (seconds since the window start) so the
frontend can replay them anchored to "now" instead of the real date.

Input:  Auto Alerts/June-2026 HIP OPS Incident Inflow Analysis.xlsx in this repo (git-ignored);
        override the path with the HIP_JUNE_XLSX environment variable.
Output: server/live-data/june-window.json  (gitignored -- redacted but
        still-real client ticket text, same privacy rule as /Auto Alerts/)

Kept fields are all either org units (Assignment group, Team -- checked
by hand against the real values; they are role/team names like "TECH
FNDN - WW - HIP INCIDENT L1", never a person) or ticket content. Dropped
outright: Caller, Assigned to, Updated by, Resolved by -- every column
that can hold a real employee's name.
"""
import json
import os
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Override with HIP_JUNE_XLSX; the default is the git-ignored /Auto Alerts/ folder in this repo.
SRC = os.environ.get(
    "HIP_JUNE_XLSX",
    os.path.join(REPO_ROOT, "Auto Alerts", "June-2026 HIP OPS Incident Inflow Analysis.xlsx"),
)
OUT_DIR = os.path.join(REPO_ROOT, "server", "live-data")
OUT_PATH = os.path.join(OUT_DIR, "june-window.json")

WINDOW_START = "2026-06-09 00:00:00"
WINDOW_END = "2026-06-11 00:00:00"

KEEP_COLUMNS = {
    "Number": "number",
    "Subject": "subject",
    "Details (description)": "details",
    "IT Organization": "it_organization",
    "Zone": "zone",
    "Service": "service",
    "Configuration Item": "configuration_item",
    "Priority": "priority",
    "Parent Incident": "parent_incident",
    "State": "state",
    "Assignment group": "assignment_group",
    "Team": "team",
    "Close code": "close_code",
    "Subclose code": "subclose_code",
    "Close notes": "close_notes",
    "Reassignment count": "reassignment_count",
    "Reopen count": "reopen_count",
    "Classification Keyword": "classification_keyword",
    "Sub Classification": "sub_classification",
    "Environment": "environment",
}

# Explicitly dropped, never written out: Caller, Updated by, Assigned to,
# Resolved by, Updated, BP, Auto, Opened Date, Opened Hour (redundant with
# Opened once we compute offsets).


def to_offset_seconds(ts, window_start):
    if pd.isna(ts):
        return None
    return round((ts - window_start).total_seconds())


def clean(v):
    if pd.isna(v):
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def main():
    if not os.path.exists(SRC):
        print(f"Source export not found at {SRC}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_excel(SRC, sheet_name="RawData", usecols="A:AE")
    window_start = pd.Timestamp(WINDOW_START)
    window_end = pd.Timestamp(WINDOW_END)
    w = df[(df["Opened"] >= window_start) & (df["Opened"] < window_end)].copy()
    w = w.sort_values("Opened")

    records = []
    for _, row in w.iterrows():
        rec = {out_key: clean(row[src_col]) for src_col, out_key in KEEP_COLUMNS.items()}
        rec["opened_offset_sec"] = to_offset_seconds(row["Opened"], window_start)
        rec["updated_offset_sec"] = to_offset_seconds(row["Updated"], window_start)
        rec["resolved_offset_sec"] = to_offset_seconds(row["Resolved"], window_start)
        records.append(rec)

    out = {
        "source": "June 2026 HIP OPS Incident Inflow Analysis (RawData sheet), redacted",
        "window_start_real": WINDOW_START,
        "window_end_real": WINDOW_END,
        "window_seconds": round((window_end - window_start).total_seconds()),
        "redacted_fields": ["Caller", "Assigned to", "Updated by", "Resolved by"],
        "incident_count": len(records),
        "incidents": records,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(records)} redacted incidents to {OUT_PATH}")
    print(f"Window: {WINDOW_START} -> {WINDOW_END} ({out['window_seconds']}s)")


if __name__ == "__main__":
    main()
