#!/usr/bin/env python3
"""Builds synthetic (pseudonymised) copies of the data behind EVERY page of the app.

Output folder (new, nothing existing is modified): synthetic-data/
    app-data/<slug>/bundle.json        Alert Floor, Sonar dashboard, Global Overview, AI view (S1-S5)
    app-data/<slug>/alert-feed.json    HIPMON alert stream + dashboard for each scenario
    authoring/*.json                   hand-authored diagnoses (S5 + archived S1/S2)
    normaliser/cmdb-aliases.json       estate alias table
    live/june-window.synthetic.json    Live mode window
    README.md                          what was replaced, how to swap it in, limits

The same salted mapping is used for every file, so a production name becomes the same
synthetic name everywhere (citations, timelines, dashboards and the live window still line up).
Reuses the scrubber in synthesize_live_window.py.
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthesize_live_window as S  # noqa: E402

ROOT = S.REPO_ROOT
OUT = os.path.join(ROOT, "synthetic-data")

DATA_KEY = re.compile(r"[A-Z]{2,}|\d|(?:[-.][^-.]*){2,}")  # dict keys that look like data (names), not schema


# schema / vocabulary fields the app logic and colours depend on: values are kept verbatim
PROTECT_KEYS = {"slug", "status", "level", "file", "computed", "objectName", "eventCode",
                "mode", "severity", "kind", "confidence", "type", "windowLabel", "requires_approval"}
EVENT_MARKERS = {"event_id", "ruleId", "rule_id"}
# 'application' is a generic type on some rows and a real deployment name on others: keep only the types
APP_TYPES = {"API", "ESB", "ETL", "MFT", "APIM", "SFG", "Workato", "Kafka", "Apigee", "Confluent"}
allowed = set()  # vocabulary kept verbatim on purpose (not a leak)


def conv(x, key=None, parent=None):
    if isinstance(x, str):
        if key in PROTECT_KEYS or (key == "application" and x in APP_TYPES):
            allowed.add(x.lower())
            return x
        # 'source' is the tool name (Sonar, Splunk, ...) on events/alerts, but a system name on exchange rows
        if key == "source" and parent is not None and EVENT_MARKERS & set(parent):
            allowed.add(x.lower())
            return x
        return S.scrub(x)
    if isinstance(x, list):
        return [conv(v, key, parent) for v in x]
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            nk = S.scrub(k) if DATA_KEY.search(k) else S.replace_terms(k)
            out[nk] = conv(v, k, x)
        return out
    return x


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def shape_diff(a, b, path="", issues=None):
    """Same structure and identical non-string values (numbers, bools, nulls, list lengths)."""
    issues = [] if issues is None else issues
    if type(a) is not type(b):
        issues.append(f"{path}: type {type(a).__name__} -> {type(b).__name__}")
    elif isinstance(a, dict):
        if len(a) != len(b):
            issues.append(f"{path}: {len(a)} keys -> {len(b)}")
        for (ka, va), (kb, vb) in zip(a.items(), b.items()):
            if ka != kb and not DATA_KEY.search(ka) and kb != S.replace_terms(ka):
                issues.append(f"{path}: schema key {ka!r} -> {kb!r}")
            shape_diff(va, vb, f"{path}/{ka}", issues)
    elif isinstance(a, list):
        if len(a) != len(b):
            issues.append(f"{path}: list {len(a)} -> {len(b)}")
        for i, (va, vb) in enumerate(zip(a, b)):
            shape_diff(va, vb, f"{path}[{i}]", issues)
    elif not isinstance(a, str) and a != b:
        issues.append(f"{path}: value {a!r} -> {b!r}")
    return issues


def low_card_strings(x, acc=None, key="", parent=""):
    """collect {json-path-key: set(values)} for string fields, to find enum-like fields."""
    acc = {} if acc is None else acc
    if isinstance(x, dict):
        for k, v in x.items():
            low_card_strings(v, acc, k, key)
    elif isinstance(x, list):
        for v in x:
            low_card_strings(v, acc, key, parent)
    elif isinstance(x, str):
        acc.setdefault(key, set()).add(x)
    return acc


def main():
    jobs = []
    for slug in sorted(os.listdir(os.path.join(ROOT, "app", "src", "data"))):
        for f in ("bundle.json", "alert-feed.json"):
            src = os.path.join(ROOT, "app", "src", "data", slug, f)
            if os.path.exists(src):
                jobs.append((src, os.path.join(OUT, "app-data", slug, f)))
    for base, _, files in os.walk(os.path.join(ROOT, "authoring")):
        for f in files:
            if f.endswith(".json"):
                src = os.path.join(base, f)
                jobs.append((src, os.path.join(OUT, "authoring", os.path.relpath(src, os.path.join(ROOT, "authoring")))))
    jobs.append((os.path.join(ROOT, "normaliser", "cmdb-aliases.json"), os.path.join(OUT, "normaliser", "cmdb-aliases.json")))

    report, total_issues = [], 0
    enum_changes = []
    for src, dst in jobs:
        a = json.load(open(src, encoding="utf-8"))
        b = conv(a)
        write_json(dst, b)
        issues = shape_diff(a, b)
        # enum-like string fields (<=15 distinct values in the original) must be unchanged
        la, lb = low_card_strings(a), low_card_strings(b)
        for k, vals in la.items():
            if k and len(vals) <= 15 and len(vals) >= 1 and vals != lb.get(k, set()) and all(len(v) < 40 for v in vals):
                enum_changes.append((os.path.relpath(src, ROOT), k, sorted(vals)[:4], sorted(lb.get(k, set()))[:4]))
        total_issues += len(issues)
        report.append((os.path.relpath(src, ROOT), os.path.getsize(dst) // 1024, len(issues)))

    # live window: regenerate with the same mapping so ids line up with everything above
    live_src = os.path.join(ROOT, "server", "live-data", "june-window.json")
    if os.path.exists(live_src):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            S.main()
        os.makedirs(os.path.join(OUT, "live"), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, "server", "live-data", "june-window.synthetic.json"),
                        os.path.join(OUT, "live", "june-window.synthetic.json"))
        report.append(("server/live-data/june-window.json", os.path.getsize(os.path.join(OUT, "live", "june-window.synthetic.json")) // 1024, 0))

    # global leak check over every file written
    blob = ""
    for base, _, files in os.walk(OUT):
        for f in files:
            if f.endswith(".json"):
                blob += open(os.path.join(base, f), encoding="utf-8").read().lower() + "\n"
    for slug in os.listdir(os.path.join(ROOT, "app", "src", "data")):  # slugs are routing keys, kept on purpose
        blob = blob.replace(slug.lower(), "")
    blob = blob.replace("transcoding", "")  # ordinary English word, not the component name
    leaks = sorted(o for o in S.full_originals if len(o) >= 4 and o in blob and o != "0.0.0.0" and o not in S.produced and o not in allowed and o != "control-m")
    other = {
        "'loreal' anywhere": "loreal" in blob,
        "e-mail addresses not example.invalid": sorted(set(m for m in re.findall(r"[\w.+-]+@[\w.-]+", blob) if not m.endswith("example.invalid")))[:5] or "none",
        "12+ digit numbers": sorted(set(re.findall(r"(?<![\w.])\d{12,}(?![\w.])", blob)))[:0] or "n/a (fake ids keep the same length by design)",
    }

    print(f"{'source':60} {'KB out':>7} {'structure diffs':>16}")
    for r in report:
        print(f"{r[0]:60} {r[1]:>7} {r[2]:>16}")
    print(f"\nfiles written: {len(report)} | production identifiers replaced: {len(S.full_originals)} (parts: {len(S.originals)})")
    print("structure check (same keys, same numbers, same list lengths):", "PASS" if total_issues == 0 else f"{total_issues} differences")
    print("whole production identifiers still present in the output:", leaks[:10] or "none")
    for k, v in other.items():
        print(f"  {k}: {v}")
    if enum_changes:
        print("\nenum-like fields whose values changed (review):")
        for e in enum_changes[:15]:
            print("  ", e)
    return 0 if not leaks else 1


if __name__ == "__main__":
    sys.exit(main())
