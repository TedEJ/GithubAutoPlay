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
4. **Tests:** run the project's tests. *(Placeholder: there is no code yet. Add the test command here when code exists.)* The CI check `checks` must also be green on the pull request (see section 5).
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

## 6. Follow-up work
Create a new issue for any follow-up found during the work or raised in pull request comments. Set a workload level (Low, Medium or High) on every new issue. New issues use the issue template (`.github/ISSUE_TEMPLATE/task.md`) so that goal, tasks and acceptance criteria are always present.

## 7. Hard rules
- Never push directly to `main`.
- Never skip verification gates.
- The required check `checks` must be green before a pull request is merged. Never merge with a failing or missing check.
- Do not merge pull requests by hand when auto-merge is enabled. Let the check and the auto-merge Action do it.
- Do not change repository settings or branch protection. That requires the repository owner.
- Never store tokens or credentials in the repository.
