# Rubric grading: review before the grade

Date: 2026-09-10
Branch: `feat/rubric-review-before-grade`
Status: design approved, not implemented.
Background, and what was already settled before this document: `docs/superpowers/2026-09-10-rubric-grading-change-notes.md`.

## The requirement

One grader. Everything visible in Canvas. Nothing final until a person approves the number.

The workflow this serves, in the owner's words: Codex grades a whole assignment against the
rubric, shows every criterion and every total, the instructor says "post the ones above 85",
those are written, and the instructor takes the rest by hand in SpeedGrader — where the rubric
is already filled in with points and comments, and the grade box is empty and theirs.

That workflow needs the assessment and the grade to be two separately targetable writes over
two different sets of students. Everything below follows from that.

## What changes for a person

Today one command writes the criteria and the grade together, and the grade is always the sum of
the criteria. After this change:

```sh
assess-with-rubric --course-id 123 --assignment-id 20 --definition assess.json --dry-run
assess-with-rubric --course-id 123 --assignment-id 20 --definition assess.json --yes
#   criteria and comments are now in Canvas; no grade exists anywhere
#   the instructor reviews in SpeedGrader
post-rubric-grade  --course-id 123 --assignment-id 20 --definition post.json --dry-run
post-rubric-grade  --course-id 123 --assignment-id 20 --definition post.json --yes
```

Two consequences worth naming, because they are the point rather than side effects:

- **The review window is a real state in Canvas**, not a JSON dry run. Criteria stored, no grade.
  This is native Canvas behaviour with `use_for_grading` false, not something built here.
- **The grade is stated, not derived.** A late penalty, a cap, extra credit, or a criterion that
  does not apply this time are all expressible for the first time.

## Decisions

| Decision | Chosen | Why |
| --- | --- | --- |
| Shape | Two verbs, each taking a list of 1–50 students | One definition format per verb; the single/bulk split disappears; the operation count stays at eight |
| The total | Excludes `ignore_for_scoring` criteria, matching Canvas | The instructor approves from SpeedGrader, which shows Canvas's total; agreeing with it beats being internally consistent |
| Drift check | `expected_total`, a stated number per student | Readable in the definition; `grade` ≠ `expected_total` is how a penalty is expressed |
| Already-graded student | `post-rubric-grade` refuses, naming what Canvas holds | The collision this workflow manufactures; changing a grade stays a guard call |
| `create-rubric` | Attaches with `use_for_grading: false`, no flag | One behaviour; the flag that makes a review window impossible should not be the default |
| An assignment that still auto-grades | `assess-with-rubric` refuses the whole run | If this is wrong, Canvas posts every grade the instant assess runs |
| Student visibility | **Open** — see below | Decided as report-never-refuse, then reopened: the premise that the only remedy was course-wide turned out to be wrong |
| Overall submission comment | Out of scope; per-criterion comments only | Already supported; an overall comment is one documented guard call |
| Guard verification | Teach the guard one named exception | The alternative proves a constant we sent and calls it verification |

## The two verbs

Both take `--course-id`, `--assignment-id`, `--definition`, and the existing mutually exclusive
`--dry-run` / `--yes`. Both accept 1–50 students. Grading one student is a one-entry list.

### Pre-flight, then write

Both verbs read and validate **every** entry before sending **any** write, and refuse the whole
run on any failure. Today's `bulk_grade_with_rubric` validates as it goes, so a bad tenth entry
turns an ordinary refusal into a partial write reported as `WRITE STATUS UNCERTAIN`. With reads
this cheap there is no reason for that.

The residual case — Canvas failing part-way through a batch that pre-flighted clean — keeps
today's semantics exactly: `GuardUncertain`, naming how many students were written, never
retried.

### `assess-with-rubric`

**Definition** (`assess.json`) — per student, this is today's `grade-with-rubric` payload:

```json
{"grades": [
  {"student_id": 4321,
   "criteria": {"_1234": {"points": 8, "comments": "Clear thesis."},
                "_1235": {"points": 6}}}
]}
```

Each criterion object requires `points`; `comments` and `rating_id` are optional. Unknown fields
are refused, as everywhere else in this program.

**Reads.** The course; the assignment (rubric criteria, `use_rubric_for_grading`,
`points_possible`, `html_url`, `post_manually`, and each criterion's `ignore_for_scoring`); and
each submission at
`?include[]=rubric_assessment&include[]=user`, which also carries `posted_at`.

**Refusals, before any write.**

1. The assignment has no attached rubric.
2. `use_rubric_for_grading` is true. The message names the fix, which needs no new code:
   ```
   get  "courses/123/rubrics/456?include[]=assignment_associations"
   put  courses/123/rubric_associations/789  {"rubric_association": {"use_for_grading": false}}
   ```
3. A criterion ID that is not in the assignment's live rubric.
4. Points above that criterion's maximum.
5. A duplicate student ID, an empty list, or more than 50 entries.

**Reported, never refused.** The course post policy and its visibility consequence; each
student's current grade; whether a stored assessment already exists for that student, since this
write replaces the criteria it names.

**The write**, per student:

```
PUT courses/123/assignments/20/submissions/4321?include[]=rubric_assessment&include[]=user
{"rubric_assessment": {"_1234": {"points": 8, "comments": "Clear thesis."}}}
```

No `submission` key at all. Canvas authorises this shape on `params[:submission] ||
params[:rubric_assessment]` and handles the assessment independently, forcing
`assessment_type: "grading"`; it answers 400 `invalid rubric_assessment` if the assignment has
no active rubric association or if no key matches a criterion ID
(source: `app/controllers/submissions_api_controller.rb`, lines 899 and 998). Both of those are
already refused above, before the request is built.

The `include[]=rubric_assessment` in the path is load-bearing: it is what puts the field in the
read-back the guard proves against. It is not decoration and there is a test on it.

### `post-rubric-grade`

**Definition** (`post.json`):

```json
{"grades": [{"student_id": 4321, "grade": 92, "expected_total": 92},
            {"student_id": 4322, "grade": 79, "expected_total": 87}]}
```

All three fields required, no optional fields. `grade` is a non-negative number. It may exceed
`points_possible`: Canvas documents values above it as extra credit. `expected_total` is the
criterion sum the assess run printed.

The second row is a late penalty: the criteria in Canvas sum to 87, the instructor is entering
79, and both numbers are visible in the file they approve.

**Reads.** The course; the assignment; each submission at
`?include[]=rubric_assessment&include[]=user`.

**The sum, and what it must agree with.** Both runs compute a total the same way: sum each
criterion's points, **excluding any criterion the live rubric flags `ignore_for_scoring`**, which
is exactly what Canvas does (source: `app/models/rubric.rb`, line 574 —
`criteria.reject { |c| c[:ignore_for_scoring] }.pluck(:points).compact.sum`; and
`app/models/rubric_association.rb#assess`). The flag is readable on the assignment's own `rubric`
array (source: `lib/api/v1/assignment.rb`, line 344, which slices `ignore_for_scoring` into each
row), so it costs no extra request — `live_rubric` already performs that read.

An earlier draft of this document argued the exclusion was unnecessary: this tool never creates
such a criterion, and the grade is posted explicitly, so Canvas's own sum is never consulted and
our two numbers would always be produced by the same rule. That is true and beside the point. The
instructor reviews in **SpeedGrader**, which shows *Canvas's* total. A rubric built in the Canvas
UI or imported from elsewhere can carry an `ignore_for_scoring` row, and then the number this tool
prints disagrees with the number on the screen the instructor is approving from — in a design
whose whole purpose is that they approve the number they reviewed. Matching Canvas is the point,
not internal consistency.

**Refusals, before any write.**

1. No stored rubric assessment for a named student — assess has not run for them.
2. The stored criteria sum differs from `expected_total` by more than `SCORE_TOLERANCE`. The
   message names the student, the stated total and the live one.
3. Canvas already holds a score for that student. The message names the score, the grade and
   `graded_at`. Deliberately changing an existing grade is a documented single call and stays
   the guard's: `put courses/123/assignments/20/submissions/4321 {"submission": {"posted_grade": N}}`.
4. A grade that is not a non-negative number, a duplicate student ID, an empty list, or more
   than 50 entries.

**The write**, per student:

```
PUT courses/123/assignments/20/submissions/4321?include[]=user
{"submission": {"posted_grade": 92}}
```

Proved by the guard's existing mapping of `posted_grade` to `entered_score`/`score`.

### Dry-run output

Both verbs print one object. `assess-with-rubric`:

```json
{"operation": "assess-with-rubric", "phase": "dry-run",
 "course_id": "123", "assignment_id": "20",
 "post_manually": false,
 "student_visibility": "criteria and comments become visible to each student when written; no grade is posted",
 "grades": [{"student_id": 4321, "student_name": "...",
             "criteria": {"_1234": {"points": 8, "comments": "Clear thesis."}},
             "criterion_total": 14, "points_possible": 20,
             "excluded_from_total": ["_1236"],
             "current_grade": {"workflow_state": "unsubmitted", "score": null,
                               "grade": null, "graded_at": null},
             "existing_assessment": false,
             "speedgrader_url": "..."}]}
```

`post-rubric-grade` prints, per student, the stored criteria, the live sum, `expected_total`,
`grade`, an explicit `difference` when the grade is not the sum, `points_possible`,
`current_grade` and `speedgrader_url`.

The `--yes` run prints the same object with `"phase": "yes"` and the written evidence.

## Student visibility during the review window

Source-confirmed, and a consequence this change introduces rather than inherits.

The submission API serves `rubric_assessment` only when `submission.user_can_read_grade?`
(source: `lib/api/v1/submission.rb`, line 145), which turns on `hide_grade_from_student?`
(source: `app/models/submission.rb#hide_grade_from_student?`, line 3246). On an assignment that
posts manually, that hides until `posted_at` is set. Otherwise it hides only when
`graded_or_resubmitted_without_posting?`, which is `(graded? || resubmitted?) && !posted?`
(source: same file, line 3238) — with a comment in the source saying it plainly: *"Only indicate
that the grade is hidden if there's an actual grade."*

The assess phase deliberately writes no grade. So on a course with the default automatic post
policy, nothing is hidden and the student can read every criterion score and comment while the
instructor is still deciding. `hide_comments_from_student?` (line 3256) has the identical shape.

Today's released behaviour never exposes this, because criteria and grade arrive together.

### The post policy is per assignment, and readable

An earlier draft of this document treated the remedy as course-wide and destructive. That was
wrong, and the correction matters enough to record.

`hash["post_manually"] = assignment.post_manually?` sits unconditionally in the assignment
serializer (source: `lib/api/v1/assignment.rb`, line 511) — not behind an `include[]`, not behind
an option. So `assess-with-rubric` reads the policy for the specific assignment, off a read it
already performs, and never guesses. `submission.posted_at` then states per student whether that
submission is actually released, which is stronger than reasoning from the policy.

Setting the policy is a gradebook action, not an API one. Neither `post_manually` nor the
deprecated `muted` appears in the assignment's writable field list (source:
`lib/api/v1/assignment.rb#API_ALLOWED_ASSIGNMENT_INPUT_FIELDS`, line 605; `muted` is output-only
at line 255). And there is no REST route to post or hide grades at all — `config/routes.rb`
matches nothing but `submissions/update_grades`, which is bulk *grading*. Whether Canvas offers
this outside REST was not established and is not claimed here.

So the two flows are:

| | posts automatically (default) | posts manually |
| --- | --- | --- |
| `assess` writes criteria | student sees them immediately | hidden |
| you adjust in SpeedGrader | student sees the change | hidden |
| `post-rubric-grade` writes grades | visible immediately | hidden |
| you hand-grade the rest | visible as entered | hidden |
| release | nothing to do | **you** click Post grades in the gradebook |

Manual posting makes the review window genuinely private and releases everything at one moment.
Its cost is the last row, which this tool cannot perform: if it is forgotten, the work looks
finished and no student has anything.

Automatic posting is not merely the unsafe fallback. "Here is my feedback on each criterion, the
grade follows once I have read the whole set" is a defensible way to teach.

**Open decision.** Whether `assess-with-rubric` refuses an automatic-post assignment, and how
hard `post-rubric-grade` works to keep the instructor oriented inside the manual flow. The
second may matter more: a refusal you cannot bypass is one bad day, a forgotten Post grades is a
week of students believing they were not graded. Three things the tool can do either way, none of
them new machinery — report each student's `posted_at` after writing; end a `post-rubric-grade`
run with a count of grades written and not visible; and answer "did I forget?" with one existing
read:

```sh
canvas_api_guard.py get "courses/123/assignments/20/submissions?per_page=100" \
  --all-pages --fields user_id,score,posted_at
```

## The guard change

An assess write cannot be proved by the guard as it stands, and would exit 3 on every student.

`compare_fields` (`canvas_api_guard.py:706`) rests on the assumption stated in its own docstring:
Canvas wraps a write body in a resource key while the read-back object does not. So it flattens
the body, takes the last path segment as the field name, and looks that name up at the top level
of the response. `{"rubric_assessment": {"_1234": {"points": 8}}}` flattens to the field `points`,
which is not a field of the submission object. Nothing is provable, and `canvas_api_guard.py:1050`
correctly reports `WRITE STATUS UNCERTAIN`. It also degrades the confirmation lines — printed to
stderr even under `--yes` (`confirm`, line 622), so shown for every student in the run — into
repeated rows all labelled `points`, with no criterion ID to tell them apart.

`rubric_assessment` breaks both halves of the assumption: it is not a wrapper to strip, it *is*
the response field, and its values sit one level deeper, keyed by criterion ID.

**The change.** A short module-level table names body keys that are response fields rather than
resource wrappers; `rubric_assessment` is its only entry. For such a key, `compare_fields` emits
one row per sub-key instead of flattening to a leaf name:

- `field` and `read_field`: `rubric_assessment.<criterion_id>`
- `requested`: the criterion object as sent
- `before` / `after`: the same path read out of the before and after objects
- `match`: `matches(requested, after)` when the response exposes it, otherwise `None`

`matches` (line 683) already compares dicts member by member, already applies numeric tolerance,
and already treats a key the response omits as unknown rather than false. The comparison logic
is not new; only the path resolution is.

Nothing else changes. `submission`, `rubric`, `quiz` and every other wrapper resolve exactly as
they do today, and there is a regression test saying so.

Two known edges:

- The guard proves the criteria only when the write path carries `?include[]=rubric_assessment`.
  Without it the response omits the field, every row is unknown, and the write is correctly
  reported uncertain. Level 2 always builds the path that way; a test enforces it.
- The comparison includes comment text. If Canvas returns a comment HTML-escaped or otherwise
  normalised, a row reads back false and a successful write is reported uncertain. This is item 5
  of the live gate. If it bites, the fix is to compare `points` structurally and leave comment
  text unproven.

**Level 2 gets smaller.** `verify_rubric_assessment` exists only because the guard could not do
this; it goes.

Rejected: using the dedicated `rubric_assessments` endpoint so that `assessment_type` — a
constant we send that happens to be a response field — satisfies the guard without modifying it.
That would print `verification: passed` for a write in which no criterion was observed to land.

## Two items from the pilot review that land here

A Codex review of the codebase raised eight pre-pilot changes; they are specified on
`spec/guard-pilot-safety`. Two of them belong to this branch instead, because this change is what
creates the condition they describe.

**The Codex rules file.** `codex/canvas-api-guard.rules` lists `grade-with-rubric` and
`bulk-grade-with-rubric` in `OPERATION_PROMPTS`. Both are being retired, and `assess-with-rubric`
and `post-rubric-grade` take their place. This is not bookkeeping: the offline suite reads those
lists against both argparse parsers, so a command nobody classified fails the tests — which is
the point of writing them that way.

**Cap the free text the audit log records.** `emit` (`canvas_api_guard.py:789`) logs the
`changes` rows, and each row carries `requested`, `before` and `after`. Today a grading write's
values are numbers. After this change they include per-criterion comments: instructor free text
about a named student, written into an append-only log with no retention. The rest of the audit
design is careful about exactly this — request bodies never reach the log, and `:228` states that
response bodies and the token never do either — so the gap is new and this branch opens it.

Cap any value recorded in a `changes` row at a named constant, with an explicit truncation
marker. The cap applies to what is **logged** only. `matches` still compares the full value, and
stdout evidence still carries it: the instructor reading the confirmation sees the whole comment,
and only the durable record is shortened. Retention for that record is specified separately, on
`spec/guard-pilot-safety`.

## What breaks

- `grade-with-rubric` and `bulk-grade-with-rubric` no longer exist. A pinned copy calling them
  fails loudly with argparse's `invalid choice` rather than silently doing half the job.
- `create-rubric --assignment-id` attaches with `use_for_grading: false`. Rubrics already
  attached are unaffected until someone flips them; `assess-with-rubric` refuses those and says
  how.
- The assess definition is today's per-student payload wrapped in `{"grades": [...]}`, which is
  already the bulk shape. The post definition is new.

## Files

| File | Change |
| --- | --- |
| `canvas_api_guard.py` | the named-exception table and its use in `compare_fields`; the logged-value cap; version 1.17.0 → 1.18.0 |
| `test_canvas_api_guard.py` | verification tests for the new resolution, plus a regression test that wrappers are unchanged |
| `level2/canvas_api_operations.py` | remove `grade_with_rubric`, `bulk_grade_with_rubric`, `grade_one`, `verify_rubric_assessment`; add `assess_with_rubric`, `post_rubric_grade`, shared list validation and the criterion sum; `create_rubric` default; version 0.15.0 → 0.16.0 |
| `test_canvas_api_operations.py` | the operation tests below |
| `codex/canvas-api-guard.rules` | the retired verbs replaced in `OPERATION_PROMPTS`; the offline suite enforces it |
| `level2/SKILL.md` | the two verbs, the review window, the visibility statement, the `use_for_grading` remedy |
| `level2/README.md` | the operations table |
| `docs/IT-REVIEW.md` | reviewed for anything that names the retired verbs |
| release pin | advanced only after asking the owner |

## Tests

Every regression test is red-proofed: demonstrated failing with only its fix reverted, before it
counts as evidence.

**Guard.** A `rubric_assessment`-only PUT whose read-back exposes matching criteria verifies,
one row per criterion ID. One criterion reading back wrong reports uncertain and names that
criterion. A read-back without `include[]` exposes nothing and is reported `UNVERIFIABLE`. The
confirmation lines name criteria by ID. Regression: `submission.posted_grade` still resolves to
`score`, and every existing wrapper is unaffected.

**Level 2.** A criterion flagged `ignore_for_scoring` on the live rubric is excluded from
`criterion_total` and from the sum `expected_total` is checked against, is reported in
`excluded_from_total`, and is still written and read back like any other criterion — the flag
changes the arithmetic, never what is stored. Assess sends no `submission` key. Assess refuses an assignment whose
`use_rubric_for_grading` is true, and the message names both remedy commands. Assess refuses an
unknown criterion, over-maximum points, duplicates, an empty list and 51 entries. A bad entry at
position three writes nothing at all. The dry run reports the post policy and the visibility
statement. Post refuses a student with no stored assessment; refuses on an `expected_total`
mismatch, naming both numbers; refuses a student Canvas already scored, naming what it holds.
Post writes `posted_grade` alone, and a grade that is not the sum is written and labelled. A
Canvas failure part-way through a pre-flighted batch raises `GuardUncertain` naming the count.
`create_rubric` attaches with `use_for_grading: false`.

## The live gate

Merge waits on watching this happen once, in a sandbox course on the instance faculty actually
use. Source is not a hosted instance, at a release, with feature flags.

1. With `use_for_grading` false, a rubric assessment written alone posts no grade — gradebook
   stays empty.
2. What the test student can see during the window.
3. SpeedGrader shows the rubric filled in and leaves the grade box empty.
4. `include[]=assignment_associations` returns the association ID, and the flip to false works.
5. Comment text round-trips through the guard's comparison unescaped.
6. The same two, one assignment set to post manually and one left automatic, confirming the
   visibility table above from the student's side.

Items 1 and 2 would invalidate the design if source and reality disagree. Testing through the
production edge does not exercise any of this: that path runs a vendored, pinned guard.

## Out of scope

Moderated grading, which solves several independent graders and one designated picker — a
different problem, deferred deliberately. Overall submission comments. Letter, percentage and
pass/fail grade strings, which stay reachable through the guard's own `PUT`. Assignment-level
post policies, which have no documented REST endpoint. Advancing the release pin without asking.
