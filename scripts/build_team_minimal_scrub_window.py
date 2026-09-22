#!/usr/bin/env python3
"""Builds a MINIMAL-touch alternative to build_team_synthetic_window.py, for comparison.

Same source (the team's file), same June 9-11 window, same schema and same dropped
columns (Caller/Assigned to/Updated by/Resolved by/Auto/Opened Date/Opened Hour/BP/Role)
as the "full" build. The difference is how much of what's left gets touched:

  build_team_synthetic_window.py (the current default, "full")
    Re-scrubs every identifier-shaped field on top of the team's own masking:
    number, subject, details, close_notes, service, configuration_item,
    sub_classification, assignment_group, parent_incident.

  build_team_minimal_scrub_window.py (this file, "minimal")
    Leaves ALL of those exactly as the team's file has them -- including their
    own partial "XXX" masking, unmodified. The only things removed are the
    three genuine privacy problems found in the team's file: e-mail addresses,
    phone numbers, and personal names in free text (sign-offs, greetings, mail
    headers, "SURNAME Firstname - ..." subject lines) -- and only inside the
    three free-text fields (subject, details, close_notes). Everything else,
    including incident numbers, is passed through byte-for-byte.

Output: synthetic-data/live/june-window.minimal.json (git-ignored).
Neither this script nor the "full" one ever touches the real export or the
git-tracked server/live-data/june-window.json; see docs/VM-SYNTHETIC-DATA.md
for how to put either variant into service.
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_live_incidents as E
import synthesize_live_window as S

REPO_ROOT = S.REPO_ROOT
OUT = os.path.join(REPO_ROOT, "synthetic-data", "live", "june-window.minimal.json")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# the company's real name, wherever it appears -- including inside an internal hostname/domain
# like "IEM...EMEA.LOREAL.INTRA" (found unmasked in the team's file; not optional to keep)
BRAND_RE = re.compile(r"L['’]?Or[ée]al", re.I)


def minimal_scrub(text):
    """Company name, names, phone numbers, e-mails -- nothing else. No id/word replacement."""
    if not text:
        return text
    text = BRAND_RE.sub("Acme", text)
    text = S.scrub_names(text)
    text = S.PHONE_CTX.sub(lambda m: m.group("lead") + "[phone]", text)
    text = S.PHONE_RAW.sub("[phone]", text)
    text = EMAIL_RE.sub(lambda m: f"user-{S.fake_word(m.group(0).split('@')[0])}@example.invalid", text)
    return text


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HIP_TEAM_XLSX")
    if not src or not os.path.exists(src):
        sys.exit("usage: build_team_minimal_scrub_window.py <path-to-team-file.xlsx> (or set HIP_TEAM_XLSX)")

    df = pd.read_excel(src, sheet_name="June")
    window_start, window_end = pd.Timestamp(E.WINDOW_START), pd.Timestamp(E.WINDOW_END)
    w = df[(df["Opened"] >= window_start) & (df["Opened"] < window_end)].copy().sort_values("Opened")

    FREE_TEXT = {"subject", "details", "close_notes"}
    records = []
    for _, row in w.iterrows():
        rec = {}
        for src_col, out_key in E.KEEP_COLUMNS.items():
            v = E.clean(row[src_col])
            if out_key in FREE_TEXT and isinstance(v, str):
                v = minimal_scrub(S.plain(v) if out_key in ("details", "close_notes") else v)
            rec[out_key] = v
        rec["opened_offset_sec"] = E.to_offset_seconds(row["Opened"], window_start)
        rec["updated_offset_sec"] = E.to_offset_seconds(row["Updated"], window_start)
        rec["resolved_offset_sec"] = E.to_offset_seconds(row["Resolved"], window_start)
        records.append(rec)

    out = {
        "source": "Team-provided window (June 2026), minimally touched: only e-mails, phone numbers "
                   "and personal names removed from free text -- every other field, including the "
                   "team's own partial masking, is unchanged from their file",
        "synthetic": True,
        "minimal_scrub": True,
        "window_start_real": E.WINDOW_START,
        "window_end_real": E.WINDOW_END,
        "window_seconds": round((window_end - window_start).total_seconds()),
        "redacted_fields": ["Caller", "Assigned to", "Updated by", "Resolved by"],
        "incident_count": len(records),
        "incidents": records,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")

    blob = json.dumps(out, ensure_ascii=False).lower()
    print(f"Wrote {len(records)} incidents to {OUT}")
    print("'loreal' anywhere:", "loreal" in blob)
    emails = sorted(set(m for m in re.findall(r"[\w.+-]+@[\w.-]+", blob) if not m.endswith("example.invalid")))
    print("e-mails not example.invalid:", emails or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
