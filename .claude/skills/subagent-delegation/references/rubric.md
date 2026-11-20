# Rubric: task type to tier and effort

Tiers: small = Haiku-class, mid = Sonnet-class, top = Opus-class. "Main" means do not delegate.

## Reading and searching
| Task | Tier | Effort |
|---|---|---|
| Grep a codebase or log, list matches | small | low |
| List files, summarize project structure | small | low |
| Extract fields from JSON/CSV, count rows | small | low |
| Summarize a short README or config | small | low |
| Scan .md files for broken links or stale paths | small | low |
| Judge whether a doc contradicts the code | mid | medium |
| Read a long module and explain how it works | mid | medium |
| Read many files (10+) to find a bug | mid | high, with the reads fanned out to small subagents |

## Running commands
| Task | Tier | Effort |
|---|---|---|
| git status/log/diff, ls, install deps, format | small | low |
| Run the test suite and report pass/fail | small | low |
| Run a backtest and return the metrics table | small | low |
| Triage a failing test from its traceback | mid | medium |
| Migration, deletion, overwrite, force push, deploy, rollback | main | high, confirm with the user first |

## Writing and changing code
| Task | Tier | Effort |
|---|---|---|
| Rename a variable, fix lint errors | small | low |
| Small utility or unit test for a known function | mid | low to medium |
| Well-specified feature | mid | medium |
| Review a diff for bugs | mid | medium to high |
| Debug an issue that spans several modules | top | high |
| Design a schema, architecture or refactor plan | top | high |
| Security-sensitive code (auth, secrets, input handling) | top | high |

## Analysis and reasoning
| Task | Tier | Effort |
|---|---|---|
| Fetch a page and check whether it mentions a term | small | low |
| Compare two parameter sets from a results table | mid | medium |
| Decide whether a backtest is real or overfit (lookahead, leakage) | top | high |
| Choose between approaches with trade-offs | top | high |
| Synthesize subagent findings into a decision | main | high |

## GithubAutoPlay
| Task | Tier | Effort |
|---|---|---|
| Run `scripts/check.sh` and report which steps fail | small | low |
| Check that `GitRequirements/*.yml` equal `.github/workflows/*.yml`, or that links in `.md` files work | small | low |
| Check whether two documents (for example `WORKFLOW.md` and `README.md`) contradict each other | mid | medium |
| Implement an issue (Designer/Developer worker) | mid | medium (pinned `sonnet`) |
| Review ordinary code or documentation changes (Reviewer worker) | mid | medium to high (pinned `sonnet`) |
| Review a hook, a guard, credential handling or any security-sensitive change | top | high |
| Create or merge a pull request, close an issue, push, handle a token | main | high, never a worker |

## Why the rows come out this way
- **Checkable beats clever.** A wrong answer from a small model is cheap when a test, exit code or row count exposes it.
- **Unverifiable judgment is where tier matters.** Nobody can easily check "is this backtest sound?", so use the strongest model.
- **Reversibility trumps everything.** Even a trivial-looking command goes to the main agent if it cannot be undone. A cache wipe that rebuilds itself is reversible; a dropped table is not.
- **Wide is not the same as hard.** Forty files of independent reads are cheap work fanned out; the diagnosis that follows is the mid-tier part.

## Debatable rows (revisit with real usage)
- "Review a diff": medium or high depends on what the diff touches (security hooks and anything guarding access are high, top tier).
- "Small utility": low or medium depending on how well specified it is.
- Vague requests ("look into why the results look off"): mid-tier default, or ask one question first.
