# Rubrics and grades

Building a rubric and attaching it to something, grading a submission with or without that
rubric, what a comment on a grade looks like, when a grade becomes visible to a student, how a
score becomes a letter, how grading periods scope a term, and how a final grade — including an
override of one — is read back. The last section is the read-only audit trail of every grade
change Canvas already recorded.

### Creating a rubric

**What Canvas does.** A rubric is created inside a course with a title and a `criteria` hash;
Canvas describes `rubric[criteria]` as "An indexed Hash of RubricCriteria objects where the keys
are integer ids and the values are the RubricCriteria objects" — the exact same sentence appears
on both the create and the update endpoint, and it is the only description of the parameter's
shape this page gives. Nowhere on the page is a literal bracket-nested request example shown for
`rubric[criteria]` — no `rubric[criteria][1][description]`, no worked query string. What the page
does show is the read-side shape: a `RubricCriterion` object (`id`, `description`,
`long_description`, `points`, `criterion_use_range`, `ratings`) and, nested inside it, a
`RubricRating` object (`id`, `criterion_id`, `description`, `long_description`, `points`) — the
same indexed-hash pattern the criteria description names, applied one level deeper for ratings,
but only ever shown as a response example, never as a request-parameter table entry.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/rubrics` | Create a single rubric |
| PUT | `/api/v1/courses/:course_id/rubrics/:id` | Update a single rubric |
| GET | `/api/v1/courses/:course_id/rubrics` | List rubrics in a course |
| GET | `/api/v1/courses/:course_id/rubrics/:id` | Get a single rubric |
| DELETE | `/api/v1/courses/:course_id/rubrics/:id` | Delete a single rubric |

**Parameters.**
- `rubric[title]` — string; "The title of the rubric."
- `rubric[free_form_criterion_comments]` — boolean; "Whether or not you can write custom comments
  in the ratings field for a rubric."
- `rubric[criteria]` — Hash; "An indexed Hash of RubricCriteria objects where the keys are integer
  ids and the values are the RubricCriteria objects."
- `rubric[skip_updating_points_possible]` — boolean, update-only; "Whether or not to update the
  points possible."
- `rubric_association_id` — integer; "The id of the rubric association object (not the
  course/assignment itself, but the join table record id). It can be used in place of
  `rubric_association[association_id]` and `rubric_association[association_type]` if desired."
- `include[]` — string, on `GET .../rubrics/:id`. Allowed values: `assessments`,
  `graded_assessments`, `peer_assessments`, `associations`, `assignment_associations`,
  `course_associations`, `account_associations`.
- `style` — string, on `GET .../rubrics/:id`; "Applicable only if assessments are being returned.
  If included, returns either all criteria data associated with the assessment, or just the
  comments. If not included, both data and comments are omitted." Allowed values: `full`,
  `comments_only`.
- `RubricCriterion` object fields (response): `id`, `description`, `long_description`, `points`,
  `criterion_use_range`, `ratings`.
- `RubricRating` object fields (response): `id`, `criterion_id`, `description`,
  `long_description`, `points`.

**Traps.**
- The `RubricCriterion` response example shows `"id": "_10"` and the `RubricRating` example shows
  `"id": "name_2"`, `"criterion_id": "_10"` — string ids with underscore prefixes, not the
  "integer ids" the `rubric[criteria]` description promises for the indexed hash's own keys. The
  page never reconciles the two: a top-level index key described as an integer id sits next to
  response objects whose own `id` field is a string (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- The object name is inconsistent on the same page: the `rubric[criteria]` parameter description
  calls the value type "RubricCriteria objects," but the response schema headed "A RubricCriterion
  object looks like" names it in the singular. Same object, two names, no cross-reference between
  them (docs: https://canvas.instructure.com/doc/api/rubrics.html).
- Ratings are nested inside a criterion only through the response example's `"ratings": null // the
  possible ratings for this Criterion` — the page gives no request-side description of how to key
  an individual rating when POSTing `rubric[criteria]`, unlike the grading-side `rubric_assessment`
  parameter (see "Grading against a rubric"), which does show a worked example (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- Repo-verified: the page never states a literal request-side key form for `rubric[criteria]` or
  its nested `ratings`, but this repo's own live-tested write does, and it resolves the "integer
  ids" contradiction above rather than sitting next to it. Both `criteria` and, inside each
  criterion, `ratings` are dicts keyed by `str(index)` from `enumerate` — stringified sequential
  indices, i.e. `"0"`, `"1"`, `"2"`, not arbitrary or meaningful ids and not the underscore-prefixed
  strings the response examples show. A criterion's own `ratings` follow the identical pattern one
  level deeper, so the full literal shape a writer sends is
  `rubric[criteria]["0"]["description"]`, `rubric[criteria]["0"]["points"]`,
  `rubric[criteria]["0"]["ratings"]["0"]["description"]`,
  `rubric[criteria]["0"]["ratings"]["0"]["points"]`, and so on for `"1"`, `"2"`, ... — what a
  writer sends (stringified indices) and what Canvas's own response examples show (`"_10"`,
  `"name_2"`) are not the same vocabulary; the writer's form is a stringified index, not an id
  Canvas assigns or expects back. A comment in the same code also records a second,
  live-observed fact: `free_form_criterion_comments` is only sent when true, because Canvas was
  observed storing `false` as `null` on a real rubric, which a strict read-back would otherwise
  flag as a mismatch — documentation states no default or storage behavior for this field at all
  (repo: `level2/canvas_api_operations.py`, the `rubric_body` function, line 191 for the
  index-keyed `criteria` construction and lines 193-194 for the observed
  `free_form_criterion_comments` behavior; repo: `test_canvas_api_operations.py`, lines 59-71,
  which assert the exact `{"0": {...}, "1": {...}}` shape for both `criteria` and nested
  `ratings`, and that `false` is omitted rather than sent).
- Both create and update return not a plain `Rubric` object but a hash of the form
  `{ 'rubric': Rubric, 'rubric_association': RubricAssociation }` — the page states this outright:
  "Unfortunately this endpoint does not return a standard Rubric object" (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- `rubric[skip_updating_points_possible]` exists only in the update endpoint's parameter table, not
  the create one — a newly created rubric always has its points recalculated from `criteria` (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- A rubric criterion can be linked to a learning outcome inside Canvas — this is where a rubric
  connects to accreditation reporting — but no field for that link is documented anywhere fetched
  for this reference. The `RubricCriterion` object above (see Parameters) lists exactly six fields,
  and none of them is an outcome id. `learning_outcome_id` and every other spelling tried
  (`outcome_id` as a criterion field, `mastery`, `mastery_points`, `alignment`, `aligned`,
  `ignore_for_scoring`, `outcome_group`) were searched for on `rubrics.html`, `outcomes.html`,
  `outcome_results.html`, and the master `all_resources.html` field index; none names a
  criterion-to-outcome link on any of them. Outcome results are their own separately documented
  report, keyed by `outcome_id`, not a field carried on a rubric criterion (docs:
  https://canvas.instructure.com/doc/api/outcome_results.html). Do not guess a field name for this
  link; read the `criteria` of a real outcome-linked rubric back from Canvas and inspect the keys it
  actually returns, rather than constructing one blind (docs:
  https://canvas.instructure.com/doc/api/rubrics.html; docs:
  https://canvas.instructure.com/doc/api/outcomes.html; docs:
  https://canvas.instructure.com/doc/api/all_resources.html).

**Source.** https://canvas.instructure.com/doc/api/rubrics.html, fetched 2026-09-10

### Attaching a rubric to something

**What Canvas does.** A `RubricAssociation` links a rubric to one `Assignment`, `Course`, or
`Account` and carries `purpose` (whether it is for grading or just a bookmark), `use_for_grading`,
and `hide_score_total`. It is its own resource with a dedicated create/update/delete endpoint,
separate from the rubric endpoint that can also embed an association at rubric-creation time.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/rubric_associations` | Create a RubricAssociation |
| PUT | `/api/v1/courses/:course_id/rubric_associations/:id` | Update a RubricAssociation |
| DELETE | `/api/v1/courses/:course_id/rubric_associations/:id` | Delete a RubricAssociation |

**Parameters.**
- `rubric_association[rubric_id]` — integer; "The id of the Rubric."
- `rubric_association[association_id]` — integer; "The id of the object with which this rubric is
  associated."
- `rubric_association[association_type]` — string; "The type of object this rubric is associated
  with." Allowed values: `Assignment`, `Course`, `Account`.
- `rubric_association[title]` — string; "The name of the object this rubric is associated with."
- `rubric_association[use_for_grading]` — boolean; "Whether or not the associated rubric is used
  for grade calculation."
- `rubric_association[hide_score_total]` — boolean; "Whether or not the score total is displayed
  within the rubric. This option is only available if the rubric is not used for grading."
- `rubric_association[purpose]` — string; "Whether or not the association is for grading (and thus
  linked to an assignment) or if it's to indicate the rubric should appear in its context." Allowed
  values, documented on the dedicated `rubric_associations` create endpoint: `grading`, `bookmark`.
- `rubric_association[bookmarked]` — boolean; "Whether or not the associated rubric appears in its
  context."

**Traps.**
- Canvas documents no read for a single rubric association: the only three endpoints named on this
  page for `rubric_associations` are `POST`, `PUT`, and `DELETE` — there is no `GET
  .../rubric_associations/:id` anywhere on `rubrics.html`. Fetching a newly created association
  back by id may 404 even though the association was created — this project's own documentation
  says so (repo: `level2/SKILL.md`; docs confirm no such GET is documented:
  https://canvas.instructure.com/doc/api/rubrics.html).
- `rubric_association[hide_score_total]` is conditional on its sibling: "This option is only
  available if the rubric is not used for grading" — setting `use_for_grading` and
  `hide_score_total` to true together is documented as contradictory (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- `rubric_association[purpose]` gets an explicit `Allowed values: grading, bookmark` line only on
  the dedicated `rubric_associations` create endpoint's own copy of the parameter table — the same
  field name embedded inside the rubric create/update endpoint's parameter table (see "Creating a
  rubric") carries no such enum line, only the description sentence (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- `rubric_association[association_type]`'s three allowed values are `Assignment`, `Course`, and
  `Account` — attaching a rubric to anything else (a section, a group) is not documented (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).

**Source.** https://canvas.instructure.com/doc/api/rubrics.html, fetched 2026-09-10

### Grading a submission

**What Canvas does.** One endpoint both comments on and grades a submission: `PUT
.../submissions/:user_id`. `submission[posted_grade]` is polymorphic — Canvas parses the same
string as points, a percentage, a letter grade, or a pass/fail keyword depending on its format,
against the assignment's own `grading_type`. A second, asynchronous path,
`.../submissions/update_grades`, grades many students in one call and hands back a `Progress`
object (see `references/fundamentals.md`) rather than the graded submissions directly.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id` | Grade or comment on a submission |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id` | Get a single submission |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions` | List submissions for an assignment |
| POST | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/update_grades` | Grade or comment on multiple submissions |
| POST | `/api/v1/courses/:course_id/submissions/update_grades` | Grade or comment on multiple submissions, course-wide |

**Parameters.**
- `submission[posted_grade]` — string. Four documented formats: points (a float or integer, e.g.
  `"13.5"`, "values above assignment.points_possible are allowed, for awarding extra credit"),
  percentage (e.g. `"40%"`, same extra-credit allowance above 100%), letter grade (per the
  assignment's grading scheme; "will be rejected if the assignment does not have a defined letter
  grading scheme"), and `"pass"`/`"complete"`/`"fail"`/`"incomplete"` (100% or 0%). "Assignments
  with grading_type of 'pass_fail' can only be assigned a score of 0 or
  assignment.points_possible, nothing inbetween."
- `submission[excuse]` — boolean; "Sets the 'excused' status of an assignment."
- `submission[late_policy_status]` — string; "Sets the late policy status to either 'late',
  'missing', 'extended', 'none', or null. NB: 'extended' values can only be set in the UI when the
  'UI features for extended Submissions' Account Feature is on."
- `submission[seconds_late_override]` — integer; "Sets the seconds late if late policy status is
  'late'."
- `submission[peer_review]` — boolean; "When true, updates the peer review sub assignment
  submission instead of the parent assignment submission... If any of these conditions are not
  met, the API will return a 422 error."
- `submission[sticker]` — string. Full enumeration extracted verbatim from the raw page, all 50
  values: `apple`, `basketball`, `bell`, `book`, `bookbag`, `briefcase`, `bus`, `calendar`, `chem`,
  `design`, `pencil`, `beaker`, `paintbrush`, `computer`, `column`, `pen`, `tablet`, `telescope`,
  `calculator`, `paperclip`, `composite_notebook`, `scissors`, `ruler`, `clock`, `globe`, `grad`,
  `gym`, `mail`, `microscope`, `mouse`, `music`, `notebook`, `page`, `panda1`, `panda2`, `panda3`,
  `panda4`, `panda5`, `panda6`, `panda7`, `panda8`, `panda9`, `presentation`, `science`, `science2`,
  `star`, `tag`, `tape`, `target`, `trophy`.
- `prefer_points_over_scheme` — boolean; "Treat posted_grade as points if the value matches a
  grading scheme value."
- `include[]` — string, on the grading endpoint. Allowed values: `submission_comments`,
  `visibility`, `sub_assignment_submissions`, `peer_review_submissions`, `provisional_grades`,
  `group`; "'submission_comments' is always included by default."
- `grade_data[<student_id>][posted_grade]`, `grade_data[<student_id>][excuse]`,
  `grade_data[<student_id>][rubric_assessment]` — bulk-grading equivalents; each documented as
  deferring to the single-submission endpoint's own documentation for the same argument.
- `grade_data[<assignment_id>][<student_id>]` — integer; "Specifies which assignment to grade. This
  argument is not necessary when using the assignment-specific endpoints."

**Traps.**
- `submission[posted_grade]` in `pass_fail` mode accepts a points or percentage value, but only if
  it equals exactly 0 or `points_possible`: "If a posted_grade in the 'points' or 'percentage'
  format is sent, the grade will only be accepted if the grade equals one of those two values."
  Anything in between is not clamped, it is rejected (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `submission[late_policy_status]`'s `"extended"` value is gated behind an account feature flag —
  sending it on an account without that flag turned on is not covered by the documented behavior
  (docs: https://canvas.instructure.com/doc/api/submissions.html).
- `submission[peer_review]=true` does not grade the parent assignment submission at all; it
  redirects the same PUT to "the peer review sub assignment submission instead," and returns "a 422
  error" if peer review allocation and grading is not fully configured for the course (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- The bulk `update_grades` endpoints are asynchronous: the response is a `Progress` object, not the
  graded submissions — the caller must poll `GET /api/v1/progress/:id` (see
  `references/fundamentals.md`) to find out whether the grades actually landed (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- Nothing on this page states whether writing `submission[posted_grade]` while the course's
  `post_manually` setting is true makes the grade visible immediately or leaves it unposted — see
  "Grade versus posted grade" (docs: https://canvas.instructure.com/doc/api/submissions.html — no
  interaction with `post_manually` is documented on this page).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### Grading against a rubric

**What Canvas does.** A rubric assessment scores a submission criterion by criterion, and it can
be written two documented ways: embedded in the same grading `PUT` used for a plain score (via the
`rubric_assessment` parameter), or through a dedicated
`.../rubric_associations/:rubric_association_id/rubric_assessments` endpoint. The two pages
document the sub-parameter shape differently. `submissions.html`'s worked example shows the full
pattern: given a rubric whose criteria have ids `crit1` and `crit2`, a caller sends
`rubric_assessment[crit1][points]=3&rubric_assessment[crit1][rating_id]=rat1&rubric_assessment[crit2][points]=5&rubric_assessment[crit2][rating_id]=rat2&rubric_assessment[crit2][comments]=Well%20Done.`
— the literal criterion id from the rubric's own `criteria` takes the place of the placeholder
`criterion_id` in each bracket.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id` | Grade a submission, including its `rubric_assessment` |
| POST | `/api/v1/courses/:course_id/rubric_associations/:rubric_association_id/rubric_assessments` | Create a single rubric assessment |
| PUT | `/api/v1/courses/:course_id/rubric_associations/:rubric_association_id/rubric_assessments/:id` | Update a single rubric assessment |
| DELETE | `/api/v1/courses/:course_id/rubric_associations/:rubric_association_id/rubric_assessments/:id` | Delete a single rubric assessment |

**Parameters.**
- `rubric_assessment` — Hash, on the grading `PUT`; "Assign a rubric assessment to this assignment
  submission. The sub-parameters here depend on the rubric for the assignment."
- `rubric_assessment[criterion_id][points]` — the points awarded for one criterion row. "For each
  criterion_id, change the id by the criterion number, ex: criterion_123."
- `rubric_assessment[criterion_id][rating_id]` — the rating id for the row; documented only on
  `submissions.html`'s embedded `rubric_assessment` parameter, not on `rubrics.html`'s dedicated
  `rubric_assessments` endpoint.
- `rubric_assessment[criterion_id][comments]` — comments to add for the row.
- `rubric_assessment[user_id]` — the user id being assessed, on the dedicated create endpoint.
- `rubric_assessment[assessment_type]` — string, on the dedicated create endpoint; "There are only
  three valid types: 'grading', 'peer_review', or 'provisional_grade'."
- `provisional` — string, optional; "Indicates whether this assessment is provisional, defaults to
  false."
- `final` — string, optional; "Indicates a provisional grade will be marked as final. It only takes
  effect if the provisional param is passed as true. Defaults to false."
- `graded_anonymously` — boolean, optional; "Defaults to false."

**Traps.**
- A rubric criterion is not a field of the submission object. The `Submission` object schema on
  `submissions.html` lists every field it carries — `assignment_id`, `assignment`, `course`,
  `attempt`, `body`, `grade`, `grade_matches_current_submission`, `html_url`, `preview_url`,
  `score`, `submission_comments`, `submission_type`, `submitted_at`, `url`, `user_id`, `grader_id`,
  `graded_at`, `user`, `late`, `assignment_visible`, `excused`, `missing`, `late_policy_status`,
  `points_deducted`, `seconds_late`, `workflow_state`, `extra_attempts`, `anonymous_id`,
  `posted_at`, `read_status`, `redo_request` — and none of them names a criterion or a rubric
  score. Proving a criterion was written requires reading the rubric assessment itself, not the
  submission — this project's own documentation says so (repo: `level2/README.md`; docs confirm
  the Submission schema carries no rubric field: https://canvas.instructure.com/doc/api/submissions.html).
- Two different documented shapes exist for the same-sounding sub-object: `rubrics.html`'s
  dedicated `rubric_assessments` endpoint documents only `[points]` and `[comments]` under
  `criterion_id`; `submissions.html`'s embedded `rubric_assessment` on the grading `PUT` documents
  `[points]`, `[rating_id]`, and `[comments]`, plus a full worked query-string example the other
  page lacks (docs: https://canvas.instructure.com/doc/api/rubrics.html; docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `criterion_id` in the parameter name is a literal placeholder, not something to send verbatim —
  "For each criterion_id, change the id by the criterion number, ex: criterion_123" (docs:
  https://canvas.instructure.com/doc/api/rubrics.html); the worked example on `submissions.html`
  uses the rubric's own arbitrary criterion ids, `crit1` and `crit2` (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- Omitting a criterion is a silent no-op, not a zero: "If the criterion_id is not specified it
  defaults to false, and nothing is updated" — a criterion left out of `rubric_assessment` keeps
  whatever it already scored rather than being cleared (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).
- `rubric_assessment[assessment_type]`'s three values (`grading`, `peer_review`,
  `provisional_grade`) match the `RubricAssessment` response object's own documented values for the
  same field — one of the few places in this reference where a request enum and a response enum
  for the same field are confirmed identical rather than merely similarly named (docs:
  https://canvas.instructure.com/doc/api/rubrics.html).

**Source.** https://canvas.instructure.com/doc/api/rubrics.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### Comments on a grade

**What Canvas does.** A comment rides on the same `PUT` used to grade a submission; there is no
separate create-comment endpoint documented on this page. A `SubmissionComment` is plain text, one
audio/video attachment, or a set of previously-uploaded files, optionally scoped to one attempt or
broadcast to a whole group.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id` | Comment on a submission |

**Parameters.**
- `comment[text_comment]` — string; "Add a textual comment to the submission."
- `comment[attempt]` — integer; "The attempt number (starts at 1) to associate the comment with."
- `comment[group_comment]` — boolean; "Whether or not this comment should be sent to the entire
  group (defaults to false). Ignored if this is not a group assignment or if no text_comment is
  provided."
- `comment[media_comment_id]` — string; "Add an audio/video comment to the submission... there is
  not yet an API to generate or list existing media comments."
- `comment[media_comment_type]` — string. Allowed values: `audio`, `video`.
- `comment[file_ids][]` — integer; "Attach files to this comment that were previously uploaded
  using the Submission Comment API's files action."
- `SubmissionComment` object fields (response): `id`, `author_id`, `author_name`, `author`,
  `comment`, `created_at`, `edited_at`, `media_comment`.

**Traps.**
- `comment[group_comment]` has two independent silent-no-op conditions in one sentence: "Ignored if
  this is not a group assignment or if no text_comment is provided" — setting it true on a
  non-group assignment, or without any text, does nothing (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `comment[file_ids][]` depends on "the Submission Comment API's files action" — a separate upload
  step this page names but does not itself document the parameters for; nothing fetched for this
  reference covers that action (docs: https://canvas.instructure.com/doc/api/submissions.html).
- The grading endpoint's own `include[]` parameter states "'submission_comments' is always included
  by default" — the one value in that enum documented as unconditionally present, unlike
  `visibility`, `provisional_grades`, or the other listed values (docs:
  https://canvas.instructure.com/doc/api/submissions.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### Grade versus posted grade

**What Canvas does.** A `Submission`'s `posted_at` is "nil if it has not been posted" —
posting is a distinct event from grading. At the course level, `course[post_manually]` is the one
documented switch that controls it: true means "all grades in the course must be posted manually,
and will not be automatically posted"; false (the default) means grades post automatically as they
are entered. The same setting is exposed a second time, under a different shape, on the dedicated
settings endpoint.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id` | Write a score or grade, which may or may not post immediately |
| PUT | `/api/v1/courses/:id` | Update a course, including `course[post_manually]` and `course[hide_final_grades]` |
| GET | `/api/v1/courses/:course_id/settings` | Get a course's settings |
| PUT | `/api/v1/courses/:course_id/settings` | Update a course's settings, including flat `post_manually`-shaped fields |

**Parameters.**
- `posted_at` — DateTime, `Submission` response field; "The date this submission was posted to the
  student, or nil if it has not been posted."
- `course[post_manually]` — boolean, on the course create/update endpoint; "Default is false. When
  true, all grades in the course must be posted manually, and will not be automatically posted.
  When false, all grades in the course will be automatically posted."
- `course[hide_final_grades]` — boolean, on the course create/update endpoint; "If this option is
  set to true, the totals in student grades summary will be hidden."
- `allow_final_grade_override` — boolean, on the settings endpoint; "Let student final grades for a
  grading period or the total grades for the course be overridden."
- `hide_final_grades` — boolean, on the settings endpoint (flat, not bracket-nested); "Hide totals
  in student grades summary."
- `grading_standard_enabled`, `grading_standard_id` — response fields on the settings `GET`.

**Traps.**
- None of the seven pages fetched for this reference documents a per-assignment or per-submission
  "post grades"/"hide grades" endpoint. Only the course-wide `course[post_manually]` switch is
  documented here; the field's own text on the update-course endpoint says "Use with caution as
  this setting will override any assignment level post policy" — confirming an assignment-level
  post policy exists in Canvas, while never documenting the endpoint that sets one, on this page or
  any other page fetched for this reference (docs:
  https://canvas.instructure.com/doc/api/courses.html).
- Nothing on either fetched page states whether writing `submission[posted_grade]` while
  `course[post_manually]` is true sets `posted_at` immediately or leaves it nil until a separate
  posting action — the interaction between the grading endpoint and the posting-policy setting is
  not documented on either page (docs: https://canvas.instructure.com/doc/api/submissions.html;
  docs: https://canvas.instructure.com/doc/api/courses.html).
- The same setting is shaped two different ways on two different endpoints: `course[post_manually]`
  is bracket-nested on the course create/update endpoint, while the settings endpoint's example
  response and its `hide_final_grades` field are flat, with no `course[...]` wrapper. The settings
  `GET` example response itself does not show `post_manually` or `allow_final_grade_override` among
  its listed keys, even though the settings `PUT` endpoint's own parameter table documents both
  (docs: https://canvas.instructure.com/doc/api/courses.html).
- `course[hide_final_grades]` hides only "the totals in student grades summary" — the field's own
  text says nothing about individual assignment grades or `posted_at`; do not conflate "hidden
  totals" with "unposted grades" (docs: https://canvas.instructure.com/doc/api/courses.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10

### What letter a score becomes

**What Canvas does.** A `GradingStandard` is a full CRUD resource at both course and account
scope, made of an ordered list of `GradingSchemeEntry` cutoffs (`name`, `value`); once created, it
is attached to a course through `course[grading_standard_id]` (an assignment attaches its own
separately — see `references/assignments.md`'s `assignment[grading_standard_id]`).

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/grading_standards` | Create a new grading standard |
| GET | `/api/v1/courses/:course_id/grading_standards` | List the grading standards available in a context |
| GET | `/api/v1/courses/:course_id/grading_standards/:grading_standard_id` | Get a single grading standard in a context |
| PUT | `/api/v1/courses/:course_id/grading_standards/:grading_standard_id` | Update a grading standard |
| DELETE | `/api/v1/courses/:course_id/grading_standards/:grading_standard_id` | Delete a grading standard |
| PUT | `/api/v1/courses/:id` | Update a course, including `course[grading_standard_id]` |

**Parameters.**
- `title` — string, `Required` on create; "The title for the Grading Standard."
- `points_based` — boolean; "Whether or not a grading scheme is points based. Defaults to false."
- `scaling_factor` — integer; "The factor by which to scale a percentage into a points based
  scheme grade... Defaults to 1. Not required for percentage based grading schemes."
- `grading_scheme_entry[][name]` — string, `Required` on create, not marked `Required` on update;
  "The name for an entry value within a GradingStandard that describes the range of the value, e.g.
  A-."
- `grading_scheme_entry[][value]` — integer, `Required` on both create and update; "The value for
  the name of the entry within a GradingStandard... e.g. 93."
- `course[grading_standard_id]` — integer; "The grading standard id to set for the course. If no
  value is provided for this argument the current grading_standard will be un-set from this
  course."
- `GradingStandard` object fields (response): `title`, `id`, `context_type`, `context_id`,
  `points_based`, `scaling_factor`, `grading_scheme`.
- `GradingSchemeEntry` object fields (response): `name`, `value`, `calculated_value`.

**Traps.**
- Updating is locked once the standard has graded something: "If the grading standard has been used
  for grading, only the title can be updated. The data, points_based, and scaling_factor cannot be
  modified once the grading standard has been used to grade assignments" (docs:
  https://canvas.instructure.com/doc/api/grading_standards.html).
- `grading_scheme_entry[][name]` carries the `Required` marker on the create endpoint's parameter
  table but not on the update endpoint's — only `grading_scheme_entry[][value]` stays `Required` in
  both (docs: https://canvas.instructure.com/doc/api/grading_standards.html).
- `course[grading_standard_id]`'s description text — "If no value is provided for this argument the
  current grading_standard will be un-set from this course" — is close to identical wording to
  `assignment[grading_standard_id]`'s own text documented in `references/assignments.md`; unlike
  that assignment-level case, this one is genuinely the course-level field the text describes, not
  copy-pasted from elsewhere (docs: https://canvas.instructure.com/doc/api/courses.html).
- `scaling_factor` is typed `integer` in the create/update parameter tables, but the
  `GradingStandard` response object's own example shows it as a float, `1.0` — the request table's
  stated type does not match the response schema's own example (docs:
  https://canvas.instructure.com/doc/api/grading_standards.html).

**Source.** https://canvas.instructure.com/doc/api/grading_standards.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10

### Grading periods

**What Canvas does.** A `GradingPeriod` carries its own `start_date`/`end_date`/`weight`, plus two
read-only fields Canvas computes: `close_date` ("Grades can only be changed before the close date
of the grading period") and `is_closed`. This page documents reading, updating, and deleting a
grading period, but no way to create one. Reading grades scoped to one period, rather than the
whole course, is a filter on the enrollments endpoint (see `references/fundamentals.md`).

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/grading_periods` | List grading periods |
| GET | `/api/v1/courses/:course_id/grading_periods/:id` | Get a single grading period |
| PUT | `/api/v1/courses/:course_id/grading_periods/:id` | Update a single grading period |
| DELETE | `/api/v1/courses/:course_id/grading_periods/:id` | Delete a grading period |
| GET | `/api/v1/courses/:course_id/enrollments` | List enrollments, filterable by `grading_period_id` |

**Parameters.**
- `grading_periods[][start_date]` — Date, `Required`; "The date the grading period starts."
- `grading_periods[][end_date]` — Date, `Required`; "no description" given.
- `grading_periods[][weight]` — number; "A weight value that contributes to the overall weight of a
  grading period set which is used to calculate how much assignments in this period contribute to
  the total grade."
- `close_date` — DateTime, response field; "Grades can only be changed before the close date of the
  grading period."
- `is_closed` — boolean, response field; "If true, the grading period's close_date has passed."
- `grading_period_id` — integer, on the enrollments list endpoint; "Return grades for the given
  grading_period. If this parameter is not specified, the returned grades will be for the whole
  course."

**Traps.**
- No `POST`/create endpoint appears anywhere on this page — only `GET`, `PUT`, and `DELETE` are
  documented. Creating a new grading period is not covered by this page's API surface at all (docs:
  https://canvas.instructure.com/doc/api/grading_periods.html).
- The `PUT` endpoint's own parameter table has no `title` field, even though `title` is a
  `GradingPeriod` object field shown in the response schema — the update endpoint's documented
  parameters (`start_date`, `end_date`, `weight`) do not include a way to rename a period (docs:
  https://canvas.instructure.com/doc/api/grading_periods.html).
- `close_date` and `is_closed` are read-only response fields; the update endpoint's parameter table
  gives no request-side way to set or extend a close date directly — only `start_date`/`end_date`
  are documented as settable (docs: https://canvas.instructure.com/doc/api/grading_periods.html).
- Omitting `grading_period_id` on the enrollments list does not default to the current grading
  period — it returns grades "for the whole course" (docs:
  https://canvas.instructure.com/doc/api/enrollments.html).

**Source.** https://canvas.instructure.com/doc/api/grading_periods.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/enrollments.html, fetched 2026-09-10

### Final grades, and overriding one

**What Canvas does.** An `Enrollment`'s `grades` hash (a `Grade` object) carries
`current_grade`/`final_grade`/`current_score`/`final_score`, and a set of `unposted_*` twins of
each that include muted or unposted assignments — visible only to users with grading permission.
Separately, the `Enrollment` object itself carries `override_grade`/`override_score` for the whole
course and `current_period_override_grade`/`current_period_override_score` for the active grading
period. `allow_final_grade_override` is a course setting that turns the override feature on.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/enrollments` | List enrollments, including `grades`, `override_grade`, and `override_score` |
| GET | `/api/v1/users/:user_id/enrollments` | List a user's enrollments, same response shape |
| PUT | `/api/v1/courses/:course_id/settings` | Update a course's settings, including `allow_final_grade_override` |

**Parameters.**
- `current_grade`, `final_grade`, `current_score`, `final_score` — `Grade` object fields; "Only
  included if user has permissions to view this grade/score."
- `current_points` — number, `Grade` object field; "Only included if user has permissions to view
  this score and 'current_points' is passed in the request's 'include' parameter."
- `unposted_current_grade`, `unposted_final_grade`, `unposted_current_score`,
  `unposted_final_score`, `unposted_current_points` — `Grade` object fields including
  muted/unposted assignments; "Only included if user has permissions to view this grade, typically
  teachers, TAs, and admins."
- `override_grade` — string, `Enrollment` field; "The user's override grade for the course."
- `override_score` — number, `Enrollment` field; "The user's override score for the course."
- `has_grading_periods` — boolean, `Enrollment` field, optional; "Indicates whether the course the
  enrollment belongs to has grading periods set up."
- `totals_for_all_grading_periods_option` — boolean, `Enrollment` field, optional.
- `current_grading_period_title`, `current_grading_period_id` — `Enrollment` fields, optional.
- `current_period_override_grade` — string, `Enrollment` field; "The user's override grade for the
  current grading period."
- `current_period_override_score` — number, `Enrollment` field; "The user's override score for the
  current grading period."
- `current_period_unposted_current_score`, `current_period_unposted_final_score`,
  `current_period_unposted_current_grade`, `current_period_unposted_final_grade` — `Enrollment`
  fields, optional, gated the same way as the course-wide `unposted_*` fields.
- `allow_final_grade_override` — boolean, settings endpoint; "Let student final grades for a
  grading period or the total grades for the course be overridden."

**Traps.**
- `allow_final_grade_override` only turns the override feature on for the course. None of the seven
  pages fetched for this reference documents a write endpoint or parameter for `override_grade`,
  `override_score`, `current_period_override_grade`, or `current_period_override_score` — all four
  appear solely as `Enrollment` response fields (docs:
  https://canvas.instructure.com/doc/api/enrollments.html; docs:
  https://canvas.instructure.com/doc/api/courses.html — the settings endpoint documents only the
  enabling switch, not a way to set the value).
- `current_points` and `unposted_current_points` are each gated by two conditions at once —
  grading permission, and the request's own `include[]=current_points` — omitting the include
  parameter hides the field even for a grader who could otherwise see it (docs:
  https://canvas.instructure.com/doc/api/enrollments.html).
- Every `unposted_*` and `current_period_unposted_*` field is gated by grading permission,
  "typically teachers, TAs, and admins" — a student reading their own enrollment does not get these
  fields even though the field names suggest they belong on the record itself (docs:
  https://canvas.instructure.com/doc/api/enrollments.html).
- The `current_period_*` fields are `null`, not omitted, "if the course the enrollment belongs to
  does not have grading periods, or if no currently active grading period exists" — a caller must
  check `has_grading_periods` and `current_grading_period_id` rather than treating a null override
  as "no override was set" (docs: https://canvas.instructure.com/doc/api/enrollments.html).

**Source.** https://canvas.instructure.com/doc/api/enrollments.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10

### Who changed a grade and when

**What Canvas does.** Gradebook history is read-only: every endpoint on this page is a `GET`. The
collated path drills down in three steps — days with grading activity, then the graders and
assignments active on one day, then the individual `SubmissionVersion`s for one grader/assignment
pair on that day — while a separate `feed` endpoint returns a flatter, paginated, optionally
user-filtered list across the whole course. A `SubmissionVersion` "contains all the fields that a
Submission object does, plus additional fields prefixed with current_*, new_*, and previous_*" —
one snapshot per graded change, not just the latest state.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/gradebook_history/days` | Days in gradebook history for this course |
| GET | `/api/v1/courses/:course_id/gradebook_history/:date` | Details for a given date in gradebook history |
| GET | `/api/v1/courses/:course_id/gradebook_history/:date/graders/:grader_id/assignments/:assignment_id/submissions` | Lists submission versions for one grader/assignment/date |
| GET | `/api/v1/courses/:course_id/gradebook_history/feed` | List uncollated submission versions |

**Parameters.**
- `date` — string, `Required` on the day-details and submissions endpoints.
- `grader_id` — integer, `Required` on the submissions endpoint.
- `assignment_id` — integer, `Required` on the submissions endpoint; optional filter on `feed`
  ("If absent, versions of submissions from any assignment in the course are included").
- `user_id` — integer, `feed` only; "If absent, versions of submissions from any user in the course
  are included."
- `ascending` — boolean, `feed` only; "Returns submission versions in ascending date order (oldest
  first). If absent, returns submission versions in descending date order (newest first)."
- `Day` object fields (response): `date`, `graders`.
- `Grader` object fields (response): `id`, `name`, `assignments`.
- `SubmissionVersion` object fields (response): `assignment_id`, `assignment_name`, `body`,
  `current_grade`, `current_graded_at`, `current_grader`, `grade_matches_current_submission`,
  `graded_at`, `grader`, `grader_id`, `id`, `new_grade`, `new_graded_at`, `new_grader`,
  `previous_grade`, `previous_graded_at`, `previous_grader`, `score`, `user_name`,
  `submission_type`, `url`, `user_id`, `workflow_state`.
- `SubmissionHistory` object fields (response): `submission_id`, `versions`.

**Traps.**
- Every endpoint on this page is `GET`. Gradebook history is a read of Canvas's own already-recorded
  grading activity, not a way to grade, regrade, or annotate anything (docs:
  https://canvas.instructure.com/doc/api/gradebook_history.html).
- The `feed` endpoint's `SubmissionVersion` is a narrower shape than the drilldown endpoint's own:
  "This SubmissionVersion objects will not include the new_grade or previous_grade keys, only the
  grade; same for graded_at and grader" — the same object name documents two different field sets
  depending on which endpoint returned it (docs:
  https://canvas.instructure.com/doc/api/gradebook_history.html).
- `feed`'s default order is "descending date order (newest first)" — a caller wanting the earliest
  grade change first must explicitly pass `ascending=true` (docs:
  https://canvas.instructure.com/doc/api/gradebook_history.html).
- There is no single call that returns "every grade change for user X across the whole history" in
  one shot: the collated days/day-details/submissions path requires walking date, then grader, then
  assignment in sequence, and even `feed`'s own `user_id` filter returns an uncollated, paginated
  list rather than a per-user summary (docs:
  https://canvas.instructure.com/doc/api/gradebook_history.html).

**Source.** https://canvas.instructure.com/doc/api/gradebook_history.html, fetched 2026-09-10
