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
- **Issues were not closed after bot merges.** Pull requests merged by the auto-merge Action did not close their issues, even with `Closes #N`, and a workflow meant to close them never ran: events caused by the built-in `GITHUB_TOKEN` do not start other workflows. A manual merge by the owner did close the issue. The tests of this were done under issue #28, in pull requests #33 and #34. The decision was to stop trying to close issues automatically: the close-linked-issues step was removed (#36, #37) and the issue is closed after the merge by the manager (first by the owner, see "Closing issues" below).
- **`Closes #N` or `Refs #N`.** Because of the above, the pull requests since then have used `Refs #N` or `Closes #N` as the issue needs, and the manager closes the issue after the merge. `WORKFLOW.md` section 5, item 9, explains the two keywords.
- **A pull request that did not merge.** #34 had auto-merge enabled but did not merge. Its branch was behind `main`, and the ruleset requires an up to date branch. It was closed without merging.
- **No `tkinter` in the default Python.** The default Python in the cloud session had no `tkinter`. A second interpreter (`/usr/bin/python3.12`) that has it was used for the window tests, and `scripts/verify_gui.sh` now looks for one.
- **Setting labels in the browser.** The label picker on GitHub's pull request page was unreliable to click, and clicking it later did not apply the label at all. What works is to prefill the page with the `labels=` parameter in the compare URL, so the label is set when the pull request is created. This matters for `no-auto-merge`, because the auto-merge Action reads the labels when the pull request is opened.

## Manual steps that remain
- **The token for each push.** The git proxy refuses the repository unless it has a credential, so a token had to be pasted in the chat in most sessions. This was the most repeated manual step and the biggest friction. It also gets lost: a token pasted earlier is no longer in the session after its history has been compressed, so a new one had to be pasted. Options are described in [WORKFLOW.md](WORKFLOW.md) section 9 and are owner decisions.
- **Workflow files and repository settings.** Only the owner changes `.github/workflows/`, the ruleset, labels and token permissions, because the token cannot change workflow files. Workflow changes were made by the owner on GitHub, and keeping the reference copies in `GitRequirements/` identical needed follow-ups (for example #19).
- **Pull requests are created in the browser.** There is no `gh` or API access in the session, so each pull request was filled in through the web page. The helper `scripts/pr_body.py` now writes the description text.
- **Closing issues.** The manager (the agent) closes the issue after the merge. Today this is done in the browser with the "Close issue" button. The intended way is a connector with its own authorisation, which is not set up. If the manager cannot close an issue, the owner does.
- **Testing GUI changes** is done by the owner by design (see the next section).

## The owner's check of GUI changes
Changes that users see are never merged on a green `checks` alone. They get the label `no-auto-merge` when the pull request is created, and the owner tests them by hand before merging.

- **Why.** The tests and the browser checks in the cloud session find logic errors and layout problems, but not how the program behaves on the owner's own computer. The owner found a real failure that way: the Riksdagen feed could not be fetched on a Windows machine because of a missing intermediate certificate. That could not be seen from the cloud session, which cannot reach the feed at all.
- **How.** The pull request description has a list "Owner check before merging" with concrete steps (what to run, what to click, what to see). The owner runs it locally, reports back in the chat, and merges the pull request. The manager then closes the issue.
- **What it does not replace.** The Reviewer pass and the required check `checks` still apply. The owner's check comes on top of them. Findings go back into the same pull request or into a new issue, and decisions that come out of the check are written into the design document.

## What we learned later (news-reader, from 2026-11-12)
- **`Closes #N` was investigated again.** The keyword is recognised (the pull request lists the issue under "may close these issues"), the repository setting "Auto-close issues with merged linked pull requests" is on, and the pull request targets `main`. The issue was still not closed when the auto-merge Action merged. GitHub's documentation does not name the merging actor as a condition, so the cause is not proven. Two small pull requests, one merged by the Action and one by the owner, would show whether the bot merge is the reason.
- **The Reviewer verdict depends on the files.** The check `checks` accepts "Not needed (documentation only)" only when every changed file is Markdown. A single changed script, even one text line in `scripts/pr_body.py`, needs a real Reviewer pass with verdict OK. The first run of a pull request failed for this reason.
- **A `Depends on:` line in the issue templates.** Each issue lists the issues that must be closed first, or `Depends on: None`. The manager checks it before an issue is taken. There is no automatic check.
- **Manager, Developer and Reviewer.** The manager talks to the owner, writes the briefing and the pull request, and keeps the token. A Developer worker implements and a Reviewer worker reviews (OK or MUST-FIX, at most two fix rounds before the owner is asked). Workers never get a token.
- **Live data in the browser when the terms require it.** Sveriges Radio may be linked and streamed but not stored or copied, so the page fetches it live in the browser, in memory only, and never from the build. The terms of a source can decide the architecture, so they are read before the first design step and again before the last.
- **Tests that cannot reach the real service.** The cloud session cannot reach SVT or Riksdagen. Real feed checks run on the owner's computer, and the pull request says so in the owner check list.

## Workload labels
The pull request template asks whether the workload label was right. In the 11 pull requests where the answer was checked (#24, #25, #26, #27, #39, #41, #43, #45, #47, #52 and #54), every one says "Right level", and none says too low or too high. This is weak evidence: the answers were filled in by Claude itself, not by an independent reviewer, and no token use was measured. So the labels were never contradicted, but we cannot say how accurate they were.

## Next time
1. **Remove the token paste.** Decide on one of the options in [WORKFLOW.md](WORKFLOW.md) section 9, preferably adding the repository to the session's sources if the Claude app allows it.
2. **One copy of the checks.** Let `ci.yml` call `scripts/check.sh` so the link check exists once. Today it is in both files.
3. **Cover more links.** The CI link check only reads Markdown files in the repository root, not in subfolders such as `applications/`.
4. **Keep the reference copies in sync.** `GitRequirements/ci.yml` must be identical to the real `ci.yml` after each workflow change, in the same pull request or an immediate follow-up.
5. **Measure the workload.** Note the real effort (for example turns or tokens) in the pull request, so the labels can be compared with something other than opinion.
6. **Test imported code.** The imported game in `applications/football-chess/` is one HTML file without tests. A first ticket for a new project could split the logic into testable parts.
