# Rubric grading: review before the grade

Date: 2026-09-10
Branch: `feat/rubric-review-before-grade`
Status: design approved, not implemented. Revised 2026-09-18: the visibility decision is closed
(the tool switches the assignment to manual posting; the instructor releases with one click), and
the grade-entry verb is renamed `enter-rubric-grade`.
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
#   the assignment now posts manually (switched by this run if it did not already);
#   criteria and comments are in Canvas, hidden from every student; no grade exists anywhere
#   the instructor reviews in SpeedGrader
enter-rubric-grade --course-id 123 --assignment-id 20 --definition enter.json --dry-run
enter-rubric-grade --course-id 123 --assignment-id 20 --definition enter.json --yes
#   grades for the approved students are in Canvas, still hidden
#   the instructor clicks Post grades, then Graded, in the gradebook: grade, criteria and
#   comments appear together for those students, and nothing appears for the rest
```

Two consequences worth naming, because they are the point rather than side effects:

- **The review window is a real state in Canvas**, not a JSON dry run. Criteria stored, no grade.
  This is native Canvas behaviour with `use_for_grading` false, not something built here.
- **The grade is stated, not derived.** A late penalty, a cap, extra credit, or a criterion that
  does not apply this time are all expressible for the first time.
- **Nothing the tool does is ever visible to a student.** The assignment posts manually before
  the first criterion is written, and the one action that releases anything is the instructor's
  click in Canvas.

## Decisions

| Decision | Chosen | Why |
| --- | --- | --- |
| Shape | Two verbs, each taking a list of 1–50 students | One definition format per verb; the single/bulk split disappears; the operation count stays at eight |
| The total | Excludes `ignore_for_scoring` criteria, matching Canvas | The instructor approves from SpeedGrader, which shows Canvas's total; agreeing with it beats being internally consistent |
| Drift check | `expected_total`, a stated number per student | Readable in the definition; `grade` ≠ `expected_total` is how a penalty is expressed |
| Already-graded student | `enter-rubric-grade` refuses, naming what Canvas holds | The collision this workflow manufactures; changing a grade stays a guard call |
| `create-rubric` | Attaches with `use_for_grading: false`, no flag | One behaviour; the flag that makes a review window impossible should not be the default |
| An assignment that still auto-grades | `assess-with-rubric` refuses the whole run | If this is wrong, Canvas posts every grade the instant assess runs |
| Student visibility | `assess-with-rubric` switches the assignment to manual posting before it writes, unless told `--keep-post-policy`; the instructor releases with Post grades → Graded | The review window is private by construction and the tool never makes anything visible; the Everyone / Graded choice belongs to the person looking at the gradebook |
| The switch itself | One guard verb, `post-policy`, sending one fixed GraphQL mutation with two validated variables; read back through REST | There is no REST route; a verb that accepted a query the model composes would be unreviewable |
| Restoring automatic posting | Never done by the tool | Under automatic policy an assessed but ungraded submission is visible at once, which exposes exactly the students the instructor has not finished |
| Verb name | `enter-rubric-grade`, not `post-rubric-grade` | "Post" is the Canvas button that reveals grades, which this verb must never be mistaken for |
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

**The post-policy switch, before any criterion write.** If the assignment's `post_manually` is
false and the run was not given `--keep-post-policy`, the run calls the guard's `post-policy`
verb (see "The guard change") to set the assignment to manual posting, and the guard reads the
assignment back before returning. A switch that does not verify ends the run before the first
criterion is written. An assignment already posting manually is left alone and reported as such.
`--keep-post-policy` is the second flow: the assignment stays automatic, and every criterion and
comment is visible to its student the moment it is written, which the dry run says in words.

**Reported, never refused.** The post policy before and after the run and its visibility
consequence; each student's current grade; whether a stored assessment already exists for that
student, since this write replaces the criteria it names.

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

### `enter-rubric-grade`

**Definition** (`enter.json`):

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

Where such a criterion comes from, which tells the implementer where to get a fixture: only from
one linked to a Learning Outcome. `Rubric#generate_criteria` sets `ignore_for_scoring` solely
inside its `if criterion_data[:learning_outcome_id].present?` branch (source:
`app/models/rubric.rb#generate_criteria`), and it is not a documented request parameter at all —
the documented `RubricCriterion` fields are `id`, `description`, `long_description`, `points`,
`criterion_use_range` and `ratings`. So a rubric this tool creates can never carry the flag:
`criterion()` rejects unknown fields and therefore cannot send `learning_outcome_id`. The affected
case is an instructor who used "Find Outcome" in the Canvas rubric editor.

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
 "post_policy": {"before": "automatic", "after": "manual", "switched_by_this_run": true},
 "student_visibility": "hidden from every student until you click Post grades in the gradebook; this run writes no grade",
 "grades": [{"student_id": 4321, "student_name": "...",
             "criteria": {"_1234": {"points": 8, "comments": "Clear thesis."}},
             "criterion_total": 14, "points_possible": 20,
             "excluded_from_total": ["_1236"],
             "current_grade": {"workflow_state": "unsubmitted", "score": null,
                               "grade": null, "graded_at": null},
             "existing_assessment": false,
             "speedgrader_url": "..."}]}
```

`enter-rubric-grade` prints, per student, the stored criteria, the live sum, `expected_total`,
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

Setting the policy is not a REST action. Neither `post_manually` nor the deprecated `muted`
appears in the assignment's writable field list (source:
`lib/api/v1/assignment.rb#API_ALLOWED_ASSIGNMENT_INPUT_FIELDS`, line 605; `muted` is output-only
at line 255), and `config/routes.rb` has no REST route to post or hide grades. It is a GraphQL
action: `setAssignmentPostPolicy(assignmentId, postManually)` (source:
`app/graphql/mutations/set_assignment_post_policy.rb`), authorised on the course's
`manage_grades` right, refusing `postManually: false` on an anonymous assignment or an unpublished
moderated one, and otherwise calling `ensure_post_policy`, which writes the flag and nothing else
(source: `app/models/abstract_assignment.rb#ensure_post_policy`). Switching in either direction
neither posts nor hides an existing grade: `posted_at` is untouched. The one GraphQL route is
`POST /api/graphql` (source: `config/routes.rb`, line 36).

Two consequences of "the flag and nothing else":

- Grades written under manual posting stay hidden after a switch back to automatic, because an
  unposted graded submission is hidden under either policy. Restoring automatic is therefore not
  a release, and this tool never does it: an assessed but ungraded submission *is* visible under
  automatic policy, so restoring early exposes exactly the students the instructor has not
  finished. The instructor restores from the gradebook when the assignment is done, if they
  want to.
- The release is the instructor's click. Post grades offers **Everyone** and **Graded** (source:
  `app/graphql/mutations/post_assignment_grades.rb`, `graded_only`, over the `Submission.postable`
  scope). Graded reveals the students who have a grade and leaves the rest hidden, which is the
  triage this design produces. Everyone also marks ungraded submissions posted, after which a
  grade entered by hand shows the moment it is entered.

So the two flows are:

| | manual posting (default; switched by `assess`) | automatic, kept with `--keep-post-policy` |
| --- | --- | --- |
| `assess` writes criteria | hidden | student sees them immediately |
| you adjust in SpeedGrader | hidden | student sees the change |
| `enter-rubric-grade` writes grades | hidden | visible immediately |
| you hand-grade the rest | hidden | visible as entered |
| release | **you** click Post grades → Graded; grade, criteria and comments appear together | nothing to do |

**Decision.** The default is the first column. Automatic posting is not merely the unsafe
fallback — "here is my feedback on each criterion, the grade follows once I have read the whole
set" is a defensible way to teach — so the second column stays reachable, by a flag the dry run
names, on an assignment that already posts automatically. A forgotten click is the cost of the
first column: the work looks finished and no student has anything. Three things keep the
instructor oriented, none of them new machinery: the dry run and the `--yes` output state the
policy and the visibility in words; `enter-rubric-grade` ends with a count of grades written and
not yet visible; and "did I forget?" is one existing read:

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

### The post-policy verb

The guard gains one verb:

```sh
canvas_api_guard.py post-policy --course-id 123 --assignment-id 20 manual --dry-run
canvas_api_guard.py post-policy --course-id 123 --assignment-id 20 manual --yes
```

It sends `POST /api/graphql` with one fixed document, a module-level constant, and two variables
the guard validates itself — the assignment id as a string of digits, the policy as a boolean:

```graphql
mutation ($id: ID!, $manual: Boolean!) {
  setAssignmentPostPolicy(input: {assignmentId: $id, postManually: $manual}) {
    postPolicy { postManually }
  }
}
```

No other document can be sent. The verb takes no query text; `post` cannot address
`/api/graphql`, because `normalise_path` still prefixes `api/v1/` to everything; and the URL
builder admits that one path only when this verb asks for it. So the guard's statement to IT
stays "paths under `/api/v1/`, plus one fixed mutation string", not "GraphQL".

Its contract is the guard's usual one. Dry run: read the assignment, print the current and the
requested policy, send nothing. `--yes`: pre-read, send, then read the assignment back through
REST (`courses/123/assignments/20`, whose `post_manually` the serializer exposes
unconditionally) and compare. GraphQL reports a refusal as HTTP 200 with an `errors` array — an
anonymous assignment, a moderated one, a missing `manage_grades` right — and the guard treats
that as a refused write: exit 2, nothing changed, the message quoted. A 200 without `errors`
whose read-back does not show the requested policy is exit 3, and `WRITE STATUS UNCERTAIN` means
what it always means: read the assignment and ask, never resend. The audit record names the verb,
the assignment and both policies; the request body never reaches the log, as today.

The Codex rules file lists it with the other guard writes: it changes an assignment, so it prompts.

## Two items from the pilot review that land here

A Codex review of the codebase raised eight pre-pilot changes; they are specified on
`spec/guard-pilot-safety`. Two of them belong to this branch instead, because this change is what
creates the condition they describe.

**The Codex rules file.** `codex/canvas-api-guard.rules` lists `grade-with-rubric` and
`bulk-grade-with-rubric` in `OPERATION_PROMPTS`. Both are being retired, and `assess-with-rubric`
and `enter-rubric-grade` take their place. This is not bookkeeping: the offline suite reads those
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
  already the bulk shape. The enter definition is new.

## Files

| File | Change |
| --- | --- |
| `canvas_api_guard.py` | the named-exception table and its use in `compare_fields`; the logged-value cap; the `post-policy` verb with its one fixed document and REST read-back; version 1.18.0 → 1.19.0 |
| `test_canvas_api_guard.py` | verification tests for the new resolution, plus a regression test that wrappers are unchanged |
| `level2/canvas_api_operations.py` | remove `grade_with_rubric`, `bulk_grade_with_rubric`, `grade_one`, `verify_rubric_assessment`; add `assess_with_rubric` (with the post-policy switch step and `--keep-post-policy`), `enter_rubric_grade`, shared list validation and the criterion sum; `create_rubric` default; version 0.15.0 → 0.16.0 |
| `test_canvas_api_operations.py` | the operation tests below |
| `codex/canvas-api-guard.rules` | the retired verbs replaced in `OPERATION_PROMPTS`; the guard's `post-policy` verb added to its prompting list; the offline suite enforces both |
| `codex/skills/canvas-api-guard/SKILL.md` | the `post-policy` verb, inside the 130-line cap |
| `level2/SKILL.md` | the two verbs, the review window, the visibility statement, the release (Post grades → Graded, never done by the tool), the `use_for_grading` remedy |
| `level2/README.md` | the operations table |
| `docs/IT-REVIEW.md` | reviewed for anything that names the retired verbs; the one-fixed-mutation statement about `/api/graphql` |
| release pin | advanced only after asking the owner |

## Tests

Every regression test is red-proofed: demonstrated failing with only its fix reverted, before it
counts as evidence.

**Guard.** A `rubric_assessment`-only PUT whose read-back exposes matching criteria verifies,
one row per criterion ID. One criterion reading back wrong reports uncertain and names that
criterion. A read-back without `include[]` exposes nothing and is reported `UNVERIFIABLE`. The
confirmation lines name criteria by ID. Regression: `submission.posted_grade` still resolves to
`score`, and every existing wrapper is unaffected. `post-policy` sends the constant document and
only its two validated variables; a GraphQL `errors` array is exit 2 with the message quoted; a
clean 200 whose read-back still shows the old policy is exit 3; and `post` cannot reach
`/api/graphql`, because `normalise_path` prefixes `api/v1/`, which a test pins.

**Level 2.** A criterion flagged `ignore_for_scoring` on the live rubric is excluded from
`criterion_total` and from the sum `expected_total` is checked against, is reported in
`excluded_from_total`, and is still written and read back like any other criterion — the flag
changes the arithmetic, never what is stored. Assess sends no `submission` key. Assess refuses an assignment whose
`use_rubric_for_grading` is true, and the message names both remedy commands. Assess refuses an
unknown criterion, over-maximum points, duplicates, an empty list and 51 entries. A bad entry at
position three writes nothing at all. The dry run reports the post policy and the visibility
statement. Enter refuses a student with no stored assessment; refuses on an `expected_total`
mismatch, naming both numbers; refuses a student Canvas already scored, naming what it holds.
Enter writes `posted_grade` alone, and a grade that is not the sum is written and labelled. A
Canvas failure part-way through a pre-flighted batch raises `GuardUncertain` naming the count.
`create_rubric` attaches with `use_for_grading: false`. Assess on an automatic assignment performs
the switch before the first criterion write and reports the policy before and after; with
`--keep-post-policy` it does not, and the dry run says the criteria will be visible; on an
assignment already manual it does not, and says so; a switch the guard reports refused or
uncertain ends the run with no criterion written. Enter ends with the count of grades written and
not yet visible.

## The live gate

Merge waits on watching this happen once, in a sandbox course on the instance faculty actually
use. Source is not a hosted instance, at a release, with feature flags.

1. `POST /api/graphql` answers an ordinary instructor access token on the faculty instance, and
   `setAssignmentPostPolicy` succeeds for an instructor on a sandbox assignment; the REST read of
   that assignment then shows `post_manually` true.
2. With `use_for_grading` false, a rubric assessment written alone posts no grade — gradebook
   stays empty.
3. Under manual posting, the test student (Student View) sees no criterion, comment or grade
   during the window, and still nothing after `enter-rubric-grade`.
4. SpeedGrader shows the rubric filled in and leaves the grade box empty.
5. `include[]=assignment_associations` returns the association ID, and the flip to false works.
6. Comment text round-trips through the guard's comparison unescaped.
7. Post grades → Graded: the graded test student sees grade, criteria and comments together; an
   assessed but ungraded one still sees nothing.
8. Switching an automatic assignment to manual leaves a grade that was already posted visible.
9. The second flow, `--keep-post-policy` on an automatic assignment: the test student sees the
   criteria as soon as assess writes them, confirming the table's right-hand column.

Items 1 to 3 would invalidate the design if source and reality disagree. Testing through the
production edge does not exercise any of this: that path runs a vendored, pinned guard.

## Out of scope

Moderated grading, which solves several independent graders and one designated picker — a
different problem, deferred deliberately. Overall submission comments. Letter, percentage and
pass/fail grade strings, which stay reachable through the guard's own `PUT`. Posting grades
from the tool: the instructor's click is the release, by design. Restoring an assignment to
automatic posting, for the reason given above. The course-level post policy, untouched. Advancing
the release pin without asking.
