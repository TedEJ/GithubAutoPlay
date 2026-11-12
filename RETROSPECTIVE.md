# Retrospective: the issue-driven workflow

This is what we learned from building the Countdown game (and a few smaller things) from GitHub issues, so the lessons can be reused. It is based on the merged pull requests, the issues and [WORKFLOW.md](WORKFLOW.md). The process itself is described in [WORKFLOW.md](WORKFLOW.md) and the repository setup in [GitRequirements/README.md](GitRequirements/README.md).

## What worked
- **Small, issue-sized steps.** Countdown was built in one pull request per step: skeleton and tests (#17), number placement (#24), game state (#25), window (#26), hide timer (#27), clicking and lose screen (#39), restart button (#41), start screen (#43), win screen (#45) and polish (#47). Each step was easy to review and test.
- **Logic without a window, thin GUI.** Placement, game rules, settings and texts are plain Python modules with `pytest` tests. Only `gui.py` imports `tkinter`, so the check `checks` can run the tests on GitHub without a display.
- **A required check and a ruleset.** Direct pushes to `main` are blocked and `checks` must be green, so nothing reached `main` without passing the tests.
- **Auto-merge for safe changes, manual merge for GUI changes.** Documentation and tooling pull requests merged by themselves. GUI pull requests got the label `no-auto-merge`, and the owner tested them by hand before merging.
- **Real-window verification.** In the cloud session a Python with `tkinter` plus `xvfb-run` made it possible to start the real window, send clicks and look at screenshots, which helped to find timing problems (for example a hide timer from an old round) before the owner tested.
- **Templates.** The issue template and the pull request template kept goal, tasks, acceptance criteria, verification gates and the workload question in every issue and pull request.

## What got stuck and how it was solved
- **Issues were not closed after bot merges.** Pull requests merged by the auto-merge Action did not close their issues, even with `Closes #N`, and a workflow meant to close them never ran: events caused by the built-in `GITHUB_TOKEN` do not start other workflows. A manual merge by the owner did close the issue. The tests of this were done under issue #28, in pull requests #33 and #34. The decision was to stop trying to close issues automatically: the close-linked-issues step was removed (#36, #37) and the owner closes the issue after the merge.
- **`Closes #N` or `Refs #N`.** Because of the above, the pull requests since then have used `Refs #N`, and the owner closes the issue. `WORKFLOW.md` section 5, item 9, explains the two keywords.
- **A pull request that did not merge.** #34 had auto-merge enabled but did not merge. Its branch was behind `main`, and the ruleset requires an up to date branch. It was closed without merging.
- **No `tkinter` in the default Python.** The default Python in the cloud session had no `tkinter`. A second interpreter (`/usr/bin/python3.12`) that has it was used for the window tests, and `scripts/verify_gui.sh` now looks for one.
- **Setting labels in the browser.** The label picker on GitHub's pull request page was unreliable to click. Selecting the entries by script and checking the result before submitting worked.

## Manual steps that remain
- **The token for each push.** The git proxy refuses the repository unless it has a credential, so a token had to be pasted in the chat in most sessions. This was the most repeated manual step and the biggest friction. Options are described in [WORKFLOW.md](WORKFLOW.md) section 9 and are owner decisions.
- **Workflow files and repository settings.** Only the owner changes `.github/workflows/`, the ruleset, labels and token permissions, because the token cannot change workflow files. Workflow changes were made by the owner on GitHub, and keeping the reference copies in `GitRequirements/` identical needed follow-ups (for example #19).
- **Pull requests are created in the browser.** There is no `gh` or API access in the session, so each pull request was filled in through the web page. The helper `scripts/pr_body.py` now writes the description text.
- **Closing issues and testing GUI changes** are done by the owner by design.

## Workload labels
The pull request template asks whether the workload label was right. In the 11 pull requests where the answer was checked (#24, #25, #26, #27, #39, #41, #43, #45, #47, #52 and #54), every one says "Right level", and none says too low or too high. This is weak evidence: the answers were filled in by Claude itself, not by an independent reviewer, and no token use was measured. So the labels were never contradicted, but we cannot say how accurate they were.

## Next time
1. **Remove the token paste.** Decide on one of the options in [WORKFLOW.md](WORKFLOW.md) section 9, preferably adding the repository to the session's sources if the Claude app allows it.
2. **One copy of the checks.** Let `ci.yml` call `scripts/check.sh` so the link check exists once. Today it is in both files.
3. **Cover more links.** The CI link check only reads Markdown files in the repository root, not in subfolders such as `applications/`.
4. **Keep the reference copies in sync.** `GitRequirements/ci.yml` must be identical to the real `ci.yml` after each workflow change, in the same pull request or an immediate follow-up.
5. **Measure the workload.** Note the real effort (for example turns or tokens) in the pull request, so the labels can be compared with something other than opinion.
6. **Test imported code.** The imported game in `applications/football-chess/` is one HTML file without tests. A first ticket for a new project could split the logic into testable parts.
