# Quizzes

The Classic Quiz arc: building a quiz shell, filling it with questions and question groups,
controlling what it is worth, what a student sees while taking it and afterwards, giving one
student different access, publishing it, and reading back attempts, statistics and reports. This
reference covers Classic Quizzes only; the last section explains why New Quizzes is out of scope.

### Creating the quiz shell

**What Canvas does.** A quiz is created inside a course with a title; everything else is
optional at creation and editable later with the same endpoint. `quiz_type` decides whether the
quiz is graded at all: `assignment` and `graded_survey` are graded types and can carry an
`assignment_group_id` — Canvas ties the quiz to an assignment group only "if the quiz is graded,
i.e. if quiz_type is 'assignment' or 'graded_survey'." `practice_quiz` and `survey` are ungraded
and never place anything in an assignment group. `anonymous_submissions` layers on top of that
split again, but along a different axis: it only applies to `graded_survey` and `survey` — the
two survey-shaped types, one graded and one not — not to `assignment` or `practice_quiz`.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/quizzes` | Create a quiz |
| GET | `/api/v1/courses/:course_id/quizzes` | List quizzes in a course |
| GET | `/api/v1/courses/:course_id/quizzes/:id` | Get a single quiz |
| PUT | `/api/v1/courses/:course_id/quizzes/:id` | Edit a quiz |
| DELETE | `/api/v1/courses/:course_id/quizzes/:id` | Delete a quiz |

**Parameters.**
- `quiz[title]` — string, `Required`.
- `quiz[description]` — string.
- `quiz[quiz_type]` — string. Allowed values: `practice_quiz`, `assignment`, `graded_survey`,
  `survey`.
- `quiz[assignment_group_id]` — integer; "Defaults to the top assignment group in the course.
  Only valid if the quiz is graded."
- `quiz[notify_of_update]` — boolean, edit-only; "If true, notifies users that the quiz has
  changed. Defaults to true."
- `search_term` — string, list-only; "The partial title of the quizzes to match and return."
- `question_types` — array (response field on the Quiz object), e.g. `["multiple_choice",
  "essay"]`.
- `anonymous_submissions` — boolean (response field); "Whether survey submissions will be kept
  anonymous (only applicable to 'graded_survey', 'survey' quiz types)."

**Traps.**
- `quiz[assignment_group_id]` is conditional, not just defaulted: it only takes effect "if the
  quiz is graded, i.e. if quiz_type is 'assignment' or 'graded_survey'" — sending it on a
  `practice_quiz` or `survey` is accepted syntactically but the documented condition says it does
  nothing (docs: https://canvas.instructure.com/doc/api/quizzes.html).
- `anonymous_submissions` does not follow the graded/ungraded split that `assignment_group_id`
  follows. It is documented against `graded_survey` and `survey` — one graded type, one ungraded
  — not against `assignment` and `practice_quiz`. Reading "graded vs. ungraded" as the axis that
  controls every `quiz_type`-conditional field is wrong; two different splits are in play (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- `quiz[notify_of_update]` appears only in the edit endpoint's parameter table, under "Additional
  arguments" — it is not a create parameter, and the documentation gives no default for it at
  creation time because there is no notification to send on a brand-new quiz (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- `search_term` exists only on the list endpoint. The single-quiz `GET` takes no query
  parameters at all — there is nothing to narrow, only an id to fetch (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).

**Source.** https://canvas.instructure.com/doc/api/quizzes.html, fetched 2026-09-10

### Adding questions

**What Canvas does.** A question belongs to a quiz (or to a quiz group inside it) and is created
or edited through its own endpoint, separate from the quiz endpoint. `question[question_type]`
selects one of twelve documented types, and "multiple optional fields depend upon the type of
question to be used" — those fields live inside `question[answers]`, an array of `Answer`
objects. The `Answer` schema shown on this page is one shared shape reused across every
question type; most of its fields are tagged in the documentation as belonging to one or two
specific types, and the rest — `answer_text` and `answer_weight` — are generic and carry no such
tag.

Every documented `question_type` value and what the `Answer` schema says about its `answers[]`
entries, extracted verbatim from the page:

| `question_type` | `answers[]` shape |
| --- | --- |
| `calculated_question` | No field on this page's `Answer` object is tagged for it. Nothing here documents how a calculated question's variables or formula are submitted through `question[answers]`. |
| `essay_question` | None — no `Answer` field is tagged for it; an essay question takes no predefined answers. |
| `file_upload_question` | None — no `Answer` field is tagged for it; the student's response is an upload, not an `Answer` entry. |
| `fill_in_multiple_blanks_question` | `answer_text`, `answer_weight`, `blank_id` — `blank_id` is documented "Used in fill in multiple blank and multiple dropdowns questions." |
| `matching_question` | `answer_match_left`, `answer_match_right`, `matching_answer_incorrect_matches` — all three documented "Used in matching questions." |
| `multiple_answers_question` | `answer_text`, `answer_weight` — no type-specific field is tagged for it. |
| `multiple_choice_question` | `answer_text`, `answer_weight` — no type-specific field is tagged for it. |
| `multiple_dropdowns_question` | `answer_text`, `answer_weight`, `blank_id` — same tag as `fill_in_multiple_blanks_question`. |
| `numerical_question` | `numerical_answer_type` (`exact_answer`, `range_answer`, or `precision_answer`), plus `exact`/`margin` (for `exact_answer`), `approximate`/`precision` (for `precision_answer`), `start`/`end` (for `range_answer`). |
| `short_answer_question` | `answer_text`, `answer_weight` — no type-specific field is tagged for it. |
| `text_only_question` | None — it carries no answers; it is a block of text shown between questions, not itself gradeable. |
| `true_false_question` | `answer_text`, `answer_weight` — no type-specific field is tagged for it. |

Two more `Answer` fields are generic rather than type-tagged: `id` ("Do not supply if this answer
is part of a new question") and `answer_comments` (a per-answer comment shown to the student).
One field, `text_after_answers`, is tagged "Used in missing word questions" — see the trap below.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/questions` | List questions in a quiz or a submission |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/questions/:id` | Get a single quiz question |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/questions` | Create a single quiz question |
| PUT | `/api/v1/courses/:course_id/quizzes/:quiz_id/questions/:id` | Update an existing quiz question |
| DELETE | `/api/v1/courses/:course_id/quizzes/:quiz_id/questions/:id` | Delete a quiz question |
| POST | `/api/v1/courses/:course_id/quizzes/:id/reorder` | Reorder quiz items |

**Parameters.**
- `question[question_name]`, `question[question_text]` — string.
- `question[quiz_group_id]` — integer; "The id of the quiz group to assign the question to."
- `question[question_type]` — string. Allowed values: `calculated_question`, `essay_question`,
  `file_upload_question`, `fill_in_multiple_blanks_question`, `matching_question`,
  `multiple_answers_question`, `multiple_choice_question`, `multiple_dropdowns_question`,
  `numerical_question`, `short_answer_question`, `text_only_question`, `true_false_question`.
- `question[position]` — integer.
- `question[points_possible]` — integer.
- `question[correct_comments]`, `question[incorrect_comments]`, `question[neutral_comments]` —
  string.
- `question[text_after_answers]` — string, "no description" given.
- `question[answers]` — `[Answer]`, "no description" given.
- `answer_text`, `answer_weight`, `answer_comments`, `text_after_answers`, `answer_match_left`,
  `answer_match_right`, `matching_answer_incorrect_matches`, `numerical_answer_type`, `exact`,
  `margin`, `approximate`, `precision`, `start`, `end`, `blank_id` — `Answer` object fields, see
  the table above for which type each belongs to.
- `order[][id]` — integer, `Required`; "The associated item's unique identifier."
- `order[][type]` — string; "The type of item is either 'question' or 'group'." Allowed values:
  `question`, `group`.
- `id` — integer, `Required` on get/delete; "The quiz question unique identifier."
- `quiz_submission_id`, `quiz_submission_attempt` — integer, list-only; scope the question list
  to what was presented in one submission attempt rather than the quiz's current question set.

**Traps.**
- `calculated_question` has no documented `answers[]` shape at all on this page. `variables` and
  `formulas` exist, but only as read-only fields on the separate `AssessmentQuestion` object
  documented on the question banks page — nothing here documents submitting them through
  `question[answers]` on this create endpoint (docs:
  https://canvas.instructure.com/doc/api/quiz_questions.html; docs:
  https://canvas.instructure.com/doc/api/assessment_question_banks.html).
- `text_after_answers` is documented "Used in missing word questions," but `missing_word_question`
  is not one of the twelve `question_type` values this page enumerates. The field's own
  description does not name which of the twelve types it belongs to (docs:
  https://canvas.instructure.com/doc/api/quiz_questions.html).
- `question[answers]` and the top-level `question[text_after_answers]` parameter share a name
  with the `Answer` object's own `text_after_answers` field — the create endpoint's own parameter
  table lists both `question[text_after_answers]` and `question[answers]` side by side with no
  further explanation of how the two relate (docs:
  https://canvas.instructure.com/doc/api/quiz_questions.html).
- `blank_id` is documented for two different question types with one field — a
  `fill_in_multiple_blanks_question`'s blanks and a `multiple_dropdowns_question`'s dropdowns
  share the exact same tagging, "Used in fill in multiple blank and multiple dropdowns
  questions." — but nothing on the page states the value spaces are interchangeable between the
  two types (docs: https://canvas.instructure.com/doc/api/quiz_questions.html).
- The top-level quiz reorder endpoint's `order[][type]` allows two values, `question` and
  `group` — do not assume the same param name means the same allowed values everywhere; the
  group-scoped reorder endpoint (see "Randomising with question groups") allows only one (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).

**Source.** https://canvas.instructure.com/doc/api/quiz_questions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quizzes.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/assessment_question_banks.html, fetched 2026-09-10

### Randomising with question groups

**What Canvas does.** A question group sits inside a quiz and picks a random subset of its
member questions to show each student: `pick_count` is "the number of questions to randomly
select for this group," and `question_points` is the point value assigned to each one picked. A
group can pull its members from a course's own questions (added one at a time via
`question[quiz_group_id]` on the question endpoint above) or from an `assessment_question_bank`,
set only at creation. Banks themselves are a separate, read-only-via-API resource: this
reference's fetched page for them documents nothing beyond listing banks and the questions inside
them.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups` | List question groups in a quiz |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id` | Get a single quiz group |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups` | Create a question group |
| PUT | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id` | Update a question group |
| DELETE | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id` | Delete a question group |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id/reorder` | Reorder question groups |
| GET | `/api/v1/question_banks` | List question banks |
| GET | `/api/v1/question_banks/:id` | Get a single question bank |
| GET | `/api/v1/question_banks/:id/questions` | List assessment questions for a question bank |

**Parameters.**
- `quiz_groups[][name]` — string.
- `quiz_groups[][pick_count]` — integer.
- `quiz_groups[][question_points]` — integer.
- `quiz_groups[][assessment_question_bank_id]` — integer, create-only; "The id of the assessment
  question bank to pull questions from."
- `order[][id]` — integer, `Required`.
- `order[][type]` — string; "The type of item is always 'question' for a group." Allowed values:
  `question`.
- `context_type` — string, `Required`; "The type of context." Allowed values: `Course`,
  `Account`.
- `context_id` — integer, `Required`.
- `include_question_count` — boolean; "Whether to include the number of questions in each bank."

**Traps.**
- `quiz_groups[][assessment_question_bank_id]` is in the create endpoint's parameter table but
  absent from the update endpoint's — pulling a group from a bank reads as a create-time-only
  choice; nothing documents changing the source bank of an existing group (docs:
  https://canvas.instructure.com/doc/api/quiz_question_groups.html).
- This page never documents how a question gets added to a group in the first place when the
  group is not bank-backed — that happens on the question endpoint's own
  `question[quiz_group_id]` parameter, a different page entirely (docs:
  https://canvas.instructure.com/doc/api/quiz_question_groups.html; docs:
  https://canvas.instructure.com/doc/api/quiz_questions.html).
- The group-scoped reorder's `order[][type]` allows exactly one value, `question` — the same
  parameter name on the quiz-level reorder (see "Adding questions") allows `question` and
  `group`. Reading one Allowed-values list as covering both endpoints is wrong (docs:
  https://canvas.instructure.com/doc/api/quiz_question_groups.html; docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- The fetched question banks page documents exactly three endpoints, all `GET`. Nothing on it
  creates a bank, adds a question to one, or edits or deletes either — bank and bank-question
  management is not covered by this page's API surface at all (docs:
  https://canvas.instructure.com/doc/api/assessment_question_banks.html).
- `context_type` restricts a bank lookup to `Course` or `Account` context only — there is no
  third context type documented, so a bank cannot be looked up by, say, a group or user context
  through this endpoint (docs: https://canvas.instructure.com/doc/api/assessment_question_banks.html).

**Source.** https://canvas.instructure.com/doc/api/quiz_question_groups.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/assessment_question_banks.html, fetched 2026-09-10

### What the quiz is worth

**What Canvas does.** The Quiz object carries a `points_possible` field — "The total point value
given to the quiz" — but it is a response field only. Neither the create nor the edit parameter
table for a quiz lists `quiz[points_possible]` anywhere; the only documented ways to put points
on a quiz are per-question (`question[points_possible]`) and per-group
(`quiz_groups[][question_points]`, applied to every question the group picks). The quiz's total is
not something this API lets a caller assign directly.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/quizzes/:id` | Get a single quiz, including its derived `points_possible` |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/questions` | Set one question's point value |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/groups` | Set one group's per-question point value |

**Parameters.**
- `points_possible` — number, response field on the Quiz object; "The total point value given to
  the quiz."
- `question[points_possible]` — integer; "The maximum amount of points received for answering
  this question correctly."
- `quiz_groups[][question_points]` — integer; "The number of points to assign to each question in
  the group."

**Traps.**
- `quiz[points_possible]` does not exist as a request parameter on either the create or the edit
  endpoint for a quiz — only `points_possible` as a read-only response field is documented there.
  Sending it in a create or update body has no documented effect (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- A question group's `question_points` sets one value applied to every question the group picks,
  not a per-question override — the `QuizGroup` schema has no field for an individual question's
  own point value once it is inside a group (docs:
  https://canvas.instructure.com/doc/api/quiz_question_groups.html).
- Ungrouped questions keep their own `question[points_possible]`; grouped ones take the group's
  `question_points` instead. Nothing on either page states what happens to a question's own
  `points_possible` once `question[quiz_group_id]` assigns it into a group — whether the
  individual value is ignored, overwritten, or retained but unused is not documented (docs:
  https://canvas.instructure.com/doc/api/quiz_questions.html; docs:
  https://canvas.instructure.com/doc/api/quiz_question_groups.html).

**Source.** https://canvas.instructure.com/doc/api/quizzes.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_questions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_question_groups.html, fetched 2026-09-10

### Time limits, attempts and what students see afterwards

**What Canvas does.** A quiz's pacing and review behaviour are a cluster of parameters on the
same create/edit endpoint as the quiz shell, several of them conditional on one another:
`time_limit`, `allowed_attempts`, `scoring_policy` for which attempt counts, `one_question_at_a_time`
plus `cant_go_back` for how far a student can navigate, and `hide_results` plus the
`show_correct_answers*` family for what a student can see once they are done.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/quizzes` | Create a quiz with its timing and review settings |
| PUT | `/api/v1/courses/:course_id/quizzes/:id` | Edit those settings |

**Parameters.**
- `quiz[time_limit]` — integer; "Time limit to take this quiz, in minutes. Set to null for no
  time limit. Defaults to null."
- `quiz[allowed_attempts]` — integer; "Number of times a student is allowed to take a quiz. Set
  to -1 for unlimited attempts. Defaults to 1."
- `quiz[scoring_policy]` — string; "Required and only valid if allowed_attempts > 1." Allowed
  values: `keep_highest`, `keep_latest`. "Defaults to 'keep_highest'."
- `quiz[one_question_at_a_time]` — boolean; "Defaults to false."
- `quiz[cant_go_back]` — boolean; "Only valid if one_question_at_a_time=true... Defaults to
  false."
- `quiz[hide_results]` — string. Allowed values: `always`, `until_after_last_attempt`. If null,
  "students can see their results after any attempt."
- `quiz[show_correct_answers]` — boolean; "Only valid if hide_results=null... Defaults to true."
- `quiz[show_correct_answers_last_attempt]` — boolean; "Only valid if show_correct_answers=true
  and allowed_attempts > 1... Defaults to false."
- `quiz[show_correct_answers_at]` — DateTime; "Only valid if show_correct_answers=true."
- `quiz[hide_correct_answers_at]` — DateTime; "Only valid if show_correct_answers=true."
- `quiz[one_time_results]` — boolean; 'Only valid if "hide_results" is not set to "always".
  Defaults to false.'
- `quiz[shuffle_answers]` — boolean; "Defaults to false."

**Traps.**
- `quiz[scoring_policy]` is documented as both "Required" and conditional in the same sentence —
  "Required and only valid if allowed_attempts > 1." The page does not state what happens if it
  is sent while `allowed_attempts` is 1 or unset, or omitted while `allowed_attempts` is greater
  than 1 (docs: https://canvas.instructure.com/doc/api/quizzes.html).
- `show_correct_answers_last_attempt` chains three preconditions at once —
  `show_correct_answers=true`, `allowed_attempts > 1`, and implicitly `hide_results=null` (since
  `show_correct_answers` itself requires that) — before it does anything (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- `quiz[hide_results]` and `quiz[show_correct_answers]` gate each other in one direction only:
  `show_correct_answers` requires `hide_results=null`, but nothing says setting
  `show_correct_answers=false` affects `hide_results`. Setting `hide_results` to `always` after
  `show_correct_answers` was already configured leaves the correct-answers settings inert rather
  than clearing them (docs: https://canvas.instructure.com/doc/api/quizzes.html).
- `quiz[cant_go_back]` requires `one_question_at_a_time=true` — enabling "lock questions after
  answering" on a quiz that shows every question at once is accepted but, per the documented
  condition, has nothing to lock (docs: https://canvas.instructure.com/doc/api/quizzes.html).

**Source.** https://canvas.instructure.com/doc/api/quizzes.html, fetched 2026-09-10

### Accommodations and access

**What Canvas does.** Three separate mechanisms restrict or loosen who can take a quiz and when.
An access code and an IP filter are plain fields on the quiz itself. A per-student extension —
extra attempts, extra time, or an unlock override — is a separate write, available at two
different scopes: one call per quiz (`quiz_extensions`) or one call per course covering whichever
quiz a student is in (`course_quiz_extensions`). A third, read-only endpoint lists an
institution's named IP filters; it does not set a quiz's own filter.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/quizzes/:id/validate_access_code` | Validate a quiz access code |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/extensions` | Set extensions for student quiz submissions, per quiz |
| POST | `/api/v1/courses/:course_id/quiz_extensions` | Set extensions for student quiz submissions, per course |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/ip_filters` | Get available quiz IP filters |

**Parameters.**
- `quiz[access_code]` — string; "Restricts access to the quiz with a password. For no access code
  restriction, set to null. Defaults to null."
- `quiz[ip_filter]` — string; "Restricts access to the quiz to computers in a specified IP range.
  Filters can be a comma-separated list of addresses, or an address followed by a mask... For no
  IP filter restriction, set to null. Defaults to null."
- `access_code` — string, `Required` on `validate_access_code`; "The access code being
  validated."
- `quiz_extensions[][user_id]` — integer, `Required`, quiz-scoped.
- `quiz_extensions[][extra_attempts]` — integer, quiz-scoped; "limited to 1000 attempts or less."
- `quiz_extensions[][extra_time]` — integer, quiz-scoped; "limited to 10080 minutes (1 week)."
- `quiz_extensions[][manually_unlocked]` — boolean, quiz-scoped.
- `quiz_extensions[][extend_from_now]` — integer, quiz-scoped; "mutually exclusive to
  extend_from_end_at... limited to 1440 minutes (24 hours)."
- `quiz_extensions[][extend_from_end_at]` — integer, quiz-scoped; "mutually exclusive to
  extend_from_now... limited to 1440 minutes (24 hours)."
- `user_id` — integer, `Required`, course-scoped (flat, not bracket-nested).
- `extra_attempts`, `extra_time`, `manually_unlocked`, `extend_from_now`, `extend_from_end_at` —
  same meanings as their quiz-scoped counterparts, course-scoped (flat).

**Traps.**
- `quiz[access_code]`'s clear instruction is "set to null" to remove the restriction; the page
  never states that an empty string `""` does the same thing (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- The course-scoped endpoint's own parameter table (`user_id`, `extra_attempts`, `extra_time`,
  `manually_unlocked`, `extend_from_now`, `extend_from_end_at`) has no field identifying which
  quiz the extension applies to, even though the endpoint's path carries only a course id, not a
  quiz id (docs: https://canvas.instructure.com/doc/api/course_quiz_extensions.html).
- The same feature is shaped differently depending on which endpoint is called: the quiz-scoped
  endpoint wraps every field in a bracket-nested array, `quiz_extensions[][user_id]`; the
  course-scoped endpoint's equivalent field is flat, `user_id`, with no `quiz_extensions[]`
  wrapper at all (docs: https://canvas.instructure.com/doc/api/quiz_extensions.html; docs:
  https://canvas.instructure.com/doc/api/course_quiz_extensions.html).
- `extend_from_now` and `extend_from_end_at` are documented as "mutually exclusive" of each other
  on both endpoints, but neither page states what happens if both are sent in the same request —
  no error is documented (docs: https://canvas.instructure.com/doc/api/quiz_extensions.html;
  docs: https://canvas.instructure.com/doc/api/course_quiz_extensions.html).
- The IP filters endpoint's own description is "Get available quiz IP filters" — a list of
  institution-defined named filters a teacher can pick from. It is not the mechanism that
  restricts a specific quiz; that is the separate `quiz[ip_filter]` field on the quiz endpoint
  itself, and this page never states the two are connected (docs:
  https://canvas.instructure.com/doc/api/quiz_ip_filters.html; docs:
  https://canvas.instructure.com/doc/api/quizzes.html).

**Source.** https://canvas.instructure.com/doc/api/quizzes.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_extensions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/course_quiz_extensions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_ip_filters.html, fetched 2026-09-10

### Giving one student different dates

**What Canvas does.** This page is read-only. Both of its endpoints return the resolved
due/unlock/lock dates a quiz currently has for the operating user, split into `due_dates` (the
dates that apply, one entry per student on a student's own request) and `all_dates` (every
override, visible to teachers and staff). Neither endpoint accepts a body that creates, edits, or
deletes an override — this page never documents the write side of a quiz assignment override at
all. A quiz is an assignment underneath (see `references/fundamentals.md`), which is a plausible
reason a write path might not live on a quiz-specific page, but no page fetched for this
reference states that connection or points at `references/assignments.md`'s `AssignmentOverride`
endpoints as the place overrides are actually written.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/quizzes/assignment_overrides` | Retrieve assignment-overridden dates for Classic Quizzes |
| GET | `/api/v1/courses/:course_id/new_quizzes/assignment_overrides` | Retrieve assignment-overridden dates for New Quizzes |

**Parameters.**
- `quiz_assignment_overrides[][quiz_ids][]` — integer array; "If omitted, overrides for all
  quizzes available to the operating user will be returned."
- `due_dates` — array of `QuizAssignmentOverride`, response field; "For students, this array will
  always contain a single item which is the set of dates that apply to that student. For teachers
  and staff, it may contain more."
- `all_dates` — array of `QuizAssignmentOverride`, response field; "visible only to teachers and
  staff."
- `base` — boolean, `QuizAssignmentOverride` field; "If this property is present, it means that
  dates in this structure are not based on an assignment override, but are instead for all
  students."

**Traps.**
- Both endpoints on this page are `GET`. Nothing here creates, edits, or deletes a quiz
  assignment override — a caller looking for the quiz analogue of
  `POST .../assignments/:assignment_id/overrides` will not find it on this page (docs:
  https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html).
- The two endpoints differ by exactly one path segment — `quizzes/assignment_overrides` versus
  `new_quizzes/assignment_overrides` — and share an identical documented request and response
  shape. This is the one page in this reference that names New Quizzes directly rather than
  excluding it (docs: https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html).
- Omitting `quiz_assignment_overrides[][quiz_ids][]` does not return nothing — it returns
  overrides "for all quizzes available to the operating user." A caller who forgets the filter
  gets every quiz's dates, not an empty result (docs:
  https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html).
- `id` on a `QuizAssignmentOverride` is conditional on the record being a real override at all:
  "unless this is the base construct, in which case the 'id' field is omitted" — a `base: true`
  entry (the default dates for everyone not covered by an override) has no `id` to act on (docs:
  https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html).

**Source.** https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html, fetched 2026-09-10

### Publishing

**What Canvas does.** A quiz's published state is a plain boolean, `published`, the same shape
Canvas uses for an assignment (see `references/assignments.md`) and unlike the multi-value
`workflow_state` a course uses (see `references/fundamentals.md`) — the Quiz object schema on
this page carries no `workflow_state` field at all. `unpublishable` is a read-only companion flag
telling the caller in advance whether unpublishing would be allowed. Unlike the assignment
endpoint, this page states an explicit failure case for unpublishing a quiz with submissions
already attached.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/quizzes/:id` | Edit a quiz, including `published` |
| GET | `/api/v1/courses/:course_id/quizzes/:id` | Get a single quiz, including `unpublishable` |

**Parameters.**
- `quiz[published]` — boolean; "Whether the quiz should have a draft state of published or
  unpublished. NOTE: If students have started taking the quiz, or there are any submissions for
  the quiz, you may not unpublish a quiz and will recieve an error."
- `unpublishable` — boolean, read-only response field; "Whether the assignment's 'published'
  state can be changed to false. Will be false if there are student submissions for the quiz."
- `locked_for_user` — boolean, read-only response field.
- `lock_info`, `lock_explanation` — response fields, "(Optional)... Present when locked_for_user
  is true."

**Traps.**
- `quiz[published]` documents an actual error, not just a documented no-op: "you may not unpublish
  a quiz and will recieve an error" [sic] once students have started or submitted. This is more
  explicit than the assignment endpoint's own publish field, which documents the precondition
  (`unpublishable`) but not what response results from violating it — see
  `references/assignments.md` (docs: https://canvas.instructure.com/doc/api/quizzes.html).
- `unpublishable`'s own description text literally reads "Whether the assignment's 'published'
  state can be changed to false" on the Quiz object's schema — the word "assignment" on a field
  that describes a quiz. This mirrors a documented copy-paste pattern already seen on the
  assignment endpoint's own `grading_standard_id` field (`references/assignments.md`); do not
  read it as evidence that this flag actually lives on or affects a separate Assignment record
  (docs: https://canvas.instructure.com/doc/api/quizzes.html).
- No `workflow_state` field appears anywhere in the Quiz object shown on this page. Do not carry
  over a course's four-value `workflow_state` enum, or even assume a `workflow_state` string
  exists on a quiz at all — publishing here is `published`/`unpublishable` only (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).
- `locked_for_user`, `lock_info`, and `lock_explanation` are a separate lock concept from
  `published` — a quiz can be published and still `locked_for_user: true` via `quiz[lock_at]` /
  `quiz[unlock_at]`, which are dates, not the publish flag (docs:
  https://canvas.instructure.com/doc/api/quizzes.html).

**Source.** https://canvas.instructure.com/doc/api/quizzes.html, fetched 2026-09-10

### Attempts and their answers

**What Canvas does.** Starting a quiz creates a `QuizSubmission`; the student answers questions
against it, optionally flags questions to revisit, and completes it, after which "no further
modifications will be allowed" through the student-facing endpoints. A teacher can adjust scores
afterward on a different endpoint. `workflow_state` on a `QuizSubmission` takes five documented
values — a different vocabulary from a course's or a Progress object's own `workflow_state` (see
`references/fundamentals.md`). Every write against an in-progress submission requires a
`validation_token` issued when the submission was created, plus the current `attempt` number,
which "must be the latest attempt index." Each `question_type` has its own documented shape for
the `answer` a student submits — a shape distinct from the `answers[]` array an author sends when
creating the question (see "Adding questions").

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions` | Get all quiz submissions |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/submission` | Get the quiz submission for the current user |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id` | Get a single quiz submission |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions` | Create the quiz submission (start a quiz-taking session) |
| PUT | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id` | Update student question scores and comments |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id/complete` | Complete the quiz submission (turn it in) |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id/time` | Get current quiz submission times |
| GET | `/api/v1/quiz_submissions/:quiz_submission_id/questions` | Get all quiz submission questions |
| POST | `/api/v1/quiz_submissions/:quiz_submission_id/questions` | Answering questions |
| GET | `/api/v1/quiz_submissions/:quiz_submission_id/questions/:id/formatted_answer` | Get a formatted student numerical answer |
| PUT | `/api/v1/quiz_submissions/:quiz_submission_id/questions/:id/flag` | Flagging a question |
| PUT | `/api/v1/quiz_submissions/:quiz_submission_id/questions/:id/unflag` | Unflagging a question |

**Parameters.**
- `include[]` — string; on the submission list/get endpoints, allowed values `submission`,
  `quiz`, `user`; on the submission-questions list endpoint, allowed value `quiz_question`.
- `access_code` — string, on create; "Access code for the Quiz, if any."
- `preview` — boolean, on create; "Whether this should be a preview QuizSubmission and not count
  towards the user's course record. Teachers only."
- `quiz_submissions[][attempt]` — integer, `Required`, on the score-update endpoint; "This
  attempt MUST be already completed."
- `quiz_submissions[][fudge_points]` — number; "Amount of positive or negative points to fudge
  the total score by."
- `quiz_submissions[][questions]` — Hash; "keys are the question IDs, and the values are hashes
  of `score` and `comment` entries."
- `attempt` — integer, `Required`, on complete/answer/flag/unflag; "must be the latest attempt
  index, as earlier attempts can not be modified."
- `validation_token` — string, `Required`, on complete/answer/flag/unflag; "The unique validation
  token you received when this Quiz Submission was created."
- `quiz_questions[]` — `QuizSubmissionQuestion`, on the answer endpoint; "Set of question IDs and
  the answer value."
- `answer` — Numeric, `Required`, on `formatted_answer`.
- `workflow_state` — string, `QuizSubmission` response field. Documented values: `untaken`,
  `pending_review`, `complete`, `settings_only`, `preview`.
- `flagged` — boolean, `QuizSubmissionQuestion` response field.
- `end_at`, `time_left` — response fields on the `time` endpoint.

Documented `answer` shape per `question_type`, from the Question Answer Formats appendix:

| `question_type` | `answer` parameter shape |
| --- | --- |
| `essay_question` | String — `{ "answer": "Answer text." }` |
| `fill_in_multiple_blanks_question` | Hash of String to String — `{ "answer": { "variable": "Answer string." } }`, one entry per blank variable |
| `short_answer_question` | String — `{ "answer": "Some sentence." }` |
| `calculated_question` | Decimal, or a string form of one — `{ "answer": 2.3e-6 }` or `{ "answer": "13.4" }` |
| `matching_question` | Array of Hash — `{ "answer": [{ "answer_id": id, "match_id": id }] }` |
| `multiple_choice_question` | Integer — `{ "answer": answer_id }` |
| `multiple_dropdowns_question` | Hash of String to Integer — `{ "answer": { "variable": answer_id } }` |
| `multiple_answers_question` | Array of Integer — `{ "answer": [ answer_id, ... ] }` |
| `numerical_question` | "This is similar to Formula Questions" (`calculated_question`'s shape). |
| `true_false_question` | "The rest is similar to Multiple Choice questions" (`multiple_choice_question`'s shape). |
| `file_upload_question` | Not documented in this appendix. |
| `text_only_question` | Not documented in this appendix — it is not answerable. |

**Traps.**
- `attempt` on the complete/answer/flag/unflag endpoints "must be the latest attempt index, as
  earlier attempts can not be modified" — the documentation states the constraint but not the
  response code for violating it beyond the complete endpoint's own explicit "400 Bad Request if
  the attempt parameter is not the latest attempt" (docs:
  https://canvas.instructure.com/doc/api/quiz_submissions.html).
- The score-update endpoint (`PUT .../submissions/:id`) documents "400 Bad Request if the
  specified QS attempt is not yet complete" — the opposite direction restriction from the
  student-facing endpoints, which require the *latest* attempt; grading requires a *completed*
  one (docs: https://canvas.instructure.com/doc/api/quiz_submissions.html).
- `file_upload_question` and `text_only_question` have no entry in the Question Answer Formats
  appendix at all — the appendix documents nine of the twelve `question_type` values (three by
  cross-reference to another type's shape) and is silent on the remaining two (docs:
  https://canvas.instructure.com/doc/api/quiz_submission_questions.html).
- `QuizSubmission.workflow_state`'s five values (`untaken`, `pending_review`, `complete`,
  `settings_only`, `preview`) are yet another distinct vocabulary from the course's four-value
  enum and the Progress object's own four values — matching the pattern already documented in
  `references/fundamentals.md`, where matching value names across object types do not imply a
  shared vocabulary (docs: https://canvas.instructure.com/doc/api/quiz_submissions.html).
- The `answers` field on `QuizSubmissionQuestion` is explicitly gated: "The presence of this
  parameter is dependent on permissions." A caller cannot assume the list of possible answers is
  always present in the response even when a question was successfully fetched (docs:
  https://canvas.instructure.com/doc/api/quiz_submission_questions.html).

**Source.** https://canvas.instructure.com/doc/api/quiz_submissions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_submission_questions.html, fetched 2026-09-10

### Statistics and reports

**What Canvas does.** Two separate objects cover a finished quiz's aggregate results. A
`QuizReport` is a generated file — CSV data Canvas builds asynchronously, of type
`student_analysis` or `item_analysis`, that a caller polls or fetches through a `Progress`
object (see `references/fundamentals.md`) or a `File` object. `QuizStatistics` is a live JSON
computation instead — one endpoint, one boolean parameter — broken into
`question_statistics` and `submission_statistics`, with the shape of each question's statistics
varying by that question's `question_type`; several types are documented as sharing another
type's shape rather than getting their own.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/reports` | Retrieve all quiz reports |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/reports` | Create a quiz report |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/reports/:id` | Get a quiz report |
| DELETE | `/api/v1/courses/:course_id/quizzes/:quiz_id/reports/:id` | Abort the generation of a report, or remove a previously generated one |
| GET | `/api/v1/courses/:course_id/quizzes/:quiz_id/statistics` | Fetching the latest quiz statistics |

**Parameters.**
- `includes_all_versions` — boolean, on report list/create; "ignored for item_analysis reports."
- `quiz_report[report_type]` — string, `Required`, on create. Allowed values: `student_analysis`,
  `item_analysis`.
- `quiz_report[includes_all_versions]` — boolean, on create.
- `include` — String array, on report create/get. Allowed values: `file`, `progress`;
  "(Note: JSON-API only)."
- `all_versions` — boolean, on the statistics endpoint; "Whether the statistics report should
  include all submissions attempts."
- `generatable` — boolean, `QuizReport` response field; "true unless the quiz is a survey one."
- `anonymous` — boolean, `QuizReport` response field; "if true, no student names will be included
  in the csv."
- `multiple_attempts_exist` — boolean, `QuizStatistics` response field.

**Traps.**
- `generatable` on a `QuizReport` is documented "true unless the quiz is a survey one" — a
  `practice_quiz`, `assignment`, or `graded_survey` quiz is reportable; only the plain `survey`
  `quiz_type` is called out as excluded, and the field name does not say what response a
  `POST .../reports` returns if a report is requested anyway on a non-generatable quiz (docs:
  https://canvas.instructure.com/doc/api/quiz_reports.html).
- Aborting a report generation is conditional and stateful: the documentation requires checking
  "the 'workflow_state' property of the QuizReport's Progress object" first, because "only when
  the progress reports itself in a 'queued' state can the generation be aborted" — calling
  `DELETE` on a report whose Progress is past that state is not guaranteed to do what the
  endpoint name suggests (docs: https://canvas.instructure.com/doc/api/quiz_reports.html).
- The same `DELETE` endpoint serves two different documented purposes depending on the report's
  state — cancel a queued generation, or remove an already-generated report — with one response
  code, "204 No Content if your request was accepted," covering both (docs:
  https://canvas.instructure.com/doc/api/quiz_reports.html).
- The statistics endpoint takes exactly one request parameter, `all_versions`. Everything else
  documented on that page — `question_statistics`, `submission_statistics`, the per-type
  breakdowns in the appendix — is response shape, not something a caller can filter or configure
  on the request (docs: https://canvas.instructure.com/doc/api/quiz_statistics.html).
- Several `question_type` values share statistics shape by cross-reference rather than getting
  their own documented schema: `True/False` "look[s] just like" `Multiple Choice`; `File Upload`
  and `Formula` (`calculated_question`) both "look just like" `Essay`; `Multiple Dropdowns`
  "look[s] just like" `Fill In Multiple Blanks`. A caller cannot assume every `question_type`
  named on the "Adding questions" table has its own entry in this appendix (docs:
  https://canvas.instructure.com/doc/api/quiz_statistics.html).

**Source.** https://canvas.instructure.com/doc/api/quiz_reports.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_statistics.html, fetched 2026-09-10

### New Quizzes is a different API

**What Canvas does.** New Quizzes is a separate service with its own API root,
`/api/quiz/v1/...`, distinct from Classic Quizzes' `/api/v1/.../quizzes`. None of the ten Classic
Quiz pages this reference is built from reach it, and nothing in this file applies to it. Its own
documentation lives on two pages: New Quizzes, "API for accessing and building New Quizzes," and
New Quiz Items, "API for accessing and building items inside a New Quiz." Where Classic models a
quiz's content as `QuizQuestion` objects with a fixed `question_type` enum, New Quizzes models it
as `QuizItem` objects — `entry_type` one of `Item`, `Stimulus`, `BankEntry`, or `Bank` — a
different vocabulary and a different object shape entirely, documented on its own two pages
without cross-reference to any of the endpoints above. This reference does not document New
Quizzes; treat every endpoint, parameter, and enum value above as Classic-only.

What tells the two apart from outside the API: a New Quiz's own object schema has no `quiz_type`
field and no `practice_quiz`/`graded_survey`/`survey` distinction the way a Classic quiz does —
grading is controlled only by `grading_type`. The item-creation model is also visibly different:
some New Quiz item kinds (`StimulusItem`, `BankItem`, `BankEntry`) are documented as retrievable
through the API but not creatable or editable through it — "They must be created and updated via
the UI" — a restriction with no analogue anywhere in the Classic question or group endpoints
above.

**Endpoints.** None recorded — this section claims no coverage.

**Parameters.** None recorded — this section claims no coverage.

**Traps.**
- The path prefix itself is the tell: every New Quizzes and New Quiz Items endpoint on its own
  two pages starts `/api/quiz/v1/courses/:course_id/quizzes...`, never `/api/v1/...`. A client
  built against the endpoints in this file will not reach a New Quiz no matter what id it is
  given (docs: https://canvas.instructure.com/doc/api/new_quizzes.html; docs:
  https://canvas.instructure.com/doc/api/new_quiz_items.html).
- Three of New Quizzes' four documented item kinds are API-read-only: "For now, stimulus items
  can only be retrieved with the API. They must be created and updated via the UI," and the same
  sentence, verbatim, is repeated for `BankItem` and `BankEntry`. Only `QuestionItem` supports
  create, update, and delete through the API on that page (docs:
  https://canvas.instructure.com/doc/api/new_quiz_items.html).
- `quiz_assignment_overrides.html` (see "Giving one student different dates") is the one
  exception in this reference: it documents a `GET .../new_quizzes/assignment_overrides`
  endpoint side by side with the Classic one. That single page is not a general bridge between
  the two systems — nothing else fetched for this reference names a New Quizzes path (docs:
  https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html).

**Source.** https://canvas.instructure.com/doc/api/new_quizzes.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/new_quiz_items.html, fetched 2026-09-10
