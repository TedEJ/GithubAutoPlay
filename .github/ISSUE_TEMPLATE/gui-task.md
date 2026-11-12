---
name: GUI task
about: A task that changes a window or screen that the owner must test by hand
title: ""
labels: []
assignees: ""
---

<!-- Set exactly one workload label before the issue is taken: Low, Medium or High.
     See section 1 of WORKFLOW.md for what the levels mean.

     GUI changes are tested by the owner before they are merged. Claude opens the
     pull request with the label `no-auto-merge`, so remind yourself that the pull
     request, not this issue, needs that label. -->

## Goal
<!-- One or two sentences: what should be true when this issue is done? -->

## Tasks
- [ ] <!-- Small, concrete step -->
- [ ] <!-- Small, concrete step -->
- [ ] Update the README of the project (how to run, step list)
- [ ] Run the tests of the project

## Notes
- The pull request gets the label `no-auto-merge`. The owner tests locally and merges manually, and closes this issue after the merge.
- Keep the GUI thin: rules and decisions live in modules that can be tested without a display.
<!-- Add constraints, links, decisions that are already made and what is out of scope. -->

## Owner check
<!-- What the owner should try by hand before merging. Claude copies this list into the pull request. -->
- [ ] 

## Acceptance criteria
<!-- Checkable statements. Claude re-reads these as a verification gate before creating the pull request. -->
- 
