# Git requirements

This folder is documentation only. Nothing in it runs. It collects everything that makes the Git and GitHub side of this project work, so it can be read in one place and set up again if needed.

## The workflow files
GitHub only runs workflows from `.github/workflows/`, and that folder is hidden in many file views. The files below are **copies for reading**. The real files are the ones in `.github/workflows/`, and those are what count.

| File | What it does |
|------|--------------|
| `ci.yml` | The required check `checks`. Runs on every pull request into `main` and verifies that the required files exist and that relative links in the Markdown files work. More steps (tests, linting) are added to the same job when the project has code. |
| `auto-merge.yml` | Enables GitHub auto-merge on every new pull request from this repository, so it merges by itself when `checks` is green. Skipped for drafts, forks and pull requests with the label `no-auto-merge`. A second job, `close-linked-issues`, runs when a pull request has been merged and closes the issues named with a closing keyword (`Closes #N`) in its description, with a comment. `Refs #N` closes nothing. |

When one of the real workflows changes, update its copy here in the same pull request, so they stay identical.

## Repository settings (done by the repository owner)
These are not in the code, so they are listed here.

- **Ruleset on `main`:** require a pull request before merging, block direct pushes, and require the status check `checks` to pass. Do not add `enable-auto-merge` as a required check.
- **Allow auto-merge:** on (Settings → General → Pull Requests), with merge commits allowed.
- **Labels:** `Low`, `Medium`, `High` (workload level) and `no-auto-merge` (opt out of auto-merge, set when the pull request is opened).
- **Token for Claude:** a fine-grained token limited to this repository with Contents, Pull requests and Issues set to Read and write. It cannot create or change files under `.github/workflows/`, so those files are added through the GitHub web interface.

## Related files
- `WORKFLOW.md`: the detailed development workflow.
- `CLAUDE.md`: the short entry point that Claude reads automatically.
