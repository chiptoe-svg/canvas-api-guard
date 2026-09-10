# Assignments

The create, configure and publish arc for an assignment: what it takes to submit, where it sits
in the gradebook, whose dates it uses, and what happens when it already has student work attached
to it.

### Creating an assignment

**What Canvas does.** An assignment is created inside a course with a single required field, the
name. Everything else — how students submit, what it is worth, when it is due, whether it is
visible — is optional at creation time and can be set later with the same endpoint used to edit
it. If the assignment group is not specified, Canvas places the new assignment in "the top
assignment group in the course" rather than refusing the request.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/assignments` | Create an assignment |
| GET | `/api/v1/courses/:course_id/assignments/:id` | Get a single assignment |
| GET | `/api/v1/courses/:course_id/assignments` | List assignments |

**Parameters.**
- `assignment[name]` — string, marked `Required` in the documentation. No other create parameter
  carries that marker.
- `assignment[position]` — integer; "the position of this assignment in the group when
  displaying assignment lists."
- `assignment[assignment_group_id]` — integer; "defaults to the top assignment group in the
  course" if omitted.
- `assignment[points_possible]` — number; "the maximum points possible on the assignment."
- `assignment[grading_type]` — string; "the assignment defaults to 'points' if this field is
  omitted."
- `assignment[description]` — HTML body of the assignment.
- `assignment[notify_of_update]` — boolean; "if true, Canvas will send a notification to students
  in the class notifying them that the content has changed."

**Traps.**
- `assignment[name]` is the only field on the create endpoint marked `Required` in the
  documentation. Every other field — including `submission_types`, `points_possible`, and
  `grading_type` — is optional and takes a documented or implicit default rather than causing a
  validation error if left out (docs: https://canvas.instructure.com/doc/api/assignments.html).
- Leaving `assignment[assignment_group_id]` out does not fail the request; it silently files the
  new assignment into "the top assignment group in the course," which is a real, existing group
  and not a fallback bucket the caller controls (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- The documentation does not state a default for `submission_types` when it is omitted on create.
  Do not assume it defaults to `["none"]` or any other specific value without checking the
  created object's actual `submission_types` field (docs:
  https://canvas.instructure.com/doc/api/assignments.html — no default is documented for this
  field, unlike `assignment_group_id` and `grading_type`, which are).

**Source.** https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10

### Choosing how students turn it in

**What Canvas does.** `submission_types` is an array, and the documentation splits its ten
allowed values into two groups that are not meant to be mixed: five values for an assignment that
is not accepting online submissions, and five for one that is. Some values pull in other fields —
`external_tool` requires `external_tool_tag_attributes`, `student_annotation` requires
`annotatable_attachment_id`, and `online_upload` is what makes `allowed_extensions` take effect.
`quiz_lti` is a separate boolean that reconfigures `submission_types` for you, for courses using
the Quizzes 2 LTI tool rather than the classic `online_quiz` type.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/assignments` | Create an assignment |
| PUT | `/api/v1/courses/:course_id/assignments/:id` | Edit an assignment |

**Parameters.**
- `assignment[submission_types][]` — string. Extracted directly from the raw page, the full set
  of allowed values, grouped exactly as the documentation groups them:
  - If not allowing online submissions: `online_quiz`, `none`, `on_paper`, `discussion_topic`,
    `external_tool`
  - If allowing online submissions: `online_upload`, `online_text_entry`, `online_url`,
    `media_recording`, `student_annotation`
- `assignment[allowed_extensions][]` — string; "allowed extensions if submission_types includes
  'online_upload'."
- `assignment[external_tool_tag_attributes]` — "hash of external tool parameters if
  submission_types is `["external_tool"]`."
- `assignment[annotatable_attachment_id]` — integer; "only applies when submission_types includes
  'student_annotation'."
- `assignment[quiz_lti]` — boolean; "whether this assignment should use the Quizzes 2 LTI tool.
  Sets the submission type to 'external_tool' and configures the external tool attributes to use
  the Quizzes 2 LTI tool configured for this course."
- `assignment[turnitin_enabled]`, `assignment[vericite_enabled]` — booleans that "only appl[y]
  when the Turnitin/VeriCite plugin is enabled for a course and the submission_types array
  includes 'online_upload'."

**Traps.**
- The documentation states "unless the assignment is allowing online submissions, the array
  should only have one element" — this is guidance, not an enforced constraint the API is shown
  rejecting; the page does not describe what happens if you send, say,
  `["on_paper", "external_tool"]` together (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- `media_recording` is "only valid when the Kaltura plugin is enabled" — one of the ten allowed
  enum values is conditionally valid depending on account configuration, not universally usable
  (docs: https://canvas.instructure.com/doc/api/assignments.html).
- `quiz_lti` silently no-ops rather than erroring when there is nothing to configure: "has no
  effect if no Quizzes 2 LTI tool is configured" for the course (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- On the Edit endpoint specifically, `assignment[submission_types][]` appears twice in the
  documentation's own parameter table: once with the full ten-value enum and the note "only
  applies if the assignment doesn't have student submissions," and a second time marked
  `[DEPRECATED] Effective 2021-05-26 (notice given 2021-02-18)` with only that same restriction
  sentence and no enum shown. The page does not explain the duplication. Treat this as a rendering
  artifact of the documentation rather than evidence of two different parameters named the same
  thing (docs: https://canvas.instructure.com/doc/api/assignments.html).
- `allowed_extensions` only does anything "if submission_types includes 'online_upload'" — setting
  it alongside `on_paper` or `external_tool` is accepted but inert per the documented text (docs:
  https://canvas.instructure.com/doc/api/assignments.html).

**Source.** https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10

### Where it sits and what it is worth

**What Canvas does.** Every assignment belongs to exactly one assignment group
(`assignment_group_id`), and a group carries its own weight toward the final grade
(`group_weight`, "the percent of the total grade that this assignment group represents") plus its
own grading rules for dropping scores. An assignment's own `points_possible` is separate from
group weighting — it is the raw maximum score, not a share of anything. `grading_type` controls
how that score is interpreted and displayed, independent of both.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/assignment_groups` | List assignment groups |
| GET | `/api/v1/courses/:course_id/assignment_groups/:assignment_group_id` | Get an assignment group |
| POST | `/api/v1/courses/:course_id/assignment_groups` | Create an assignment group |
| PUT | `/api/v1/courses/:course_id/assignment_groups/:assignment_group_id` | Edit an assignment group |
| DELETE | `/api/v1/courses/:course_id/assignment_groups/:assignment_group_id` | Destroy an assignment group |

**Parameters.**
- `name`, `position`, `group_weight`, `sis_source_id`, `integration_data` — assignment group
  create/edit fields.
- `rules` — a `GradingRules` object: `drop_lowest` ("number of lowest scores to be dropped for
  each user"), `drop_highest` ("number of highest scores to be dropped for each user"),
  `never_drop` ("assignment IDs that should never be dropped").
- `move_assignments_to` — integer, delete-only; "the ID of an active Assignment Group to which the
  assignments that are currently assigned to the destroyed Assignment Group will be assigned."
- `assignment[points_possible]` — number; "the maximum points possible on the assignment."
- `assignment[grading_type]` — string. Extracted allowed values, exactly six:
  `pass_fail`, `percent`, `letter_grade`, `gpa_scale`, `points`, `not_graded`.
- `assignment[grading_standard_id]` — integer; "valid if grading_type is 'letter_grade' or
  'gpa_scale'."
- `assignment[omit_from_final_grade]` — boolean; "whether this assignment is counted towards a
  student's final grade."
- `assignment[hide_in_gradebook]` — boolean; "whether this assignment is shown in the gradebook."

**Traps.**
- Deleting an assignment group without `move_assignments_to` does not just remove an empty
  container: "if this argument is not provided, any assignments in this Assignment Group will be
  deleted." Deleting a group is a data-loss operation by default, not a reorganization one (docs:
  https://canvas.instructure.com/doc/api/assignment_groups.html).
- `assignment[grading_type]`'s six-value enum (extracted above) is not the same enum the peer
  review sub-object uses: `assignment[peer_review][grading_type]` allows only five of those six —
  `not_graded` is documented on the assignment's own `grading_type` but absent from the peer
  review one (docs: https://canvas.instructure.com/doc/api/assignments.html — the two "Allowed
  values" lists are on separate parameter rows on the same page).
- `assignment[grading_standard_id]`'s documented description text literally says "the grading
  standard id to set for the course" and "this will update the grading_type for the course to
  'letter_grade'" — on a parameter that sets a value on the assignment, not the course. This looks
  like copied text from the course-level grading-standard parameter; do not read it as evidence
  that setting this field on an assignment touches the course record (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- `omit_from_final_grade` (does this assignment count toward the grade at all) and
  `hide_in_gradebook` (is it shown in the gradebook UI) are two independently-documented booleans,
  not two names for the same switch — an assignment can be counted but hidden, or shown but not
  counted (docs: https://canvas.instructure.com/doc/api/assignments.html).
- `group_weight` is documented only as "the percent of the total grade that this assignment group
  represents." Nothing on this page states that group weights across a course are validated to
  sum to 100 — do not assume the API enforces that (docs:
  https://canvas.instructure.com/doc/api/assignment_groups.html).

**Source.** https://canvas.instructure.com/doc/api/assignment_groups.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10

### Dates, and giving one student different ones

**What Canvas does.** An assignment carries its own `due_at`/`unlock_at`/`lock_at`. To give a
different date to a subset of students, Canvas uses a separate `AssignmentOverride` object rather
than a second set of date fields on the assignment — an override targets one adhoc student list,
one group, or one section, and supplies its own dates. `only_visible_to_overrides` controls
whether students outside any override can see the assignment at all. `learning_object_dates.html`
documents a newer, unified `date_details` endpoint that reads and writes this same date/override
information for several object types, assignments included, through one shape.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/overrides` | List assignment overrides |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/overrides/:id` | Get a single assignment override |
| POST | `/api/v1/courses/:course_id/assignments/:assignment_id/overrides` | Create an assignment override |
| PUT | `/api/v1/courses/:course_id/assignments/:assignment_id/overrides/:id` | Update an assignment override |
| DELETE | `/api/v1/courses/:course_id/assignments/:assignment_id/overrides/:id` | Delete an assignment override |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/date_details` | Get a learning object's date information |
| PUT | `/api/v1/courses/:course_id/assignments/:assignment_id/date_details` | Update a learning object's date information |

**Parameters.**
- `assignment[due_at]`, `assignment[lock_at]`, `assignment[unlock_at]` — DateTime, ISO 8601.
  `due_at` "must be between the lock dates if there are lock dates"; `lock_at` "must be after the
  due date if there is a due date"; `unlock_at` is implied by the same relationship in reverse.
- `assignment[only_visible_to_overrides]` — boolean; "whether this assignment is only visible to
  overrides (only useful if 'differentiated assignments' account setting is on)."
- `assignment[assignment_overrides][]` — array of `AssignmentOverride`, settable directly on
  create/edit.
- `assignment_override[student_ids][]`, `assignment_override[title]`,
  `assignment_override[group_id]`, `assignment_override[course_section_id]`,
  `assignment_override[due_at]`, `assignment_override[unlock_at]`,
  `assignment_override[lock_at]` — the override object's own fields.
- `date_details` fields: `include[]`, `exclude[]`, `due_at`, `unlock_at`, `lock_at`,
  `only_visible_to_overrides`, `assignment_overrides[]`.

**Traps.**
- Creating an override: "one of student_ids, group_id, or course_section_id must be present. At
  most one should be present; if multiple are present only the most specific (student_ids first,
  then group_id, then course_section_id) is used and any others are ignored." Sending more than
  one target does not error — it silently drops all but the most specific one (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- `assignment_override[title]` is "required if student_ids is present, ignored otherwise (the
  title is set to the name of the targetted group or section instead)" — the same field is
  mandatory for one target type and meaningless for the other two (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- A `group_id` override additionally requires "the assignment MUST be a group assignment (a
  group_category_id is assigned to it)" — this target type has a precondition the other two do
  not (docs: https://canvas.instructure.com/doc/api/assignments.html).
- Updating date_details with a list of overrides is destructive by omission: "overrides not
  included in the list will be deleted." Sending a partial list to add one override removes every
  override you did not re-send (docs:
  https://canvas.instructure.com/doc/api/learning_object_dates.html).
- `only_visible_to_overrides` is explicitly conditional: "only useful if 'differentiated
  assignments' account setting is on." Setting it true on an account without that setting is
  accepted by the field's type but the documentation gives no indication it changes visibility
  (docs: https://canvas.instructure.com/doc/api/assignments.html).

**Source.** https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/learning_object_dates.html, fetched 2026-09-10

### Editing an assignment that already has submissions

**What Canvas does.** Most fields on an assignment can be changed with the same PUT endpoint used
to create it, whether or not students have already submitted. `submission_types` is the
documented exception. A related but separate accommodation — extra attempts for one student — is
its own small endpoint rather than a PUT to the assignment itself.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/assignments/:id` | Edit an assignment |
| POST | `/api/v1/courses/:course_id/assignments/:assignment_id/extensions` | Set extensions for student assignment submissions |

**Parameters.**
- `assignment[submission_types][]` — on the edit endpoint, documented "only applies if the
  assignment doesn't have student submissions."
- `assignment[allowed_attempts]` — integer; "the number of submission attempts allowed for this
  assignment. Set to -1 for unlimited attempts."
- `assignment[notify_of_update]` — boolean; "if true, Canvas will send a notification to students
  in the class notifying them that the content has changed."
- `assignment_extensions[][user_id]` — integer, `Required`; "the ID of the user we want to add
  assignment extensions for."
- `assignment_extensions[][extra_attempts]` — integer, `Required`; "number of times the student is
  allowed to re-take the assignment over the limit."

**Traps.**
- "Only applies if the assignment doesn't have student submissions" is stated as a condition, not
  as an error case — the documentation does not say the request is rejected when submissions
  exist, only that the change has no effect. A caller checking for a 4xx to detect this will not
  see one documented (docs: https://canvas.instructure.com/doc/api/assignments.html).
- Extensions are explicitly excluded for two submission shapes: "these cannot be set for
  discussion assignments or quizzes. For quizzes, use Quiz Extensions instead." — the extensions
  endpoint on this page does not cover every assignment type (docs:
  https://canvas.instructure.com/doc/api/assignment_extensions.html).
- The extensions endpoint documents its own error responses distinctly: "403 Forbidden if you are
  not allowed to extend assignments for this course" and "400 Bad Request if any of the
  extensions are invalid" — two different failure reasons collapsed into ordinary HTTP codes with
  no further documented detail on what makes an extension "invalid" (docs:
  https://canvas.instructure.com/doc/api/assignment_extensions.html).
- The page does not state how `extra_attempts` interacts with an assignment whose
  `allowed_attempts` is already `-1` (unlimited) — granting extra attempts on top of unlimited
  ones is not addressed (docs: https://canvas.instructure.com/doc/api/assignment_extensions.html;
  docs: https://canvas.instructure.com/doc/api/assignments.html).
- `notify_of_update`'s default when omitted is not documented on this page — do not assume editing
  an assignment with existing submissions is silent by default without checking the actual
  behavior (docs: https://canvas.instructure.com/doc/api/assignments.html).

**Source.** https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/assignment_extensions.html, fetched 2026-09-10

### Publishing and unpublishing

**What Canvas does.** An assignment's published state is a plain boolean field, `published`, not
a value inside `workflow_state` the way a course models it. Canvas separately exposes a read-only
flag, `unpublishable`, that tells the caller in advance whether an attempt to unpublish would even
be allowed.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/assignments/:id` | Edit an assignment |
| GET | `/api/v1/courses/:course_id/assignments/:id` | Get a single assignment |

**Parameters.**
- `assignment[published]` — boolean; "whether this assignment is published. (Only useful if
  'draft state' account setting is on.) Unpublished assignments are not visible to students."
- `unpublishable` — boolean, read-only, not a request parameter; "whether the assignment's
  'published' state can be changed to false. Will be false if there are student submissions for
  the assignment."
- `workflow_state` — string, read-only; the schema example shows a single value, `"unpublished"`.

**Traps.**
- `unpublishable` tells you the answer before you try: once an assignment has student submissions,
  `unpublishable` reads `false`. The documentation does not state what response code or error, if
  any, results from sending `assignment[published]: false` anyway once that flag is false — it
  documents the precondition, not the failure (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- Unlike a course, whose `workflow_state` is a documented four-value enum
  (`unpublished`/`available`/`completed`/`deleted`), this page never enumerates the full set of
  values `workflow_state` can take on an assignment — the only value shown anywhere on the page is
  the single example `"unpublished"`. Do not carry the course's four-value enum over to
  assignments; it is not documented here (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- `published` is explicitly qualified as "only useful if 'draft state' account setting is on" —
  the field exists regardless, but the documentation ties its effect to an account-level setting
  outside the assignment itself (docs: https://canvas.instructure.com/doc/api/assignments.html).

**Source.** https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10

### Peer review

**What Canvas does.** Peer review has two distinct, separately-documented layers on this page.
The older layer is a pair of booleans on the assignment (`peer_reviews`,
`automatic_peer_reviews`) plus a set of endpoints for manually or automatically assigning one
student's submission to another student as a reviewer. A newer, separate `assignment[peer_review]`
sub-object lets the peer review itself be graded, with its own points, grading type, and dates,
independent of the assignment's own grade.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/peer_reviews` | Get all peer reviews |
| GET | `/api/v1/sections/:section_id/assignments/:assignment_id/peer_reviews` | Get all peer reviews, by section |
| POST | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:submission_id/peer_reviews` | Create peer review |
| DELETE | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:submission_id/peer_reviews` | Delete peer review |
| POST | `/api/v1/courses/:course_id/assignments/:assignment_id/allocate` | Allocate peer review |

**Parameters.**
- `assignment[peer_reviews]` — boolean; "if submission_types does not include
  external_tool,discussion_topic, online_quiz, or on_paper, determines whether or not peer reviews
  will be turned on for the assignment."
- `assignment[automatic_peer_reviews]` — boolean; "whether peer reviews will be assigned
  automatically by Canvas or if teachers must manually assign peer reviews. Does not apply if peer
  reviews are not enabled."
- `include[]` on the list-peer-reviews endpoint: `submission_comments`, `user`.
- `user_id` — integer, `Required` on create; "user_id to assign as reviewer on this assignment."
- `assignment[peer_review][points_possible]` — number; "the maximum points possible for peer
  reviews."
- `assignment[peer_review][grading_type]` — string. Extracted allowed values, exactly five:
  `pass_fail`, `percent`, `letter_grade`, `gpa_scale`, `points`. "Defaults to 'points' if this
  field is omitted."
- `assignment[peer_review][due_at]`, `assignment[peer_review][lock_at]`,
  `assignment[peer_review][unlock_at]` — DateTime fields for the peer review's own schedule,
  separate from the assignment's.
- `assignment[peer_review][peer_review_overrides][]` — "list of overrides for the peer reviews."
- `PeerReview` object fields: `assessor_id`, `asset_id`, `asset_type`, `id`, `user_id`,
  `workflow_state`. "The state of the Peer Review, either 'assigned' or 'completed'."

**Traps.**
- `peer_reviews` has a documented no-op condition: it only does anything "if submission_types does
  not include external_tool, discussion_topic, online_quiz, or on_paper." Turning it on for an
  assignment with one of those four submission types is accepted but, per the documented text,
  does not turn peer review on (docs: https://canvas.instructure.com/doc/api/assignments.html).
- `automatic_peer_reviews` "does not apply if peer reviews are not enabled" — it depends on
  `peer_reviews` being true, and that field in turn depends on `submission_types` not being one of
  the four excluded values. Two chained preconditions, not one (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- `assignment[peer_review][grading_type]`'s five allowed values are not the same set as
  `assignment[grading_type]`'s six: `not_graded` is missing from the peer review sub-object's enum
  (docs: https://canvas.instructure.com/doc/api/assignments.html).
- `PeerReview.workflow_state` is documented as exactly two values, `assigned` and `completed` — a
  smaller, differently-named vocabulary than any other `workflow_state` this reference documents
  elsewhere (docs: https://canvas.instructure.com/doc/api/peer_reviews.html).
- The documentation for `create peer review` and `delete peer review` does not state whether
  either endpoint checks that `assignment[peer_reviews]` is actually enabled before acting — the
  precondition described above is documented for the boolean's effect on automatic assignment, not
  for manual create/delete (docs: https://canvas.instructure.com/doc/api/peer_reviews.html).

**Source.** https://canvas.instructure.com/doc/api/peer_reviews.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10

### Late and missing policy

**What Canvas does.** A late policy is scoped to a course as a whole, not to an individual
assignment — there is one late policy object per course, fetched, created, or patched through the
same three verbs on the same path. Two deduction mechanisms exist side by side and are
independently switched on: a flat deduction for a missing submission, and a per-interval deduction
for a late one, with an optional floor under how low a late submission's score can fall.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:id/late_policy` | Get a late policy |
| POST | `/api/v1/courses/:id/late_policy` | Create a late policy |
| PATCH | `/api/v1/courses/:id/late_policy` | Patch a late policy |

**Parameters.**
- `late_policy[missing_submission_deduction_enabled]` — boolean; "whether to enable the missing
  submission deduction late policy."
- `late_policy[missing_submission_deduction]` — number; "how many percentage points to deduct from
  a missing submission."
- `late_policy[late_submission_deduction_enabled]` — boolean; "whether to enable the late
  submission deduction late policy."
- `late_policy[late_submission_deduction]` — number; "how many percentage points to deduct per the
  late submission interval."
- `late_policy[late_submission_interval]` — string; "the interval for late policies." The schema
  example value is `"hour"`.
- `late_policy[late_submission_minimum_percent_enabled]` — boolean; "whether to enable the late
  submission minimum percent for a late policy."
- `late_policy[late_submission_minimum_percent]` — number; "the minimum grade a submissions can
  have in percentage points."

**Traps.**
- Creating a second late policy for a course fails outright: "if the course already has a late
  policy, a bad_request is returned since there can only be one late policy per course." The
  create and patch endpoints are not interchangeable once a policy exists — a second POST errors,
  where a PATCH is required to change it (docs:
  https://canvas.instructure.com/doc/api/late_policy.html).
- `late_submission_interval` has no `Allowed values` enum on this page — the only value shown
  anywhere is the schema example `"hour"`. Do not treat that example as a documented complete
  enumeration; nothing on the page states what other values, if any, are accepted (docs:
  https://canvas.instructure.com/doc/api/late_policy.html).
- `missing_submission_deduction` and `late_submission_deduction` are independent switches with
  independent `_enabled` flags — enabling one does not enable or imply the other, and a submission
  could in principle be both late and missing under two separately-configured deductions (docs:
  https://canvas.instructure.com/doc/api/late_policy.html).
- The late policy object itself carries no reference to any specific assignment — nothing in its
  schema (`id`, `course_id`, the deduction fields, `created_at`, `updated_at`) scopes it below the
  course, confirming it applies course-wide rather than per assignment (docs:
  https://canvas.instructure.com/doc/api/late_policy.html).

**Source.** https://canvas.instructure.com/doc/api/late_policy.html, fetched 2026-09-10

### Deleting an assignment

**What Canvas does.** Deletion is one endpoint with almost no documented behavior beyond its
name. The documentation states only that it deletes the given assignment and returns the deleted
Assignment object; it does not describe a soft-delete state, a change to `workflow_state`, or what
happens to existing submissions.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| DELETE | `/api/v1/courses/:course_id/assignments/:id` | Delete an assignment |

**Parameters.** None. The endpoint takes no body — only the course and assignment ids in the
path.

**Traps.**
- The entire documented description of this endpoint is "Delete the given assignment." There is
  no mention of `workflow_state`, no mention of a `deleted` value, and no mention of what happens
  to submissions that already exist. Do not assume this endpoint behaves like a course's
  documented `deleted` workflow state; nothing on this page says an assignment even has one (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- The endpoint's only documented output is that it "returns an Assignment object" — the same
  object shape as every other assignment endpoint, with no additional field or flag distinguishing
  a deleted assignment's representation from a live one (docs:
  https://canvas.instructure.com/doc/api/assignments.html).
- Deleting the assignment's own group has a separate, sharper documented effect than deleting the
  assignment itself: omitting `move_assignments_to` on assignment-group deletion deletes every
  assignment in that group, not just the group (docs:
  https://canvas.instructure.com/doc/api/assignment_groups.html — see "Where it sits and what it
  is worth" above).

**Source.** https://canvas.instructure.com/doc/api/assignments.html, fetched 2026-09-10
