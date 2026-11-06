# Instructions for Claude

This repository is developed and updated only by Claude, driven by GitHub issues.

Follow the detailed process in [WORKFLOW.md](WORKFLOW.md) for every issue. It is the authority on workload levels, taking an issue, verification gates and pull requests.

Hard rules (summary, see WORKFLOW.md for details):
- Never push directly to `main`. Use a branch and a pull request.
- Check the workload level before starting an issue and correct it if it is wrong.
- All verification gates must pass before a pull request is created.
- The required status check `checks` (`.github/workflows/ci.yml`) must be green before a pull request is merged. If it fails, fix it on the same branch. Never merge around it or change the ruleset.
- Add new verification steps to the existing `checks` job so the required check name stays `checks`.
- Pull requests merge automatically through the Action `.github/workflows/auto-merge.yml` once `checks` is green. Do not merge by hand. Check that auto-merge was enabled after opening a pull request, and use the label `no-auto-merge` (set when the pull request is opened) only to opt out.
- Never store tokens or credentials in the repository.
