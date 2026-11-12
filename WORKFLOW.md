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
4. **Tests:** run the project's tests before creating the pull request. For Python projects under `applications/`, run `python -m pytest` from the project folder (for example `applications/Countdown`), after `python -m pip install -r requirements.txt`. Add new tests for new code. The CI check `checks` runs the same tests and must be green on the pull request (see section 5). `scripts/check.sh` runs these tests and the other checks locally in one step (see section 8).
5. **Extra checks:** *(Placeholder: add further verification steps here, for example linting, a build, or a manual check.)*

## 5. Pull request and merge
1. Push the branch and create a pull request that references the issue and carries the same labels as the issue. The pull request template lists the verification gates and asks whether the workload level was right, so fill it in.
2. Direct pushes to `main` are blocked. Every change goes through a pull request.
3. The required status check `checks` (GitHub Actions, `.github/workflows/ci.yml`) must pass before the pull request can be merged. This is enforced by the repository ruleset on `main`, so a failing or missing check blocks the merge.
4. If `checks` fails, read the failure in the pull request's Checks tab, fix it on the same branch, push again and wait for the check to run again. Never merge around a failing check, and never change the required check or ruleset to get a pull request through.
5. New verification steps (tests, linting, build) are added as steps in the existing `checks` job, so the required check name stays the same.
6. A GitHub Action (`.github/workflows/auto-merge.yml`) enables auto-merge on every new pull request from this repository, so the pull request merges by itself as soon as `checks` is green. Nobody needs to click merge.
7. After opening a pull request, check that auto-merge was enabled (the Conversation tab shows "github-actions enabled auto-merge"). If it was not, for example because the Action failed or the repository setting "Allow auto-merge" is off, report it as a follow-up issue instead of merging by hand.
8. To keep a pull request from merging automatically, set the label `no-auto-merge` when the pull request is opened (a label added afterwards does not undo auto-merge that is already enabled), or open it as a draft. Pull requests from forks never get auto-merge.
9. Name the issue in the pull request description: `Closes #N` if the pull request finishes issue #N, or `Refs #N` if it does not. Issues named with `Closes #N` were not closed after merges made by the auto-merge Action (see #28), so do not rely on it. The owner closes the issue after the pull request is merged (GitHub also closes it by itself when the owner merges by hand). Do not wait for the issue to close, and do not close it by hand. In the report after the last pull request of an issue, say that the owner closes the issue.

## 6. Follow-up work
Create a new issue for any follow-up found during the work or raised in pull request comments. Set a workload level (Low, Medium or High) on every new issue. New issues use an issue template so that goal, tasks and acceptance criteria are always present: `.github/ISSUE_TEMPLATE/task.md` for ordinary tasks and `.github/ISSUE_TEMPLATE/gui-task.md` for changes to a window that the owner tests by hand (it adds an owner check list and reminds that the pull request needs the label `no-auto-merge`).

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
| `scripts/check.sh [project folder]` | Before creating a pull request (verification gate 4). It runs the required-files check, the link check, the tests of the project folder (default `applications/Countdown`) and the tests of the scripts, prints a summary and exits with an error code if any step fails. | `scripts/check.sh applications/Countdown` |
| `scripts/verify_gui.sh script.py [args]` | When a tkinter window must be tested without a screen, for example to start the window with a test script that sends clicks. It runs the given script under `xvfb-run` with a Python that has `tkinter`, or says what is missing. Run it from the folder the script expects. | `scripts/verify_gui.sh my_check.py` |
| `scripts/pr_body.py` | When writing the pull request description. It prints text in the format of `.github/pull_request_template.md`, with options for the issue number, `Closes` or `Refs`, ticked gates, the workload feedback, and the owner check list for pull requests with `no-auto-merge`. It refuses text that looks like a token and never adds links. Use `--footer` for text that must end the description. | `python3 scripts/pr_body.py --issue 50 --summary "..." --gates-passed --workload right` |

The link check in `scripts/check.sh` repeats the logic in `.github/workflows/ci.yml`. If one changes, change the other as well. CI does not run the tests in `scripts/tests/`, only `scripts/check.sh` does. Running them in CI needs a new step in `ci.yml`, which is a workflow change for the owner (see `GitRequirements/README.md`).

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
