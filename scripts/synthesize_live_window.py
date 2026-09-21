#!/usr/bin/env python3
"""Builds a SYNTHETIC copy of the Live-mode window: same shape, same timing, same
relationships between incidents, but every production identifier is replaced.

Input  (read-only): server/live-data/june-window.json   (redacted real window)
Output (new file) : server/live-data/june-window.synthetic.json
Salt   (new file) : server/live-data/.synthetic-salt      (random; makes the mapping one-way)

Replaced: exchange / message ids, flow and interface names, source and destination
system names, Kafka topics, processing groups, app and host names, IPs, e-mail
addresses, company URLs, the company name and ticket numbers.
Kept: region and environment codes, protocol words (ESB, MFT, API, IDOC, ...),
short numeric suffixes, priority/state/zone, team names and all timing.

The mapping is consistent (the same production name always becomes the same synthetic
name), so patterns such as "the same failure on every IDoc-out flow" survive.
Nothing here modifies the real window, the extractor or the server.
"""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sys

_bad = [c for c in open(__file__, encoding="utf-8").read() if ord(c) < 32 and c not in "\n\r\t"]
if _bad:
    sys.exit(f"script contains stray control characters: {sorted(set(map(hex, map(ord, _bad))))}")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(REPO_ROOT, "server", "live-data")
SRC = os.path.join(DIR, "june-window.json")
OUT = os.path.join(DIR, "june-window.synthetic.json")
SALT_PATH = os.path.join(DIR, ".synthetic-salt")

if os.path.abspath(OUT) == os.path.abspath(SRC):
    sys.exit("refusing to overwrite the real window")

if os.path.exists(SALT_PATH):
    SALT = open(SALT_PATH, "rb").read()
else:
    SALT = secrets.token_bytes(32)
    with open(SALT_PATH, "wb") as f:
        f.write(SALT)

# words that stay as they are: platform vocabulary, regions, environments, generic incident language
KEEP = set("""
euro emea apac amer glbl global na latam prd ppd qua dev prod test
esb mft api sap idoc rfc ecc azure hip sonar ops kafka confluent workato apigee splunk servicenow sfg elk
kibana consumer lag alert flow flows failure fail failed report critical daily health chk check in out v1 v2 v3
split common batch master process int fwk message trace default app module publication inbound outbound
incident error warning exception timeout major minor normal priority pending resolved closed open running
medium high low active unknown success inprogress replayed status service host server node pod cluster
default idocs group topic queue file transfer sender receiver partner profile config document sending
the and for with from to of is are not no yes true false null none
http https tls ssl utf json xml sql csv pdf jvm gc oom heap sqs
linux windows redhat ubuntu disk memory usage swap cpu load mount data logs log tmp opt var
sonarops cess local remote primary secondary backup restore restart timeout retry queue lag
hipmon control kfk apg snr spl wkt hrly crit workato apigee servicenow
""".split())

SYL_C = "bdfgklmnprstvz"
SYL_V = "aeiou"
_word_seen = {}


def _digest(kind, s):
    return hmac.new(SALT, f"{kind}|{s.lower()}".encode(), hashlib.sha256).digest()


def fake_word(orig):
    key = orig.lower()
    if key in _word_seen:
        w = _word_seen[key]
    else:
        d = _digest("w", key)
        n = 3
        while True:
            w = "".join(SYL_C[d[i * 2] % len(SYL_C)] + SYL_V[d[i * 2 + 1] % len(SYL_V)] for i in range(n))
            if w not in _word_seen.values() and w not in KEEP:
                break
            n += 1
            d = hashlib.sha256(d).digest()
        _word_seen[key] = w
    if orig.isupper():
        return w.upper()
    if orig.islower():
        return w
    return w.capitalize()


_digits_seen = {}   # original digit string -> fake (one-to-one, so ids never collide)
_digits_used = set()


def fake_digits(orig):
    if orig in _digits_seen:
        return _digits_seen[orig]
    attempt = 0
    while True:
        d = _digest("d", orig if attempt == 0 else f"{orig}#{attempt}")
        out = "".join(str(b % 10) for b in d[: len(orig)])
        while len(out) < len(orig):
            d = hashlib.sha256(d).digest()
            out += "".join(str(b % 10) for b in d)
        out = out[: len(orig)]
        if out.startswith("0") and not orig.startswith("0"):
            out = "1" + out[1:]
        if (len(orig), out) not in _digits_used and out != orig:
            break
        attempt += 1
    _digits_used.add((len(orig), out))
    _digits_seen[orig] = out
    return out


def fake_hex(orig):
    d = _digest("h", orig)
    while len(d) * 2 < len(orig):
        d += hashlib.sha256(d).digest()
    h = d.hex()
    out = []
    for i, ch in enumerate(orig):
        out.append(ch if ch == "-" else (h[i].upper() if ch.isupper() else h[i]))
    return "".join(out)


originals = set()       # parts and tokens replaced (informational)
full_originals = set()  # whole identifiers, ids, e-mails, urls, ips replaced (leak check)
produced = set()        # whole tokens we generated (an original may coincide with one of these)


def map_part(part):
    """Map one identifier part: alpha runs and digit runs handled separately."""
    def run(m):
        t = m.group(0)
        if t.isdigit():
            if len(t) <= 3:
                return t
            originals.add(t)
            return fake_digits(t)
        if t.lower() in KEEP or len(t) <= 2:
            return t
        originals.add(t.lower())
        return fake_word(t)
    return re.sub(r"[A-Za-z]+|\d+", run, part)


def map_ident(tok):
    if re.match(r"(?:java|javax|com|org|sun|jdk)\.", tok):  # vendor / library package names
        return tok
    parts = re.split(r"([_.\-])", tok)
    return "".join(p if p in "_.-" else map_part(p) for p in parts)


def worth_mapping(tok):
    seps = len(re.findall(r"[_.\-]", tok))
    return bool(re.search(r"[A-Z]{2,}", tok) or re.search(r"\d", tok) or seps >= 2)


def map_url(u):
    u = u.split("?")[0].split("#")[0]
    m = re.match(r"https?://[^/]+(/.*)?$", u)
    path = (m.group(1) or "") if m else ""
    segs = [s if s.lower() in KEEP else map_part(s) for s in path.split("/")]
    originals.add(u.split("/")[2].lower() if u.count("/") >= 2 else u)
    return "https://svc.example.invalid" + "/".join(segs)


def map_email(e):
    originals.add(e.lower())
    return f"user-{fake_word(e.split('@')[0])}@example.invalid"


def map_ip(ip):
    if ip in ("0.0.0.0", "127.0.0.1"):
        return ip
    d = _digest("ip", ip)
    originals.add(ip)
    return f"10.{d[0] % 250 + 1}.{d[1] % 250 + 1}.{d[2] % 250 + 1}"


# extra internal names to replace everywhere (kept in a private, git-excluded file, never in this script)
_TERMS_PATH = os.path.join(REPO_ROOT, "synthetic-data", ".extra-terms.txt")
EXTRA_TERMS = []
if os.path.exists(_TERMS_PATH):
    EXTRA_TERMS = sorted({ln.strip().lower() for ln in open(_TERMS_PATH, encoding="utf-8").read().splitlines()
                          if ln.strip() and not ln.lstrip().startswith("#")}, key=len, reverse=True)
# a term counts when not glued to a letter on the left and not followed by a lowercase letter
# (so "non-<term>" and "<Term>Invoke" are replaced, but longer lowercase words that merely start with it are not)
_TERM_CORE = "|".join(re.escape(t) for t in EXTRA_TERMS)
_TERM_PAT = r"(?<![A-Za-z])(?i:(?:" + _TERM_CORE + r"))(?-i:(?![a-z]))"
TERM_RE = re.compile(_TERM_PAT) if EXTRA_TERMS else None
_TERM_ALT = (r"|(?P<term>" + _TERM_PAT + r")") if EXTRA_TERMS else ""


def replace_terms(text):
    """Replace configured internal names wherever they occur inside a token."""
    if TERM_RE is None:
        return text

    def one(m):
        new = fake_word(m.group(0))
        full_originals.add(m.group(0).lower())
        produced.add(new.lower())
        return new
    return TERM_RE.sub(one, text)
_SAPID_ALT = r"|(?P<sapid>\bSAP[A-Z0-9]{2,5}\b)"  # standalone SAP system ids (SAPXX, SAPXXX)

MASTER = re.compile(
    r"(?P<brand>\bL['’]?Or[ée]al\b)"
    r"|(?P<url>https?://[^\s\"<>)\]]+)"
    r"|(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<ip>\b\d{1,3}(?:\.\d{1,3}){3}\b)"
    r"|(?P<longid>\b(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{20,}|\d{9,})\b)"
    r"|(?P<inc>\bINC\d{6,}\b)"
    + _TERM_ALT + _SAPID_ALT +
    r"|(?P<alnum>\b[A-Za-z]{2,}\d{2,}[A-Za-z0-9]*\b)"
    r"|(?P<ident>\b[A-Za-z][A-Za-z0-9]*(?:[_.\-][A-Za-z0-9]+)+\b)"
    r"|(?P<caps>\b[A-Z][A-Z0-9]{6,}\b)",
    re.I,
)


NAME = r"[A-ZÀ-Ý][A-Za-zà-ÿ'’\-]+"
GENERIC_AFTER_GREETING = {"team", "all", "everyone", "support", "helpdesk", "sir", "madam", "colleagues", "hip",
                          "there", "both", "again", "und", "and", "l1", "l2", "l3", "hello", "hi", "dear", "guys", "folks"}
CLOSING = re.compile(
    r"(?P<lead>\b(?i:(?:viele|liebe|liebste|beste|sch[öo]ne|freundliche|herzliche)\s+gr[üu](?:ß|ss)e(?:\s+aus\s+[A-Za-zÀ-ÿ\-]+)?|"
    r"mit\s+(?:freundlichen|besten)\s+gr[üu](?:ß|ss)en|gru(?:ß|ss)|(?:with\s+)?(?:best|kind|warm|many)\s+regards|"
    r"regards|thanks\s+and\s+regards|thank\s+you|thanks|cheers|sincerely|cordialement|saludos|atentamente|grazie|merci|BR)"
    r"[,:\s]+)(?P<name>(?:" + NAME + r")(?:\s+" + NAME + r"){0,3})")
# subjects that start "SURNAME Firstname - ..." (a person named in the title)
SUBJECT_PERSON = re.compile(r"^(?P<first>[A-ZÄÖÜ]{3,})(?P<rest>(?:\s+[A-ZÄÖÜ][A-Za-zà-ÿ'’\-]+){1,2})(?P<dash>\s+-\s)")
NOT_A_PERSON_LEAD = {"hipmon", "auto", "sonar", "sonarops", "info", "warning", "critical", "alert", "incident", "global"}
PHONE_CTX = re.compile(r"(?i:\b(?P<lead>tel|telefon|phone|mobil|mobile|fax|handy|tlf)\b[.:\s]*)(?P<num>\+?[\d][\d\s/\-\(\)\.]{5,24}\d)")
PHONE_RAW = re.compile(r"(?<![\d\-:.])(?:\+\d{1,3}[\s\-]?)?\(?0\d{2,5}\)?[\s/\-]\d{4,}(?:[\s\-]\d{1,4})?(?![\d:])")
# "Lt. E-Mail von Katja ...", "reported by ...", "contact: ..."
ATTRIBUTION = re.compile(
    r"(?P<lead>\b(?:E-?Mail von|Mail von|e-?mail from|mail from|reported by|raised by|requested by|sent by|"
    r"created by|contact person|Ansprechpartner(?:in)?|Kontakt)[:\s]+)(?P<name>" + NAME + r"(?:\s+" + NAME + r"){0,2})")
# mail header lines: "Von: SURNAME Firstname <...>", "From: Jane Doe <...>"
HEADER = re.compile(
    r"(?P<lead>\b(?:Von|From|An|To|Cc|Bcc|Absender|Empf[äa]nger|Sender)\s*:\s*)"
    r"(?P<name>[A-Za-zÀ-ÿ'’\-,\. ]{2,60}?)(?=\s*(?:<|Gesendet|Sent|Betreff|Subject|Cc:|Datum|Date|An:|To:|$))")
GREETING = re.compile(
    r"(?P<lead>\b(?:Hi|Hello|Hallo|Dear|Hola|Bonjour|Ciao|Hey)[\s,]+)(?P<name>" + NAME + r"(?:\s+" + NAME + r")?)")


def scrub_names(text):
    text = PHONE_CTX.sub(lambda m: m.group("lead") + "[phone]", text)
    text = PHONE_RAW.sub("[phone]", text)
    m0 = SUBJECT_PERSON.match(text)
    if m0 and m0.group("first").lower() not in NOT_A_PERSON_LEAD and m0.group("rest").split()[0].lower() not in KEEP:
        text = "[name]" + m0.group("dash") + text[m0.end():]
    text = CLOSING.sub(lambda m: m.group("lead") + "[name]", text)
    text = ATTRIBUTION.sub(lambda m: m.group("lead") + "[name]", text)
    text = HEADER.sub(lambda m: m.group("lead") + "[name]", text)

    def greet(m):
        first = m.group("name").split()[0].lower()
        return m.group(0) if first in GENERIC_AFTER_GREETING else m.group("lead") + "[name]"
    return GREETING.sub(greet, text)


def scrub(text):
    if not text:
        return text
    text = scrub_names(text)

    def sub(m):
        g = m.lastgroup
        s = m.group(0)
        if g == "brand":
            return "Acme"
        if g == "url":
            full_originals.add(s.split("?")[0].lower())
            return map_url(s)
        if g == "email":
            full_originals.add(s.lower())
            return map_email(s)
        if g == "ip":
            full_originals.add(s)
            return map_ip(s)
        if g == "longid":
            full_originals.add(s.lower())
            originals.add(s.lower())
            return fake_hex(s) if re.search(r"[a-fA-F\-]", s) else fake_digits(s)
        if g == "inc":
            full_originals.add(s.lower())
            originals.add(s.lower())
            return "INC" + fake_digits(s[3:])
        if g == "ident":
            if not worth_mapping(s):
                return replace_terms(s)
            new = replace_terms(map_ident(s))
            if new != s:
                full_originals.add(s.lower())
                produced.add(new.lower())
            return new
        if g == "term":
            return replace_terms(s)
        if g == "sapid":
            if not s.isupper() or s.lower() in KEEP:
                return s
            new = map_part(s)
            full_originals.add(s.lower())
            produced.add(new.lower())
            return new
        if g == "alnum":
            new = map_part(s)
            if new != s:
                full_originals.add(s.lower())
                produced.add(new.lower())
            return new
        if g == "caps":
            if s.lower() in KEEP or not s.isupper():
                return s
            return map_part(s)
        return s

    return MASTER.sub(sub, text)


def plain(html_text):
    if not html_text:
        return html_text
    t = re.sub(r"<br\s*/?>", " ", html_text, flags=re.I)
    t = re.sub(r"</(td|tr|p|div)>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


TEXT_FIELDS = ["subject", "details", "close_notes", "configuration_item", "service",
               "classification_keyword", "sub_classification"]
INC_FIELDS = ["number", "parent_incident"]


def main():
    win = json.load(open(SRC, encoding="utf-8"))
    out_incidents = []
    for inc in win["incidents"]:
        r = dict(inc)
        for f in TEXT_FIELDS:
            v = inc.get(f)
            if isinstance(v, str):
                r[f] = scrub(plain(v) if f in ("details", "close_notes") else v)
        for f in INC_FIELDS:
            v = inc.get(f)
            if isinstance(v, str):
                r[f] = scrub(v)
        out_incidents.append(r)

    out = dict(win)
    out.update({
        "source": "Synthetic, pseudonymised replay of a real incident window: production identifiers replaced",
        "synthetic": True,
        "incidents": out_incidents,
    })
    blob = json.dumps(out, ensure_ascii=False, indent=2)

    # leak check: nothing we replaced may still appear, and no obvious secrets patterns remain
    low = blob.lower()
    leaks = sorted(o for o in full_originals if len(o) >= 4 and o in low and o != "0.0.0.0" and o not in produced and o != "control-m")
    checks = {
        "whole production identifiers still present": leaks[:10] or "none",
        "'loreal' present": "loreal" in low,
        "'service-now' present": "service-now" in low,
        "'@' outside example.invalid": [m for m in re.findall(r"[\w.+-]+@[\w.-]+", blob) if not m.endswith("example.invalid")] or "none",
        "person names remaining after sign-off/greeting scrub (review)": sorted(set(re.findall(r"(?<![\w\[])[A-ZÀ-Ý][a-zà-ÿ]{2,} [A-ZÀ-Ý][a-zà-ÿ]{2,}(?![\w])", re.sub(r"[A-Z][a-z]+ (?:Team|Support|Group|Flow|Report|Error|Message|Failure|Failed)", "", blob))))[:40],
        "10.x IPs only": sorted(set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", blob)))[:5],
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(blob + "\n")
    print(f"Wrote {len(out_incidents)} synthetic incidents to {OUT}")
    print(f"Distinct production identifiers replaced: {len(originals)} (whole identifiers/ids: {len(full_originals)})")
    for k, v in checks.items():
        print(f"  check - {k}: {v}")
    return 0 if not leaks else 1


if __name__ == "__main__":
    sys.exit(main())
