#!/usr/bin/env python3
"""Builds the Live-mode window from the team-provided "synthetic" export instead of the
real one, then runs it through our own full scrub on top.

Why the extra scrub: the team's own file only partially masks a few columns (first 3 +
"XXX" + last 2-3 characters of names, e.g. "cheXXXef@lorXXXal.com" -- which still shows
the real company's domain and enough of the local part to be identifiable). Those exact
columns (Caller, Assigned to, Updated by, Resolved by) are ones this pipeline already
drops entirely, same as the real-data extractor -- but free-text fields (Subject,
Details, Close notes) can still contain emails, phone numbers and names, and identifiers
like Configuration Item are only lightly masked. This script keeps the same 20 columns,
same June 9-11 window and same schema as extract_live_incidents.py, then applies the
same scrub as synthesize_live_window.py (emails, phones, names, ids, the company name).

Input : the workbook path (positional arg or HIP_TEAM_XLSX env var), sheet "June".
Output: synthetic-data/live/june-window.synthetic.json (git-ignored) -- overwrites the
        previous synthetic window. Does not touch server/live-data/june-window.json
        (the real one) or anything else.
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_live_incidents as E  # reuses KEEP_COLUMNS, WINDOW_START/END, offset/clean helpers
import synthesize_live_window as S  # reuses scrub(), scrub_names(), the salted id mapping

REPO_ROOT = S.REPO_ROOT
OUT = os.path.join(REPO_ROOT, "synthetic-data", "live", "june-window.synthetic.json")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HIP_TEAM_XLSX")
    if not src or not os.path.exists(src):
        sys.exit("usage: build_team_synthetic_window.py <path-to-team-file.xlsx> (or set HIP_TEAM_XLSX)")

    df = pd.read_excel(src, sheet_name="June")
    window_start, window_end = pd.Timestamp(E.WINDOW_START), pd.Timestamp(E.WINDOW_END)
    w = df[(df["Opened"] >= window_start) & (df["Opened"] < window_end)].copy().sort_values("Opened")

    records = []
    for _, row in w.iterrows():
        rec = {out_key: E.clean(row[src_col]) for src_col, out_key in E.KEEP_COLUMNS.items()}
        rec["opened_offset_sec"] = E.to_offset_seconds(row["Opened"], window_start)
        rec["updated_offset_sec"] = E.to_offset_seconds(row["Updated"], window_start)
        rec["resolved_offset_sec"] = E.to_offset_seconds(row["Resolved"], window_start)
        records.append(rec)

    # scrub every string field (subject/details/close_notes/config item/etc.), same rules as the real pipeline
    TEXT_FIELDS = ["subject", "details", "close_notes", "configuration_item", "service",
                   "classification_keyword", "sub_classification", "team", "assignment_group"]
    ID_FIELDS = ["number", "parent_incident"]
    scrubbed = []
    for rec in records:
        r = dict(rec)
        for f in TEXT_FIELDS:
            v = rec.get(f)
            if isinstance(v, str):
                r[f] = S.scrub(S.plain(v) if f in ("details", "close_notes") else v)
        for f in ID_FIELDS:
            v = rec.get(f)
            if isinstance(v, str):
                r[f] = S.scrub(v)
        scrubbed.append(r)

    out = {
        "source": "Synthetic replay window provided by the team (June 2026, further scrubbed): "
                   "production identifiers, emails, phone numbers and names removed",
        "synthetic": True,
        "window_start_real": E.WINDOW_START,
        "window_end_real": E.WINDOW_END,
        "window_seconds": round((window_end - window_start).total_seconds()),
        "redacted_fields": ["Caller", "Assigned to", "Updated by", "Resolved by"],
        "incident_count": len(scrubbed),
        "incidents": scrubbed,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # leak check, same style as the rest of the pipeline
    blob = json.dumps(out, ensure_ascii=False).lower()
    leaks = sorted(o for o in S.full_originals if len(o) >= 4 and o in blob and o != "0.0.0.0" and o not in S.produced)
    print(f"Wrote {len(scrubbed)} incidents (window {E.WINDOW_START} -> {E.WINDOW_END}) to {OUT}")
    print(f"production identifiers replaced: {len(S.full_originals)}")
    print("whole production identifiers still present:", leaks[:10] or "none")
    print("'loreal' anywhere:", "loreal" in blob)
    import re
    print("e-mails not example.invalid:", sorted(set(m for m in re.findall(r"[\w.+-]+@[\w.-]+", blob) if not m.endswith("example.invalid"))) or "none")
    return 0 if not leaks else 1


if __name__ == "__main__":
    sys.exit(main())
