#!/usr/bin/env python3
"""Heuristic picker: task description -> model tier, effort, delegation advice.

A sanity check for the delegation rubric, not an oracle. Rule of thumb inside:
the highest tier that matches wins, because under-powering is the costly error.

Caller flags carry the answers to the four questions (reversible? checkable?
how wide? what does a wrong answer cost?) and override the keywords:
    --read-only      action only reads: ignore destructive/security keywords
    --reversible     easily undone (e.g. a cache that rebuilds): ignore destructive keywords
    --irreversible   cannot be undone: main agent, top tier, confirm first
    --mechanical     bounded and checkable (grep, convert, tidy): small tier
    --routine        ordinary bounded engineering: mid tier, design/"why" keywords ignored
    --unverifiable   no cheap way to check the answer: top tier
    --high-stakes    a wrong answer is costly (security, money, shipping): top tier

Usage:
    python pick_model.py "Run the test suite and report failures"
    python pick_model.py "Read these files and report timeouts" --files 9
    python pick_model.py "Is this safe to ship?" --high-stakes --title "ship check"
"""
import argparse
import json
import re

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}

# Irreversible or destructive: never delegate to a cheap subagent.
IRREVERSIBLE = [
    r"\bdelete\b", r"\brm -rf\b", r"\bforce[- ]push\b", r"\boverwrite\b", r"\btruncate\b",
    r"\bdrops?\b.*\b(table|database|column)\b", r"\bmigrat(e|ion|ions)\b", r"\bproduction\b",
    r"\bprod\b", r"\bdeploy(s|ed|ment)?\b", r"\broll ?back\b", r"\brotate\b.*\b(keys?|secrets?)\b",
    r"\brevoke\b", r"\bwipe\b", r"\bpurge\b",
]
# Security-sensitive: top tier, high effort.
SECURITY = [
    r"\bpasswords?\b", r"\btokens?\b", r"\bsecrets?\b", r"\bcredentials?\b", r"\bauth(entication|orization)?\b",
    r"\bencrypt\w*", r"\binjection\b", r"\bsanitiz\w*", r"\bapi keys?\b",
]
# Unverifiable judgment, design, cross-cutting reasoning: top tier.
OPUS = [
    r"\bdesign\b", r"\barchitect\w*", r"\bschema\b", r"\btrade-?offs?\b", r"\boverfit\w*",
    r"\blookahead\b", r"\bleakage\b", r"\broot cause\b", r"\bdecid(e|ing)\b", r"\bdecision\b",
    r"\bsynthesi[sz]e\b", r"\bcompeting\b", r"\bwhy (does|is|do|are)\b",
    r"\bplan\b.*\brefactor\b|\brefactor\b.*\bplan\b",
    r"\bspans?\b", r"\bbypass\w*", r"\bhooks?\b.*\b(review|audit|guard|security)\b|\b(review|audit)\b.*\bhooks?\b", r"\bacross (the )?\w+( \w+)? (modules|files|services|layers|components)\b",
    r"\b(multiple|several) (modules|services|files)\b",
]
# Routine engineering with some judgment: mid tier.
SONNET = [
    r"\bimplement\w*", r"\bexplain\b", r"\bdebug\w*", r"\bbugs?\b", r"\btraceback\b",
    r"\bfix (the |this )?(failing |broken )?(test|bug|crash|error)", r"\bfailing test",
    r"\breview (this |the )?(diff|pull request|pr|code|change)", r"\bcontradict\w*",
    r"\bcompare\b", r"\bwrite (a |an )?(small |simple )?(function|utility|script|class|test|handler)",
    r"\bunit tests?\b", r"\bwith tests\b", r"\bfind the cause\b",
]
# Mechanical, checkable work: small tier.
HAIKU = [
    r"\bgrep\b", r"\blist\b", r"\bcount\b", r"\bextract\b", r"\bfind where\b", r"\blocate\b",
    r"\bsummari[sz]e\b", r"\brun (the )?(tests?|test suite|backtest|linter|script|build)\b",
    r"\bgit (status|log|diff)\b", r"\bls\b", r"\binstall\b", r"\bformat\b", r"\blint\w*",
    r"\brename\b", r"\bfetch\b", r"\blook up\b", r"\bread\b.*\band report\b", r"\breturn the\b",
    r"\bcheck whether\b", r"\breport (the|which)\b", r"\bbroken links?\b", r"\bcheck\.sh\b",
]
FAN_OUT_MIN = 8  # below this, reading in the main thread costs less than spawning


def _hits(patterns, text):
    return [p for p in patterns if re.search(p, text)]


def count_files(text, provided=0):
    n = provided
    for m in re.finditer(r"\b(\d+|" + "|".join(WORDS) + r")\b[\w\s]{0,15}?\b(files|modules|documents|configs)\b", text):
        tok = m.group(1)
        n = max(n, int(tok) if tok.isdigit() else WORDS[tok])
    return n


FLAGS = ("read_only", "reversible", "irreversible", "mechanical", "routine", "unverifiable", "high_stakes")


def announcement(title, model, effort):
    """The line every subagent begins its final report with. It states what was assigned: a
    subagent cannot reliably know which model it really runs on."""
    return f"Hi, subagent taking task '{title}' with assigned model {model} at {effort} effort."


def default_title(task):
    t = task.strip().rstrip(".?!")
    return t if len(t) <= 60 else t[:57].rstrip() + "..."


def pick(task, file_count=0, flags=(), title=None):
    flags = set(flags)
    t = task.lower()
    n_files = count_files(t, file_count)
    irr, sec = _hits(IRREVERSIBLE, t), _hits(SECURITY, t)
    top, mid, low = _hits(OPUS, t), _hits(SONNET, t), _hits(HAIKU, t)
    reasons = []

    if "read_only" in flags:
        irr, sec = [], []
        reasons.append("flag read-only: destructive/security keywords ignored")
    if "reversible" in flags:
        irr = []
        reasons.append("flag reversible: destructive keywords ignored")
    if "routine" in flags:
        top = []
        reasons.append("flag routine: design/why keywords ignored, mid tier")

    if "irreversible" in flags or irr:
        model, effort = "opus", "high"
        reasons.append("irreversible or destructive action")
        irr = irr or ["flag"]
    elif sec:
        model, effort = "opus", "high"
        reasons.append("security-sensitive")
    elif flags & {"unverifiable", "high_stakes"}:
        model, effort = "opus", "high"
        reasons.append("flagged " + " and ".join(sorted(flags & {"unverifiable", "high_stakes"})).replace("_", "-"))
    elif top:
        model, effort = "opus", "high"
        reasons.append("design or unverifiable judgment")
    elif "mechanical" in flags:
        model, effort = "haiku", "low"
        reasons.append("flag mechanical: bounded and checkable")
    elif mid or "routine" in flags:
        model, effort = "sonnet", "medium"
        reasons.append("routine engineering with some judgment")
        if re.search(r"\b(small|simple|tiny|trivial|quick)\b", t):
            effort = "low"
            reasons.append("small scope")
        if n_files >= 10:
            effort = "high"
            reasons.append(f"wide scope ({n_files} files)")
    elif low:
        model, effort = "haiku", "low"
        reasons.append("mechanical, checkable work")
    else:
        model, effort = "sonnet", "medium"
        reasons.append("no clear signal: default to mid-tier (or ask one clarifying question)")

    # Destructive work and decisions about findings stay with the main agent.
    main_only = bool(irr or sec or re.search(r"\bsynthesi[sz]e\b|\bdecision\b", t))
    split = bool(low and (top or irr))
    fan_out = model == "haiku" and n_files >= FAN_OUT_MIN
    if split:
        reasons.append("mixed task: delegate the gathering to haiku, keep the decision")
    if fan_out:
        reasons.append(f"{n_files} independent reads: fan out to parallel subagents")

    title = title or default_title(task)
    return {
        "model": model,
        "effort": effort,
        "delegate": "main" if main_only else "subagent",
        "split": split,
        "fan_out": fan_out,
        "announce": None if main_only else announcement(title, model, effort),
        "reasons": reasons,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--files", type=int, default=0, help="number of files in scope")
    ap.add_argument("--title", help="short task name used in the announcement line")
    for f in FLAGS:
        ap.add_argument("--" + f.replace("_", "-"), action="store_true")
    args = ap.parse_args()
    chosen = [f for f in FLAGS if getattr(args, f)]
    print(json.dumps(pick(args.task, args.files, chosen, args.title), indent=2))
