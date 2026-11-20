---
name: subagent-delegation
description: Choose the model tier and effort level for each subagent, and write the delegation brief, whenever you are about to spawn, delegate to, or fan out work to a subagent or parallel agent (in GithubAutoPlay this includes the Designer/Developer and Reviewer workers). Use it even if the user never mentions models or cost. It covers reading or searching files, running commands or tests, bulk edits, debugging, code review, design decisions and anything destructive. Do not use it for work you will do yourself in the main thread; the main agent never switches its own model mid-task.
---

# Subagent delegation

The main agent keeps its own model. This skill only decides, for each subagent you spawn, **which model and effort it should run on**, and what the brief must say.

## Procedure

0. **Is a subagent worth it?** Every spawn is a cold start: the subagent knows nothing, so the brief costs tokens and its report has to be read. A single grep, a few small files or one command is cheaper in the main thread. Spawn only for work that is large, independent, or needs isolation or a different tier, and in this environment only when the user has asked for delegation or the project's process calls for a worker (see "This project").
1. **Split the task into gather and decide.** Gathering (read, grep, run, extract) can usually go down a tier. Deciding (interpret, choose, design, judge risk) stays with you or goes to the top tier.
2. **Ask four questions about each subtask.**
   - *Reversible?* Can the action be undone cheaply? If not, do it yourself.
   - *Checkable?* Will a test, exit code, schema or row count expose a wrong answer? Checkable work can go cheap.
   - *Breadth?* How many things must be held in mind at once? Many interacting pieces push the tier up. Many independent pieces fan out in parallel instead.
   - *Cost of a wrong answer?* Security, money, data loss and shipping decisions push the tier up.
3. **Pick the tier and effort** from the table, or from `references/rubric.md` for the full task list.
4. **Write the brief** using `references/brief-template.md`. Every brief states the model, the effort, the goal, the scope, the allowed actions and the return format, and tells the subagent to open with the announcement line (see below). Set the tier through the `model` parameter of the Agent tool and the effort through its `effort` parameter; text in the brief does not set either.
5. **Escalate on doubt.** If a cheap subagent returns something ambiguous, contradictory or suspiciously empty, rerun that subtask one tier up instead of trusting it.

| Work | Tier | Effort |
|---|---|---|
| Grep, list, count, extract, run tests or commands, format, rename, fetch and check a term | Small (Haiku-class) | low |
| Explain code, triage a failure, implement a well-specified feature, compare results, review a diff | Mid (Sonnet-class) | medium (high if wide) |
| Design, cross-module debugging, security-sensitive code, overfit or bias checks, trade-offs | Top (Opus-class) | high |
| Destructive or irreversible actions, final decisions, synthesis of subagent results | Main agent, not a subagent | high |

## Announcement line

Every subagent starts every task by saying, word for word:

> Hi, subagent taking task '<short task name>' with assigned model <model> at <effort> effort.

Put the filled-in line in the brief (the script prints it as `announce`; it is `null` when the main agent should do the task itself). A subagent that handles several tasks in a row says it again at the start of each one. The line states what the brief **assigned**. A subagent cannot reliably know which model it really runs on, so the line shows that the brief was read and does not prove the model. If a report comes back without the line, note that in your summary and treat the brief as not read. For work that matters, check the tier you passed in the Agent call, not what the subagent claims. In a Developer or Reviewer report the line comes first, before the report format required by `WORKFLOW.md`.

## This project (GithubAutoPlay)

- **Use the defined workers.** The roles live in `.claude/agents/`: `designer-developer` (model `sonnet`, hook that blocks push, `gh` and network commands) and `reviewer` (model `sonnet`, read-only by tools and hook). A defined agent keeps its pinned model; do not override it without a reason, and do not copy its role limits into a different agent type while the real one is available.
- **Hooks only exist where the agent definitions load.** In Claude Code in a terminal clone, `/agents` lists both. In a Cowork or app task they are not loaded, so the manager starts a general-purpose subagent and pastes the role file into the brief; the limits then rest on the brief alone, and the pull request must say so (see "Two ways of working" in `WORKFLOW.md` section 10).
- **Briefing and reports follow `WORKFLOW.md` section 10.** The brief carries the issue text, the repository folder and branch name, the instruction to read `WORKFLOW.md` and `CLAUDE.md`, what the worker must not do, the deliverable and the report format. The brief template below adds the model, effort and announcement line on top; it never replaces those.
- **Workers never get a token** and never push, create pull requests or change `.github/workflows/`. Put that under Forbidden in every worker brief.
- **Tier overrides for this project.** The pinned `sonnet` Reviewer is right for ordinary code and documentation. For hooks, scripts that guard something, credential handling and anything else security-sensitive, the Reviewer needed three rounds on the guard hook, so run the review on the top tier (a general-purpose subagent with `model: opus`, or ask the owner to run it in the terminal) and say so in the pull request.
- **Always read the diff yourself** after a Developer reports; a worker once reported a change that was never made.

## Rules

- Gather and report goes down a tier; decide stays up.
- Cheap subagents get read-only or easily reversible actions. Anything destructive stays with the main agent, and you confirm with the user first.
- Fan out independent reads to parallel small subagents only when there are eight or more files or sources and delegation is wanted; below that, read them in the main thread. Merge the reports yourself.
- A vague task gets the mid tier by default, or one clarifying question before spawning anything.
- Never let a subagent make the call that depends on what other subagents found.

## The helper script

`scripts/pick_model.py "<task>" [--files N] [--title "..."] [flags]` prints a recommendation as JSON: model, effort, whether to delegate at all, whether to split or fan out, the `announce` line, and the reasons.

On its own it is a keyword heuristic, and a weak one: on `tests/stress.jsonl` (rephrased tasks without trigger words) it scores 2 of 14. It under-powers hard reasoning phrased in plain words, and over-escalates reversible or read-only tasks that mention "delete" or "token". The flags fix that by letting you pass the answers to the four questions, which override the keywords:

| Flag | Meaning | Effect |
|---|---|---|
| `--read-only` | The action only reads | Ignores destructive and security keywords |
| `--reversible` | Easily undone, e.g. a cache that rebuilds | Ignores destructive keywords |
| `--irreversible` | Cannot be undone | Main agent, top tier, confirm first |
| `--mechanical` | Bounded and checkable (grep, convert, tidy) | Small tier |
| `--routine` | Ordinary bounded engineering | Mid tier, ignores design and "why" keywords |
| `--unverifiable` | No cheap way to check the answer | Top tier |
| `--high-stakes` | A wrong answer is costly | Top tier |

Flags combine, e.g. `--reversible --mechanical` for "wipe the cache directory". With the flags set, the stress set scores 14 of 14, but I chose those flags knowing the labels, so that number only shows the flags are honored. The judgment is yours when you set them. Run `tests/run_eval.py` after any change to the script, and `tests/run_eval.py --no-flags tests/stress.jsonl` for the keyword-only baseline.

## Reference files

- `references/rubric.md`: full task-to-tier list with the reasoning behind each row.
- `references/brief-template.md`: what every delegation brief must contain.
- `references/environments.md`: how to set the model per subagent in Claude Code and the API.
