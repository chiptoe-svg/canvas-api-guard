# Rubric grading: the requirement, and what is already settled

Date: 2026-09-10
Status: not started. Notes only, so a fresh session does not re-derive them.
Scope: a change to RELEASED behaviour. Own branch, own brainstorm. Nothing here is decided.

## The requirement, in the owner's words

> I would want to be able to have it grade with the entire rubric, have it all entered in canvas
> with comments, but not have grades finalized until reviewed (with all individual pieces shown
> and total calculated) for final approval for grade entry.

So: one grader, everything visible in Canvas, nothing final until a human approves the number.

**This is not moderated grading.** Moderated grading solves several graders scoring
independently with one designated person picking the winner. That is a different problem and the
owner explicitly deferred it. Do not reach for the moderated grading endpoints for this.

## What the Canvas source settles

`app/models/rubric_assessment.rb#update_artifact` (lines 209-230 on `master`, 2026-09-10):

```ruby
return if artifact.blank? || !rubric_association&.use_for_grading? || artifact.score == score
# ... then, for a Submission:
return if !assignment.grants_right?(assessor, :grade) || assignment.checkpoints_parent?
assignment.grade_student(artifact.student, score:, grader: assessor, ...)
```

- With `use_for_grading` **false**, saving a rubric assessment returns early. Criterion points
  and comments are stored. The gradebook is untouched. **This is exactly the review window the
  requirement asks for**, and it is native Canvas behaviour, not something to build.
- With it **true**, Canvas sums the criteria and posts the grade itself, immediately. No review
  window exists.
- Two further gates the REST documentation never mentions: the assessor must hold grade rights,
  and checkpointed assignments are excluded outright, with a source comment saying support is
  unfinished.

The sum itself is computed in `app/models/rubric_association.rb#assess` (around line 302),
which skips criteria flagged `ignore_for_scoring`.

Full detail, with citations, is in `.claude/skills/canvas-api-authoring/references/rubrics-and-grades.md`.

## The blocker

`level2/canvas_api_operations.py` line 214, inside `create_rubric`:

```python
body["rubric_association"] = {"association_type": "Assignment", "association_id": int(assignment_id),
                              "purpose": "grading", "use_for_grading": True}
```

Every rubric this tool attaches to an assignment auto-grades. The requirement is impossible with
rubrics it creates today, because the grade is posted before anyone can review it. Changing that
default is the first thing the change has to do.

Note also that `grade_with_rubric` currently sends `{"submission": {"posted_grade": total},
"rubric_assessment": criteria}` in one request (line 308), computing `total` itself. That is why
it works regardless of the flag, and it is also why nothing today can express a grade that is not
the criterion sum.

## Where the discussion landed

Not a decision. The starting position for the brainstorm.

- Two phases, deliberately. Write the assessment with all criteria and comments and no grade.
  Present every criterion and the computed sum. Then a separate, approved write posts the grade.
- The grade should be **stated, not derived**. The instructor approves a number they can see
  rather than one the tool inferred. This is the part that survives from the single-write design.
- The definition format has to change, and `bulk-grade-with-rubric` follows it. That format change
  is what would matter to anyone vendoring a pinned copy.
- This also unlocks something impossible today: a grade that is not the criterion sum. Late
  penalty, a cap, extra credit, a criterion that does not apply this time.

**Where I was wrong, recorded so it is not re-argued.** I first objected to two writes because
they leave criteria stored with no grade showing, which I called a confusing partial state. That
state is not a failure here. It is the review window, and it is the whole point of the
requirement. The objection was wrong.

## Open dependency before shipping

The flag semantics above are **source-confirmed but not observed**. Source on the default branch
is not what a hosted instance runs, with which feature flags, at which release.

For a reference file, source is proportionate. For changing how grades reach real student
records, watch it happen once first: on an assignment with the flag off, write a rubric
assessment and confirm no grade appears.

GC_Agent (2026-09-10) gave two routes to an instance that is not the production one, and noted
they answer different questions:

- **Canvas Free-for-Teacher.** Hosted, free, real API and token. Confirms documented behaviour
  against real behaviour. Caveat: a scripted probe of its signup page 503s, so check in a
  browser; and it may default to New Quizzes, which would leave classic-quiz work unexercised.
- **Self-hosted `instructure/canvas-lms`.** AGPL-3.0, ships a Dockerfile. Heavier, and the only
  route that lets you manufacture pathological cases — a submission that changes between the dry
  run and the write, an object that reads back wrong. Those are what the refusal and read-back
  logic exist for and cannot be conjured on a live instance.

Also from GC_Agent: testing through the production edge does not exercise new code, because that
path runs a vendored, pinned guard. And if `grade-with-rubric` is ever exposed there, its
semantics should be settled before it is pinned, not after.

## Files a change would touch

`level2/canvas_api_operations.py` (the default, the definition format, the write shape),
`test_canvas_api_operations.py`, `level2/SKILL.md` and `level2/README.md` (the operator-facing
description), and the release pin. It is released behaviour, so it carries the IT review surface
that the authoring skill deliberately does not.
