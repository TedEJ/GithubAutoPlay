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
1. Review the issue. Check that the workload level matches the description and Claude's own estimate of token use. If the level is wrong, update the level to a higher or lower one instead of performing the issue. Then continue, or take another issue that is within token reach.
2. Fetch the main branch.
3. Check out a new branch named after the issue, for example `feature-Update-ReadME`.
4. Perform the updates.
5. Create a pull request that is set to merge automatically. Create new issues from comments in the pull request, and set Low, Medium or High as the workload level on each new issue.

## Safeguards for automatic merge
Pull requests are merged automatically, so changes must never go straight into `main`. The following safeguards apply (see issue #3):

- Direct pushes to `main` are blocked. All changes go through a pull request.
- Once a pull request is ready, it is merged automatically.

There are no required automated checks yet, because the project has no code to test. When code exists, a CI check (GitHub Actions) should be added and made required, so a pull request with a failing check cannot be merged. Until then, mistakes are caught by reviewing the pull request before it is merged.

Changing branch protection and repository settings requires owner rights and is done by the repository owner.
