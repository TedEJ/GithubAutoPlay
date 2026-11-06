# GithubAutoPlay
An attempt to automatically have development through Claude and version handling through Github

## About this project
This project is developed and updated only by Claude, without human interaction. Ideas and tasks are handed to Claude as GitHub issues.

## Workload levels
Every new issue must have a workload level set as a label. The level shows how many tokens are expected to be needed to solve the task:

- **Low**
- **Medium**
- **High**

## Workflow for issues
This is the short version. The full, detailed workflow, including verification gates, is in [WORKFLOW.md](WORKFLOW.md), and Claude reads it together with [CLAUDE.md](CLAUDE.md).

1. Review the issue. Check that the workload level matches the description and Claude's own estimate of token use. If the level is wrong, update the level to a higher or lower one instead of performing the issue. Then continue, or take another issue that is within token reach.
2. Fetch the main branch.
3. Check out a new branch named after the issue, for example `feature-Update-ReadME`.
4. Perform the updates.
5. Create a pull request that is set to merge automatically. Create new issues from comments in the pull request, and set Low, Medium or High as the workload level on each new issue.

## Safeguards for automatic merge
Pull requests are merged automatically, so changes must never go straight into `main`. The following safeguards apply (see issue #3):

- Direct pushes to `main` are blocked. All changes go through a pull request.
- Before a pull request is created, all verification gates in [WORKFLOW.md](WORKFLOW.md) must pass. Steps for testing and verification are added there.
- The required status check `checks` (GitHub Actions, defined in `.github/workflows/ci.yml`) must pass before a pull request can be merged. A pull request with a failing check cannot be merged.
- Once a pull request is ready and the check is green, it is merged.

The check currently verifies that the required files exist and that relative links in the Markdown files work. More steps, such as tests, are added to the same job when the project has code, so the required check name stays `checks`. If the check fails, fix the problem on the same branch and push again.

Changing branch protection and repository settings requires owner rights and is done by the repository owner.
