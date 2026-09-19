# canvas-api-guard release

Guard: 1.19.0
Specialized Functions: 0.16.0
Commit: 0a50e7d0691020583292d12f88ec92a3270cc23c
Date: 2026-09-19

Install or update: paste into Terminal

    curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/release/install-from-github.sh | sh

## Changes since the previous release

- test: deferred minors from the whole-branch review
- docs: note the audit log's 200-char truncation on write evidence and requests
- docs(guard skill): fence download-submission-file and post-policy commands
- fix(level2): honour posted_at when counting visibility of a rubric grade
- fix(level2): refuse to count a grade as written unless the guard proved it
- fix(guard): disprove a criterion missing from an exposed rubric assessment
- docs(skill): the guard has two added verbs, not one
- chore: guard 1.19.0 and level 2 0.16.0 - rubric review before grade, documented
- docs(level2): drop the retired bulk-grade-with-rubric from the skill
- feat(level2): grade-with-rubric takes a list, grade optional per entry, hidden by manual posting
- feat(guard): post-policy verb - one fixed GraphQL mutation, read back through REST
- feat(guard): cap free text in the audit log's request and evidence records
- feat(guard): prove a rubric_assessment-only write, one row per criterion
- docs(spec,plan): one verb - grade-with-rubric with an optional grade per entry
- docs(plan): implementation plan for rubric review before grade
- Merge remote-tracking branch 'origin/main' into feat/rubric-review-before-grade
- docs(spec): record item 1 of the live gate as observed on the faculty instance
- docs(spec): close the visibility decision - switch to manual posting, instructor releases
- docs(spec): say where an ignore_for_scoring criterion comes from
- docs(spec): exclude ignore_for_scoring from the totals, matching Canvas
- docs: correct the post-policy finding, and take two pilot-review items
- docs: design for rubric review before the grade
