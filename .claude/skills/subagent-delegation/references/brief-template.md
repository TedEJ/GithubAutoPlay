# Delegation brief template

Every subagent brief contains these fields. The opening line is mandatory and is the first line of the subagent's final report, for every task it takes. Only the final message comes back to the main agent, so the brief must say "final report". Keep it short; the subagent has no memory of the conversation.

```
Opening line: Begin your final report with exactly: Hi, subagent taking task '<short task name>' with assigned model <model> at <effort> effort.
Model / effort: <haiku|sonnet|opus> / <low|medium|high>
Goal: <one sentence: what question this answers or what this produces>
Scope: <exact files, directories, URLs; say what is out of scope>
Allowed actions: <read-only | run tests | edit these files only | ...>
Forbidden: <delete, overwrite, push, deploy, anything not listed above>
Return format: <e.g. a table of path | line | message, max 20 rows>
If unsure: <report the uncertainty and stop; do not guess or widen scope>
```

## Worker briefs in GithubAutoPlay

For a Designer/Developer or Reviewer the brief also contains what `WORKFLOW.md` section 10 ("Briefing: what every worker gets") requires: the full issue text, the repository folder and branch name, the instruction to read `WORKFLOW.md` and `CLAUDE.md` first, and the report format (Designer/Developer: Summary, Files changed, Checks run, Acceptance criteria, Assumptions and open questions, Follow-up ideas; Reviewer: Verdict, Must fix, Should consider, Checked, Not checked). Under Forbidden always write: push, create or merge pull requests, handle tokens, change `.github/workflows/` or repository settings. The announcement line is the first line of the final report, before those headings.

```
Opening line: Begin your final report with exactly: Hi, subagent taking task 'review PR 130 guard hook' with assigned model opus at high effort.
Model / effort: opus / high
Goal: Review branch designer-guard for bypasses of the push block; report findings only.
Scope: .claude/hooks/designer_guard.py, .claude/hooks/designer_guard.sh, scripts/tests/test_designer_guard.py, issue #126 text below.
Allowed actions: read-only, and running python -m pytest scripts/tests.
Forbidden: edits, commits, push, pull requests, tokens, .github/workflows/.
Return format: the Reviewer report from WORKFLOW.md section 10 (Verdict, Must fix, Should consider, Checked, Not checked).
If unsure: list the open question in the report and stop as far as it matters.
```

## Examples

Small, fanned out:
```
Opening line: Begin your final report with exactly: Hi, subagent taking task 'read timeout in service_a.yaml' with assigned model haiku at low effort.
Model / effort: haiku / low
Goal: Report the value of `timeout` in this config file.
Scope: configs/service_a.yaml only.
Allowed actions: read-only.
Forbidden: edits of any kind.
Return format: one line: path | timeout value | not found.
If unsure: say "not found" and stop.
```

Mid, diagnosis:
```
Opening line: Begin your final report with exactly: Hi, subagent taking task 'diagnose test_cache_eviction' with assigned model sonnet at medium effort.
Model / effort: sonnet / medium
Goal: Find why test_cache_eviction fails; propose the smallest fix but do not apply it.
Scope: src/cache.py, tests/test_cache.py.
Allowed actions: read-only, and running pytest on that one test.
Forbidden: edits, other test files.
Return format: cause in two sentences, then a diff in a code block.
If unsure: list the two most likely causes and what would distinguish them.
```
