#!/usr/bin/env python3
"""One-off script: adds Tailwind `dark:` variants to the Screen 2 ("With AI")
component tree so the existing dark look becomes the dark:-prefixed variant
and a new light palette becomes the unprefixed default. Screen 1 (alert
floor), BridgeTimer and LayerStack are intentionally left untouched -- they
keep their current fixed dark styling regardless of theme (see commit
message / conversation for the reasoning).

Run once, by hand, then delete or ignore -- not part of the app's runtime.
"""
import re

APP_SRC = "C:/Users/GenAIHYDRPUSR18/Desktop/gaf_usecase/loreal/app/src"

FILES = [
    f"{APP_SRC}/App.tsx",
    f"{APP_SRC}/screens/AiView.tsx",
    f"{APP_SRC}/components/PanelShell.tsx",
    f"{APP_SRC}/components/EvidenceColumns.tsx",
    f"{APP_SRC}/components/ApprovalDialog.tsx",
    f"{APP_SRC}/components/Badges.tsx",
    f"{APP_SRC}/components/ScenarioSwitcher.tsx",
    f"{APP_SRC}/panels/BlastRadius.tsx",
    f"{APP_SRC}/panels/Checks.tsx",
    f"{APP_SRC}/panels/Hypotheses.tsx",
    f"{APP_SRC}/panels/IncidentHeader.tsx",
    f"{APP_SRC}/panels/Recovery.tsx",
    f"{APP_SRC}/panels/RuledOut.tsx",
    f"{APP_SRC}/panels/Timeline.tsx",
]

# old (current, dark-only) token -> new light-mode token.
# Each entry becomes "<light> dark:<old>" in the output.
MAP = {
    # structural surfaces
    "bg-slate-950": "bg-slate-100",
    "bg-slate-950/60": "bg-slate-200/60",
    "bg-slate-900/70": "bg-white",
    "bg-slate-900/60": "bg-white",
    "bg-slate-900/50": "bg-slate-100",
    "bg-slate-900/40": "bg-slate-100",
    "bg-slate-900": "bg-white",
    "bg-slate-800/60": "bg-slate-100",
    "bg-slate-800/40": "bg-white",
    "bg-slate-800": "bg-slate-100",
    "bg-slate-700/60": "bg-slate-200",
    "bg-slate-700": "bg-slate-200",
    "bg-slate-500/15": "bg-slate-200",
    "border-slate-700/60": "border-slate-300",
    "border-slate-700/50": "border-slate-200",
    "border-slate-700": "border-slate-300",
    "border-slate-600/60": "border-slate-300",
    "border-slate-600/50": "border-slate-200",
    "border-slate-600": "border-slate-300",
    "border-slate-500/40": "border-slate-300",
    "decoration-slate-600": "decoration-slate-400",
    # text
    "text-white": "text-slate-900",
    "text-slate-100": "text-slate-900",
    "text-slate-200": "text-slate-800",
    "text-slate-300": "text-slate-600",
    "text-slate-400": "text-slate-500",
    "text-slate-600": "text-slate-500",
    # emerald
    "bg-emerald-500/5": "bg-emerald-50",
    "bg-emerald-500/15": "bg-emerald-100",
    "bg-emerald-500/20": "bg-emerald-100",
    "border-emerald-500/40": "border-emerald-300",
    "border-emerald-500/30": "border-emerald-300",
    "border-emerald-500/20": "border-emerald-300",
    "text-emerald-500": "text-emerald-600",
    "text-emerald-400/80": "text-emerald-600/80",
    "text-emerald-400": "text-emerald-600",
    "text-emerald-300": "text-emerald-700",
    "text-emerald-200": "text-emerald-800",
    "text-emerald-100/90": "text-emerald-900/90",
    # amber
    "hover:bg-amber-500/20": "hover:bg-amber-100",
    "bg-amber-500/20": "bg-amber-100",
    "bg-amber-500/15": "bg-amber-100",
    "bg-amber-500/10": "bg-amber-50",
    "bg-amber-500/5": "bg-amber-50",
    "border-amber-500/40": "border-amber-300",
    "border-amber-500/30": "border-amber-300",
    "text-amber-400": "text-amber-600",
    "text-amber-300": "text-amber-700",
    "text-amber-200/90": "text-amber-800/90",
    # rose
    "bg-rose-500/20": "bg-rose-100",
    "bg-rose-500/15": "bg-rose-100",
    "bg-rose-500/5": "bg-rose-50",
    "border-rose-500/40": "border-rose-300",
    "border-rose-500/20": "border-rose-300",
    "text-rose-400/80": "text-rose-600/80",
    "text-rose-400": "text-rose-600",
    "text-rose-300": "text-rose-700",
    # sky
    "bg-sky-500/20": "bg-sky-100",
    "bg-sky-500/10": "bg-sky-100",
    "border-sky-500/40": "border-sky-300",
    "border-sky-500": "border-sky-400",
    "focus:border-sky-500": "focus:border-sky-500",
    "text-sky-400/80": "text-sky-600/80",
    "text-sky-400/70": "text-sky-600/70",
    "text-sky-300": "text-sky-700",
    # indigo
    "bg-indigo-500/10": "bg-indigo-100",
    "border-indigo-400/50": "border-indigo-300",
    "border-indigo-400/40": "border-indigo-300",
    "border-indigo-400/25": "border-indigo-300",
    "border-indigo-400/20": "border-indigo-300",
    "text-indigo-300": "text-indigo-700",
    "text-indigo-200": "text-indigo-800",
    # source badges (Timeline)
    "border-purple-500/40": "border-purple-300",
    "text-purple-300": "text-purple-700",
    "border-orange-500/40": "border-orange-300",
    "text-orange-300": "text-orange-700",
    "border-lime-500/40": "border-lime-300",
    "text-lime-300": "text-lime-700",
    "border-cyan-500/40": "border-cyan-300",
    "text-cyan-300": "text-cyan-700",
    # interactive states
    "hover:bg-slate-800": "hover:bg-slate-200",
    "hover:text-slate-200": "hover:text-slate-900",
    "hover:text-slate-300": "hover:text-slate-800",
    "disabled:bg-slate-700": "disabled:bg-slate-200",
    "disabled:text-slate-500": "disabled:text-slate-400",
    "border-amber-700/50": "border-amber-300",
    "bg-amber-900/10": "bg-amber-50",
    "text-amber-400": "text-amber-600",
}


def process(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()

    placeholders = {}
    for i, (old, new) in enumerate(sorted(MAP.items(), key=lambda kv: -len(kv[0]))):
        ph = f"@@LT{i}@@"
        pattern = re.compile(r"(?<![-\w:])" + re.escape(old) + r"(?![-\w/])")
        if old == new:
            final = old  # e.g. focus:border-sky-500 -- same in both themes
        else:
            final = f"{new} dark:{old}"
        n = len(pattern.findall(text))
        if n:
            text = pattern.sub(ph, text)
            placeholders[ph] = final

    for ph, final in placeholders.items():
        text = text.replace(ph, final)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    return sum(1 for ph in placeholders)


if __name__ == "__main__":
    for path in FILES:
        n = process(path)
        print(f"{path}: {n} token types replaced")
