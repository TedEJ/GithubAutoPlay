# Development workflow

This file is the detailed, authoritative description of how work is done in this project. The README has the short version. Claude follows this file for every issue. To add a step, add it to the right section below and keep the numbering.

## 1. Workload levels
Every issue must have exactly one workload level label. The level shows how many tokens are expected to be needed to solve the task.

| Level  | Meaning |
|--------|---------|
| Low    | Small, well-defined change, for example a text edit or a single small file. |
| Medium | Several files or a new piece of functionality with clear requirements. |
| High   | Large or unclear change, or one that touches many parts of the project. |

## 2. Taking an issue
1. Read the whole issue, including comments.
2. Check that the workload level matches the description and your own estimate of token use.
3. If the level is wrong, update the level label (higher or lower) and stop. Do not perform the issue at the wrong level.
4. If the issue is too large for what you can do now, take another issue that is within reach.
5. If the requirements are unclear or conflict with this file, add a comment with the question instead of guessing.
6. Check the dependencies. Every issue has a line `Depends on: #N, #M` (or `Depends on: None`) in its Notes section, and the line is required. It lists the earlier issues that must be finished first, because this issue builds on their result. The manager checks that every listed issue is closed as completed before the issue is taken, and a pull request for an issue is not started while a dependency is open. An issue that depends on an open issue is not taken: the worker or manager tells the owner which issue is still open and takes another issue instead. Issues are closed by the manager after the merge (see section 5), so a dependency counts as done only once its pull request is merged and the issue is closed. If the line is missing, add a comment with the question instead of guessing. There is no automatic check for this rule.

## 3. Doing the work
1. Fetch the latest `main`.
2. Create a new branch from `main`, named after the issue, for example `feature-Update-ReadME`.
3. Make only the changes the issue asks for. Anything else becomes a new issue (see section 6).
4. Commit with a clear message that references the issue, for example `Closes #3`.

## 4. Verification gates (before creating the pull request)
All gates must pass. If one fails, fix it on the same branch and run the gates again. Never skip a gate to get a pull request through.

1. **Scope check:** the diff contains only what the issue asks for.
2. **Acceptance criteria:** every acceptance criterion in the issue is met. Re-read the issue and tick them off one by one.
3. **Documentation:** README and this file are updated if behaviour or process changed.
4. **Tests:** run the project's tests before creating the pull request. For Python projects under `applications/`, run `python -m pytest` from the project folder (for example `applications/Countdown`), after `python -m pip install -r requirements.txt`. Add new tests for new code. The pull request gate states the local result; the CI check `checks` runs the same tests and must also be green before the merge (see section 5). `scripts/check.sh` runs these tests and the other checks locally in one step (see section 8).
5. **Extra checks:** *(Placeholder: add further verification steps here, for example linting, a build, or a manual check.)*

## 5. Pull request and merge
1. Push the branch and create a pull request that references the issue and carries the same labels as the issue. The pull request template lists the verification gates and asks whether the workload level was right, so fill it in. Create it with the description written by `scripts/pr_body.py`, not the empty template, because the Reviewer verdict in the description is needed for `checks` to pass.
2. Direct pushes to `main` are blocked. Every change goes through a pull request.
3. The required status check `checks` (GitHub Actions, `.github/workflows/ci.yml`) must pass before the pull request can be merged. This is enforced by the repository ruleset on `main`, so a failing or missing check blocks the merge.
4. If `checks` fails, read the failure in the pull request's Checks tab, fix it on the same branch, push again and wait for the check to run again. Never merge around a failing check, and never change the required check or ruleset to get a pull request through.
5. New verification steps (tests, linting, build) are added as steps in the existing `checks` job, so the required check name stays the same.
6. A GitHub Action (`.github/workflows/auto-merge.yml`) enables auto-merge on every new pull request from this repository, so the pull request merges by itself as soon as `checks` is green. Nobody needs to click merge.
7. After opening a pull request, check that auto-merge was enabled (the Conversation tab shows "github-actions enabled auto-merge"). If it was not, for example because the Action failed or the repository setting "Allow auto-merge" is off, report it as a follow-up issue instead of merging by hand.
8. To keep a pull request from merging automatically, set the label `no-auto-merge` when the pull request is opened (a label added afterwards does not undo auto-merge that is already enabled), or open it as a draft. Pull requests from forks never get auto-merge.
9. Name the issue in the pull request description: `Closes #N` if the pull request finishes issue #N, or `Refs #N` if it does not. Issues named with `Closes #N` were not closed after merges made by the auto-merge Action (see #28), so do not rely on it. The manager (the agent) closes the issue as completed after the pull request is merged; the owner does not have to. GitHub also closes it by itself when the owner merges by hand. Workers do not close issues (they have no access) and do not wait for the issue to close. Today the manager closes the issue in the browser with the "Close issue" button. The intended way is a connector with its own authorisation, which is not set up yet; until it is, if the manager cannot close an issue, it says so and the owner closes it. In the report after the last pull request of an issue, say who closes the issue.

## 6. Follow-up work
Create a new issue for any follow-up found during the work or raised in pull request comments. Set a workload level (Low, Medium or High) on every new issue. New issues use an issue template so that goal, tasks and acceptance criteria are always present: `.github/ISSUE_TEMPLATE/task.md` for ordinary tasks and `.github/ISSUE_TEMPLATE/gui-task.md` for changes to a window that the owner tests by hand (it adds an owner check list and reminds that the pull request needs the label `no-auto-merge`). Both templates have the required line `Depends on:` in the Notes section (see section 2); a follow-up issue lists there the issues it depends on, or `None`.

## 7. Hard rules
- Never push directly to `main`.
- Never skip verification gates.
- The required check `checks` must be green before a pull request is merged. Never merge with a failing or missing check.
- Do not merge pull requests by hand when auto-merge is enabled. Let the check and the auto-merge Action do it.
- Do not change repository settings or branch protection. That requires the repository owner.
- Never store tokens or credentials in the repository.

## 8. Helper scripts
The folder `scripts/` holds small helpers. They are conveniences: the required check `checks` in CI is still the authority. They need plain `bash` and Python 3.10 or newer, and no extra packages (the tests need `pytest`). The two `.sh` scripts need bash, so they run on Linux, macOS and in a cloud session, and on Windows only through WSL or Git Bash. `pr_body.py` is plain Python and runs anywhere.

| Script | Use it when | Example |
|--------|-------------|---------|
| `scripts/check.sh [project folder]` | Before creating a pull request (verification gate 4). It runs the required-files check, the link check, the tests of the project folder (default `applications/Countdown`) and the tests of the scripts, prints a summary and exits with an error code if any step fails (1 = a step failed, 2 = usage error or no Python). It prints which Python it uses: the first of `python3`, `python`, `py` that can import `pytest`, otherwise the first that runs, with a message that `pytest` is missing. | `scripts/check.sh applications/Countdown` |
| `scripts/verify_gui.sh script.py [args]` | When a tkinter window must be tested without a screen, for example to start the window with a test script that sends clicks. It runs the given script under `xvfb-run` with a Python that has `tkinter`, or says what is missing. Run it from the folder the script expects. | `scripts/verify_gui.sh my_check.py` |
| `scripts/pr_body.py` | When writing the pull request description. It prints text in the format of `.github/pull_request_template.md`, with options for the issue number, `Closes` or `Refs`, ticked gates, the workload feedback, and the owner check list for pull requests with `no-auto-merge`. It refuses text that looks like a token and never adds links. It requires `--reviewer-verdict ok` (or `must-fix`) with `--reviewer-summary`, or `--docs-only` for a documentation-only change. Use `--footer` for text that must end the description. | `python3 scripts/pr_body.py --issue 50 --summary "..." --gates-passed --workload right --reviewer-verdict ok --reviewer-summary "..."` |
| `scripts/check_reviewer.py` | Run by the CI job `checks`. It fails unless the pull request description has `Verdict: OK` in its `## Reviewer` section (or `Verdict: Not needed (documentation only)` when every changed file is Markdown). | `python3 scripts/check_reviewer.py --body-file body.txt --changed-files files.txt` |

The link check in `scripts/check.sh` repeats the logic in `.github/workflows/ci.yml`. If one changes, change the other as well. CI runs the tests in `scripts/tests/` as the step "Run tests of the helper scripts", and `scripts/check.sh` runs them locally.

## 9. Token handling options
This section only describes choices. All of them are **owner settings**: Claude does not change tokens, repository settings or how a session is set up.

Claude needs write access to this repository to push a branch. The git proxy in a cloud session refuses the repository unless it has a credential for it (it answers with an error that says the repository is not in the session's authorized set).

| Option | How it works | Trade-offs |
|--------|--------------|------------|
| Paste a token per session (today) | The owner creates a token and pastes it in the chat when Claude has to push. Claude uses it for the push and does not store it. | Simple, but needs a paste in nearly every session, and the token is visible in the conversation. Revoke it when the work is done. |
| A fine-grained token with a short expiry | The same flow, but the token is limited to this repository, has only Contents, Pull requests and Issues set to Read and write (as in `GitRequirements/README.md`), and expires after a few days. | Less damage if it leaks and no long-lived secret, but still pasted by hand. It cannot change files under `.github/workflows/`. |
| Add the repository to the session's sources | The proxy's error message says the repository must be added to the session's sources. When it is, the proxy supplies the credential itself and no token has to be pasted. | Removes the most repeated manual step. How and where to set it depends on the Claude app, and it has not been tested in this repository, so the owner should check the app's settings. |

Never store a token in the repository, in a script or in an issue, whichever option is used.

Lessons from using this workflow are collected in [RETROSPECTIVE.md](RETROSPECTIVE.md).

## 10. Agents: a manager and workers
Work can be split between a **manager** and **worker agents**. The manager is the Claude conversation with the owner. Workers are sub-agents that the manager starts for one task at a time. A worker starts with **no knowledge** of earlier conversations: everything it needs must be in the instructions the manager gives it and in this file, `CLAUDE.md` and the issue.

### Roles
| Role | Does | Must not |
|------|------|----------|
| Manager | Talks to the owner and asks the owner's questions, owns the plan, starts workers with a full briefing, reads their reports, decides what happens next, pushes branches and creates pull requests, closes the issue after the merge, holds any token the owner pastes. | Skip the verification gates or the owner's manual test. |
| Designer/Developer (worker) | Takes one issue: designs when asked to, creates a branch from the latest `main`, writes code, tests and documentation, runs `scripts/check.sh`, commits locally, and reports. | Push, create or merge pull requests, receive or store tokens, change repository settings or `.github/workflows/`, or work outside the issue. |
| Reviewer (worker) | Reads the finished branch with fresh eyes against the issue's acceptance criteria and sections 3 and 4 of this file, runs the tests, and reports findings. | Change files, commit or push. It has read-only work only. |
| Owner | Gives the ideas, answers questions, tests changes that users see, merges pull requests with `no-auto-merge`, and decides about tokens, settings and workflow files. | |

The manager may start more than one worker in a role when the work needs it. A new kind of role is added to this table first.

### Flow for one issue
1. The owner gives the issue (or the manager and the owner write it together).
2. The manager briefs a Designer/Developer worker (see "Briefing" below).
3. The worker reports. The manager checks the report against the acceptance criteria and reads the diff itself (`git diff main...<branch>`). A report can say that a change was made when it was not (for example a text replacement that failed silently because of line endings).
4. The manager briefs a Reviewer worker on the branch.
5. If the Reviewer lists things that must be fixed, the manager sends them back to the Designer/Developer. At most two rounds; after that the manager asks the owner.
   After the Reviewer's OK, the manager may send small "should consider" items back to the Designer/Developer as a short extra task. The Reviewer looks again when that extra work changes more than comments, wording or names; otherwise the manager checks the diff itself, and the `## Reviewer` section says that the last commit was not reviewed again.
6. The manager pushes the branch and creates the pull request with the description written by `scripts/pr_body.py` (section 5). The `## Reviewer` section of the description holds the Reviewer's verdict (`Verdict: OK`, or `Verdict: Must fix`) and a short summary of what it found. The required check `checks` fails unless the verdict is OK; a pull request that changes only Markdown files may use `Verdict: Not needed (documentation only)`.
7. The owner tests changes that users see, and merges or the auto-merge does. The manager closes the issue.

GitHub does not let the author of a pull request approve it, and all work is done with the owner's account, so the Reviewer reports to the manager instead of approving on GitHub. The verdict check in `checks` is therefore a process rule: it reads what the description says, not who wrote it. A technical guard comes later (level 2): the Reviewer gets its own identity (a separate account or a GitHub App) and the ruleset on `main` requires an approving review from it.

### Status lines
When the manager starts or finishes a worker, it posts one short line in the conversation, in the owner's language, so the owner can follow the work and ask to see a worker's report. The line names the issue number, or the task if there is no issue. Workers do not post status lines; the manager posts them. An extra task after the Reviewer's OK uses the same Designer/Developer lines.

- Designer/Developer started: "Påbörjar arbete på #N"
- Designer/Developer done: "Färdig med arbete på #N"
- Reviewer started: "Review påbörjad på #N"
- Reviewer done: "Review färdig på #N: OK" or "Review färdig på #N: Must fix" (with the round number when it is a second or third round)

### Briefing: what every worker gets
- The full text of the issue, or the task if there is no issue yet.
- The folder of the repository (or git worktree) it works in and the branch name to use.
- An instruction to read `WORKFLOW.md` and `CLAUDE.md` first, and what it must not do (see the table).
- The text of its role file in `.claude/agents/` (`designer-developer.md` or `reviewer.md`) when the worker is not started as that agent (see "How the agents are set up").
- The deliverable: what the manager expects back and where files go.
- The report format below.
- Anything the owner has already decided, and what is out of scope.

A worker that needs an answer from the owner does not guess: it lists the question in its report and stops as far as that question matters.

### Design documents
A design document is named `<project-name>-design.md` and lives in the folder of its project, so that several projects can each have their own, for example `applications/news-reader/news-reader-design.md`. A worker that is asked to design writes the document there, on its own branch, and names it in its report.

### Report formats
Designer/Developer report: **Summary**; **Files changed**; **Checks run** (the command and the result); **Acceptance criteria** one by one, each with yes or no and the evidence; **Assumptions and open questions**; **Follow-up ideas**.

Reviewer report: **Verdict** (ready, or needs changes); **Must fix** (each with file and reason); **Should consider**; **Checked** (what was read and which commands were run); **Not checked**.

### How the agents are set up
- **Definitions:** the two worker roles are defined in `.claude/agents/designer-developer.md` and `.claude/agents/reviewer.md`. Each file holds the role's instructions, its allowed tools and its model, and is the single source for them. Change a role in a pull request, in that file first.
- **Reviewer is read-only by tools and by a hook:** it gets only `Read`, `Grep`, `Glob` and `Bash`. A hook (`.claude/hooks/reviewer_readonly.sh`, which runs `reviewer_readonly.py`) lets `Bash` run only reading commands and the project's tests, and blocks everything else. The hook fails closed: when no working Python is found, the command is blocked. It has tests in `scripts/tests/test_reviewer_hook.py`. It is a process guard, not a security boundary; its known limits are in the docstring of `reviewer_readonly.py`.
- **Where the definitions are loaded:** in Claude Code started inside a clone of this repository (for example `claude` in the terminal), where `/agents` lists both agents. Tested on 2026-11-16: the Reviewer could run `git status`, and its attempts to write a file, commit and create a folder were blocked by the hook. In tasks in the Claude desktop app the definitions are not loaded (the agent type `reviewer` was not found, also in a new task), so the tool limit does not apply there. There the manager starts workers from the conversation, reads the role file and puts its text in the briefing, so the rules are the same but the Reviewer's read-only limit rests on the instructions alone. The agent files use the model `sonnet`; the manager or the owner asks for a stronger model when a task needs it (for example design work or a hard bug).
- **Working directory and the Reviewer's hook:** the manager keeps the session in the repository root and tells both workers to run every command from the root with relative paths (no `cd`, no `git -C`, no absolute paths, no `$` in commands), because the hook blocks them. Loosening this is tracked in issue #121.
- **GitHub access when the manager runs locally:** a local Claude Code session has no `gh` and no connector yet. The owner pushes the branch and opens the pull request, pasting the description written by `scripts/pr_body.py` in full (never the empty template, or `checks` fails on the missing Reviewer verdict), and the manager in the app closes the issue after the merge. Workers must not push; today that rule is text only for the Designer/Developer.
- **Windows:** `.gitattributes` keeps LF line endings for the agent files and scripts, because CRLF can make Claude Code skip an agent file without a message. The hook wrapper tries `python3`, `python` and `py`.
- **Tested on real issues:** the Designer/Developer and Reviewer agents ran in the terminal on #119 and #122. The Reviewer found a real defect in #122.
- Access to GitHub is shared by all agents for now (see the project document "Decision: GitHub access for agents"). Separate access per role is decided later, when several agents are in use. Workers never receive a token: the manager does the pushing.

