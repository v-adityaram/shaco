#!/usr/bin/env python3
"""Builds docs/architecture.html: a single self-contained page that explains, from the
REAL files, how a request flows through this project -- what is sent, in what shape, to
whom, and the full prompt. Nothing is retyped: the prompt text, the sample payloads and
the size figures are read from prompts/, data/ and server/cache/ every time it runs.

The output (docs/architecture.html) is git-ignored; this generator is committed.
Standard library only.   python scripts/build_architecture_html.py
"""
import html
import json
import os
import re
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "architecture.html")
SLUG = "s3-vendor-release"  # the scenario used for the worked example


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def load(*p):
    return json.loads(read(*p))


def esc(s):
    return html.escape(str(s))


def clip(v, n=230):
    """shorten long strings inside a JSON sample so the page stays readable"""
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + " ... [+%d chars]" % (len(v) - n)
    if isinstance(v, list):
        return [clip(x, n) for x in v]
    if isinstance(v, dict):
        return {k: clip(x, n) for k, x in v.items()}
    return v


def pj(obj, indent=2):
    return esc(json.dumps(clip(obj), indent=indent, ensure_ascii=False))


# ------------------------------------------------------------------ real inputs
system_prompt = read("prompts", "analyst-system.md")
late_prompt = read("prompts", "late-evidence.md")
pack = load("data", SLUG, "evidence-pack.json")["events"]
rule_hits = [e for e in pack if e["kind"] == "rule_hit"]
context = [e for e in pack if e["kind"] != "rule_hit"]
sample_rule = rule_hits[0]
sample_ctx = next(e for e in context if e["source"] == "SONAR")
input_chars = len(json.dumps(rule_hits)) + len(json.dumps(context))
late_event = load("data", SLUG, "late-event-normalised.json")

cache_path = os.path.join(ROOT, "server", "cache", SLUG + ".diagnosis.json")
if os.path.exists(cache_path):
    cached = load("server", "cache", SLUG + ".diagnosis.json")
    out = cached["payload"]
    meta = out.get("_meta", {})
else:
    out, meta = {}, {}

bundle = load("app", "src", "data", SLUG, "bundle.json")
bundle_keys = list(bundle.keys())
mode_by_slug = {}
for s in sorted(os.listdir(os.path.join(ROOT, "app", "src", "data"))):
    bp = os.path.join(ROOT, "app", "src", "data", s, "bundle.json")
    if os.path.exists(bp):
        with open(bp, encoding="utf-8") as f:
            mode_by_slug[s] = json.load(f)["meta"]["mode"]

# a trimmed model answer for the "what comes back" block
answer_sample = {}
if out:
    h0 = out["hypotheses"][0]
    answer_sample = {
        "incident_summary": out["incident_summary"],
        "timeline": out["timeline"][:2] + ["... more items, rebuilt by the server from the pack ..."],
        "hypotheses": [dict(h0, supports=h0["supports"][:2] + ["..."], contradicts=h0["contradicts"][:1] + ["..."]), "... 1 to 3 more ..."],
        "ruled_out": out["ruled_out"][:1] + ["..."],
        "checks": out["checks"][:1] + ["..."],
        "blast_radius": out["blast_radius"],
        "recovery": dict(out["recovery"]),
        "post_incident_note": out["post_incident_note"],
        "_meta": meta,
    }

req_browser = {"slug": SLUG, "events": [sample_rule, sample_ctx, "... %d more events (the evidence pack) ..." % (len(pack) - 2)]}
input_text = (
    "rule_hits (already fired by existing rules/monitors -- %d events):\n" % len(rule_hits)
    + json.dumps(clip([sample_rule], 300)[0:1] + ["..."], ensure_ascii=False)
    + "\n\ncontext (records retrieved around the rule hits -- %d events):\n" % len(context)
    + json.dumps(clip([sample_ctx], 300)[0:1] + ["..."], ensure_ascii=False)
)
req_model = {
    "model": "gpt-5",
    "instructions": "<the full text of prompts/analyst-system.md -- see section 4>",
    "input": "<the text shown in the next block>",
    "text": {"verbosity": "medium"},
    "reasoning": {"effort": "low"},
}
late_body = {
    "slug": SLUG,
    "events": ["... same %d pack events ..." % len(pack)],
    "lateEvent": late_event,
    "previousDiagnosis": "<the diagnosis currently on screen, without _meta and diff>",
}

modes_rows = "".join(
    "<tr><td class='mono'>%s</td><td>%s</td></tr>"
    % (esc(s), "<span class='chip llm'>AI-live</span>" if m == "ai-live" else "<span class='chip human'>Stored (hand-written)</span>")
    for s, m in mode_by_slug.items()
)

TEMPLATE = open(os.path.join(ROOT, "scripts", "architecture_template.html"), encoding="utf-8").read()

subs = {
    "@@DATE@@": date.today().isoformat(),
    "@@SLUG@@": SLUG,
    "@@NPACK@@": str(len(pack)),
    "@@NRULE@@": str(len(rule_hits)),
    "@@NCTX@@": str(len(context)),
    "@@INCHARS@@": "{:,}".format(input_chars),
    "@@BUNDLEKEYS@@": esc(", ".join(bundle_keys)),
    "@@REQ_BROWSER@@": pj(req_browser),
    "@@REQ_MODEL@@": pj(req_model),
    "@@INPUT_TEXT@@": esc(input_text),
    "@@ANSWER@@": pj(answer_sample) if answer_sample else esc("(run the S3 scenario once to populate server/cache, then rebuild this page)"),
    "@@LATE_BODY@@": pj(late_body),
    "@@SYSTEM_PROMPT@@": esc(system_prompt),
    "@@LATE_PROMPT@@": esc(late_prompt),
    "@@MODES@@": modes_rows,
    "@@LATENCY@@": esc(str(meta.get("latencyMs", "about 70000")) + (" ms" if meta.get("latencyMs") else " ms (typical)")),
}
page = TEMPLATE
for k, v in subs.items():
    page = page.replace(k, v)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(page)
print("wrote", OUT, "(%d KB)" % (os.path.getsize(OUT) // 1024))
