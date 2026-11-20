#!/usr/bin/env python3
"""Score scripts/pick_model.py against labeled cases.

Usage: python tests/run_eval.py [--no-flags] [cases.jsonl ...]   (default: cases.jsonl and holdout.jsonl)
--no-flags ignores each case's "flags" field, to show the keyword-only baseline.
Under-powering (picking a lower tier or effort than labeled) is reported separately,
because it is the expensive mistake.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from pick_model import pick  # noqa: E402

MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}


def run(path, use_flags=True):
    cases = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    tot = {"model": 0, "effort": 0, "delegate": 0, "delegate_n": 0, "split": 0, "split_n": 0, "fan": 0, "fan_n": 0}
    under, misses = [], []
    for c in cases:
        r = pick(c["task"], len(c.get("files", [])), c.get("flags", []) if use_flags else [])
        ok_m = r["model"] == c["model"]
        ok_e = r["effort"] in c["effort"]
        tot["model"] += ok_m
        tot["effort"] += ok_e
        problems = []
        want_line = f"Hi, subagent taking task '"
        if r["delegate"] == "main":
            if r["announce"] is not None:
                problems.append("announcement given for a main-agent task")
        elif not (r["announce"].startswith(want_line) and "assigned model " + r["model"] in r["announce"] and r["effort"] in r["announce"]):
            problems.append("announcement line malformed")
        if not ok_m:
            problems.append(f"model {r['model']} (want {c['model']})")
        if not ok_e:
            problems.append(f"effort {r['effort']} (want {'/'.join(c['effort'])})")
        if MODEL_RANK[r["model"]] < MODEL_RANK[c["model"]] or EFFORT_RANK[r["effort"]] < min(EFFORT_RANK[e] for e in c["effort"]):
            under.append(c["id"])
        for key, field, got in (("delegate", "delegate", r["delegate"]), ("split", "split", r["split"]), ("fan_out", "fan", r["fan_out"])):
            if key in c:
                tot[field + "_n"] += 1
                if got == c[key]:
                    tot[field] += 1
                else:
                    problems.append(f"{key} {got} (want {c[key]})")
        if problems:
            misses.append((c["id"], "; ".join(problems)))
    n = len(cases)
    print(f"\n== {Path(path).name}: {n} cases ==")
    print(f"model accuracy   {tot['model']}/{n}")
    print(f"effort accuracy  {tot['effort']}/{n}")
    for label, a, b in (("delegate", "delegate", "delegate_n"), ("split", "split", "split_n"), ("fan_out", "fan", "fan_n")):
        if tot[b]:
            print(f"{label:<16} {tot[a]}/{tot[b]}")
    print(f"under-powered    {len(under)}" + (f"  -> {', '.join(under)}" if under else ""))
    for cid, why in misses:
        print(f"  MISS {cid}: {why}")
    return len(under)


if __name__ == "__main__":
    args = sys.argv[1:]
    use_flags = "--no-flags" not in args
    paths = [a for a in args if a != "--no-flags"] or [HERE / "cases.jsonl", HERE / "holdout.jsonl"]
    sys.exit(1 if sum(run(p, use_flags) for p in paths) else 0)
