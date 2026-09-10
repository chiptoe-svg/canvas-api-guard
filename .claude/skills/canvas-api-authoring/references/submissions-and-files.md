# Submissions and files

Finding and filtering what students have turned in, reading back one student's submission and
its attempts, the files attached to a submission, downloading a file, the full three-step upload
flow (and its URL-based alternative), where an uploaded file lands, and exporting a course or a
piece of it. `include[]`, `workflow_state`, and long-job polling follow the same shapes described
in `fundamentals.md`; grading a submission and rubric assessment live in `rubrics-and-grades.md`.

### Listing submissions for an assignment

**What Canvas does.** One assignment's submissions come back as a paginated array of `Submission`
objects from a course- or section-scoped endpoint. A `Submission`'s own id in this API is the id
of the student, not a separate submission id — there is no other submission id exposed anywhere
in this API. The listing itself takes only two request parameters: which related objects to pull
in, and whether to bucket the array by student group.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions` | List submissions for an assignment |
| GET | `/api/v1/sections/:section_id/assignments/:assignment_id/submissions` | List submissions for an assignment, scoped to a section |

**Parameters.**
- `include[]` — string; "Associations to include with the group." Allowed values:
  `submission_history`, `submission_comments`, `submission_html_comments`, `rubric_assessment`,
  `assignment`, `visibility`, `course`, `user`, `group`, `read_status`, `student_entered_score`.
- `grouped` — boolean; "If this argument is true, the response will be grouped by student
  groups."
- Response fields named on this page: `assignment_id`, `user_id`, `grader_id`,
  `canvadoc_document_id`, `submitted_at`, `score`, `attempt`, `body`, `grade`,
  `grade_matches_current_submission`, `preview_url`, `redo_request`, `url`, `late`,
  `assignment_visible`, `workflow_state` (`submitted`, `unsubmitted`, `graded`,
  `pending_review`).

**Traps.**
- Only `include[]` and `grouped` exist here — no `workflow_state` filter, no `student_ids[]`, no
  `assignment_ids[]`. To filter by grading status or to scope to particular students, use
  `/students/submissions` instead (see "Listing submissions across several assignments at once")
  (docs: https://canvas.instructure.com/doc/api/submissions.html).
- `grouped` here groups by student *group* — the collaborative-group construct, "If this argument
  is true, the response will be grouped by student groups" — not by grading status and not the
  same grouping key as the identically-named parameter on `/students/submissions`, which groups
  by student instead (docs: https://canvas.instructure.com/doc/api/submissions.html).
- "The submission id in these URLs is the id of the student in the course, there is no separate
  submission id exposed in these APIs" — a caller reading `:user_id` in the path as anything but
  a student id is already wrong (docs: https://canvas.instructure.com/doc/api/submissions.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### Listing submissions across several assignments at once

**What Canvas does.** `/students/submissions` answers "which submissions, for which students,
across which assignments" in one call, independent of the per-assignment listing above. It
accepts explicit student and assignment id lists (or the literal id `"all"`), a `workflow_state`
filter, submitted/graded date bounds, grading-period scoping, enrollment-state filtering, and
ordering — none of which the per-assignment endpoint documents. `grouped` here reshapes the flat
array into one object per student holding a nested `submissions` array.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/students/submissions` | List submissions for multiple assignments |
| GET | `/api/v1/sections/:section_id/students/submissions` | List submissions for multiple assignments, scoped to a section |

**Parameters.**
- `student_ids[]` — string; "List of student ids to return submissions for. If this argument is
  omitted, return submissions for the calling user. Students may only list their own
  submissions. Observers may only list those of associated students. The special id `"all"` will
  return submissions for all students in the course/section as appropriate."
- `assignment_ids[]` — string; "List of assignments to return submissions for. If none are
  given, submissions for all assignments are returned."
- `grouped` — boolean; "If this argument is present, the response will be grouped by student,
  rather than a flat array of submissions."
- `post_to_sis` — boolean; "If this argument is set to true, the response will only include
  submissions for assignments that have the `post_to_sis` flag set to true and user enrollments
  that were added through sis."
- `submitted_since` — DateTime; "will only include submissions that were submitted after the
  specified date_time," "must be formatted as ISO 8601 YYYY-MM-DDTHH:MM:SSZ."
- `graded_since` — DateTime; "will only include submissions that were graded after the specified
  date_time."
- `grading_period_id` — integer; "The id of the grading period in which submissions are being
  requested (Requires grading periods to exist on the account)."
- `workflow_state` — string; "The current status of the submission." Allowed values:
  `submitted`, `unsubmitted`, `graded`, `pending_review`.
- `enrollment_state` — string; "The current state of the enrollments. If omitted will include
  all enrollments that are not deleted." Allowed values: `active`, `concluded`.
- `state_based_on_date` — boolean; "If omitted it is set to true. When set to false it will
  ignore the effective state of the student enrollments and use the workflow_state for the
  enrollments. The argument is ignored unless `enrollment_state` argument is also passed."
- `order` — string; "Defaults to `id`. Doesn't affect results for `grouped` mode." Allowed
  values: `id`, `graded_at`.
- `order_direction` — string; "Defaults to `ascending`. Doesn't affect results for `grouped`
  mode." Allowed values: `ascending`, `descending`.
- `include[]` — string; "Associations to include with the group. `total_scores` requires the
  `grouped` argument." Allowed values: `submission_history`, `submission_comments`,
  `submission_html_comments`, `rubric_assessment`, `assignment`, `total_scores`, `visibility`,
  `course`, `user`, `sub_assignment_submissions`, `peer_review_submissions`,
  `student_entered_score`.

**Traps.**
- `total_scores` in `include[]` "requires the `grouped` argument" — this dependency is stated
  outright but the page never says what happens if `total_scores` is requested without `grouped`
  (docs: https://canvas.instructure.com/doc/api/submissions.html).
- `student_ids[]` is capability-gated by the caller's role — "Students may only list their own
  submissions. Observers may only list those of associated students" — it is not a free-form id
  filter for every caller (docs: https://canvas.instructure.com/doc/api/submissions.html).
- `workflow_state`'s four allowed values are the same four the per-assignment listing names as a
  *response* field's possible values, but here they are a *request* filter — the parallel
  vocabulary does not mean the per-assignment endpoint (see previous section) accepts this same
  filter; it documents no `workflow_state` parameter at all (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `include[]`'s allowed-value list differs from the per-assignment listing's: `total_scores`,
  `sub_assignment_submissions`, and `peer_review_submissions` are unique to this endpoint, while
  `group` and `read_status` (present on the per-assignment listing) are absent here (docs:
  https://canvas.instructure.com/doc/api/submissions.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### Finding who has not been graded

**What Canvas does.** Canvas documents one endpoint purpose-built for the ungraded count,
`submission_summary`, and it returns counts only — `graded`, `ungraded`, and `not_submitted` —
for one assignment's gradeable students. Getting the actual list of who falls into each bucket
means falling back to `/students/submissions` (see the previous section) filtered by
`workflow_state`, since no single documented value means "not yet graded" on its own.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/submission_summary` | Submission summary counts for an assignment |
| GET | `/api/v1/sections/:section_id/assignments/:assignment_id/submission_summary` | Submission summary counts, scoped to a section |

**Parameters.**
- `grouped` — boolean; "If this argument is true, the response will take into account student
  groups."
- `include_deactivated` — boolean; "If this argument is true, the response will include
  deactivated students in the summary (defaults to false)."
- Response fields: `graded`, `ungraded`, `not_submitted`.

**Traps.**
- `submission_summary` "Returns the number of submissions for the given assignment based on
  gradeable students that fall into three categories: graded, ungraded, not submitted" — three
  integers, never a list of submissions or user ids (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- There is no `workflow_state` value literally named "ungraded." `/students/submissions`
  documents only `submitted`, `unsubmitted`, `graded`, `pending_review` — a caller has to filter
  out `graded` (and decide what to do with `pending_review`, a distinct state from `submitted`)
  to approximate the ungraded set by hand (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `grouped`'s meaning here — "take into account student groups" for a count adjustment — is a
  third distinct sense of the same parameter name on this page family, next to the per-assignment
  listing's grouping-by-collaborative-group and `/students/submissions`'s grouping-by-student; the
  three are documented separately and none behaves like another (docs:
  https://canvas.instructure.com/doc/api/submissions.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### One student's submission, and its attempts

**What Canvas does.** A single submission is addressed by course or section, assignment, and
either the student's `user_id` (`self` for the caller's own) or, when grading is anonymized, an
`anonymous_id`. `attempt` on the returned object is the current attempt number; the only
documented way to see prior attempts is to request `include[]=submission_history`.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id` | Get a single submission by user id |
| GET | `/api/v1/sections/:section_id/assignments/:assignment_id/submissions/:user_id` | Get a single submission by user id, scoped to a section |
| GET | `/api/v1/courses/:course_id/assignments/:assignment_id/anonymous_submissions/:anonymous_id` | Get a single submission by anonymous id |
| GET | `/api/v1/sections/:section_id/assignments/:assignment_id/anonymous_submissions/:anonymous_id` | Get a single submission by anonymous id, scoped to a section |

**Parameters.**
- `include[]`, on the `:user_id` form; "Associations to include with the group." Allowed values:
  `submission_history`, `submission_comments`, `submission_html_comments`, `rubric_assessment`,
  `full_rubric_assessment`, `visibility`, `course`, `user`, `read_status`,
  `student_entered_score`.
- `include[]`, on the `:anonymous_id` form; Allowed values: `submission_history`,
  `submission_comments`, `rubric_assessment`, `full_rubric_assessment`, `visibility`, `course`,
  `user`, `read_status`.
- `attempt` — response field; "This is the submission attempt number."
- `anonymous_id` — response field; "A unique short ID identifying this submission without
  reference to the owning user. Only included if the caller has administrator access for the
  current account."

**Traps.**
- The two single-submission forms do not share one `include[]` enum: the `:user_id` form
  supports `submission_html_comments` and `student_entered_score`; the `:anonymous_id` form
  supports neither. `group` belongs to neither form — it is unique to the per-assignment listing
  (docs: https://canvas.instructure.com/doc/api/submissions.html).
- "The submission id in these URLs is the id of the student in the course, there is no separate
  submission id exposed in these APIs" — the `:user_id` path segment names a student, not a
  submission, and the page states plainly that no other submission id exists in this API (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `include[]=submission_history` is documented only as an enum value name. The page never shows
  the shape of a history entry — no worked example, no field list — so each entry should be
  treated as an unspecified object, not assumed to be a full `Submission` (docs:
  https://canvas.instructure.com/doc/api/submissions.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10

### The files a student attached

**What Canvas does.** A student attaches files to a submission by first running the file-upload
flow (see below) and then citing the resulting file ids in `submission[file_ids][]` on the
assignment submission, or by uploading directly against the submission's own file-creation
endpoint. Reading files back afterward crosses into the Files API: its `File` object carries a
`preview_url` field documented as "Only included in submission endpoints" — the only sentence on
either page that acknowledges files appear nested inside a submission response at all.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id/files` | Upload a file to a submission (step one) |
| POST | `/api/v1/sections/:section_id/assignments/:assignment_id/submissions/:user_id/files` | Upload a file to a submission, scoped to a section |
| GET | `/api/v1/files/:id/public_url` | Get an inline preview URL for a file |

**Parameters.**
- `submission[file_ids][]` — integer; "Submit the assignment as a set of one or more previously
  uploaded files residing in the submitting user's files section (or the group's files section,
  for group assignments)... Requires a submission_type of `online_upload`."
- `submission_id` — integer, on `GET /files/:id/public_url`; "The id of the submission the file
  is associated with. Provide this argument to gain access to a file that has been submitted to
  an assignment (Canvas will verify that the file belongs to the submission and the calling user
  has rights to view the submission)."
- `preview_url` — `File` object field; "optional: url to the document preview. This url is
  specific to the user making the api call. Only included in submission endpoints."

**Traps.**
- The word "attachments" appears nowhere in `submissions.html`'s own `Submission` object schema
  — zero literal occurrences anywhere on the page — even though a real `online_upload`
  submission carries files. A caller reading only the Submissions API page has no documented
  field name for "the files on this submission" (docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `files.html`'s `preview_url` comment — "Only included in submission endpoints" — is the sole
  acknowledgment, on either page, that `File` objects nest inside a submission response at all.
  The `Submission` schema and the `File` schema live on two different pages, and neither
  cross-links the other's claim (docs: https://canvas.instructure.com/doc/api/files.html; docs:
  https://canvas.instructure.com/doc/api/submissions.html).
- `submission[file_ids][]` only ever accepts ids of files that already exist in Canvas — it never
  accepts raw file data. See "Uploading a file: the three steps" for how those ids come to exist
  (docs: https://canvas.instructure.com/doc/api/submissions.html).

**Source.** https://canvas.instructure.com/doc/api/submissions.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/files.html, fetched 2026-09-10

### Downloading an attachment

**What Canvas does.** Canvas documents the identical download route nine times, once per context
it can be reached from: a bare file id, and eight further scopes named on the page (accounts,
assessment questions, assignments, courses, groups, quiz statistics, quiz submissions, and
users). All nine share one two-line documentation body. A separate, `/api/v1/`-namespaced "Get
file" endpoint returns the `File` JSON object rather than the file's bytes.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/files/:file_id/download` | Download file |
| GET | `/courses/:course_id/files/:file_id/download` | Download file, scoped to a course |
| GET | `/api/v1/files/:id` | Get file (the `File` JSON object, not a download) |
| GET | `/api/v1/courses/:course_id/files/:id` | Get file, scoped to a course |

**Parameters.**
- `include[]`, on `GET /api/v1/files/:id`; "Array of additional information to include."
  Allowed values: `user`.
- `replacement_chain_context_type` — string, `[DEPRECATED]`, on `GET /api/v1/files/:id`; "When a
  user replaces a file during upload, Canvas keeps track of the `replacement chain`... Must be
  set to `course` or `account`."
- `replacement_chain_context_id` — integer, `[DEPRECATED]`, on `GET /api/v1/files/:id`.
- `File` object's `url` field is rendered in the docs' own example as
  `"http://www.example.com/files/569/download?download_frd=1"`.

**Traps.**
- "Download file"'s own text reads "Downloads the file" directly above "Example Request," but the
  same entry's return-type line says "Returns a File object" — the same endpoint entry describes
  its response body two different ways (docs: https://canvas.instructure.com/doc/api/files.html).
- The download route repeats nine times with no scope carrying any documented behavioral
  difference from another — every one of the nine reuses the identical "Downloads the file" /
  "Returns a File object" body (docs: https://canvas.instructure.com/doc/api/files.html).
- "Get file" (`GET /api/v1/files/:id`) and "Download file" (`GET /files/:file_id/download`) are
  two different, separately documented endpoints for the same resource — only one of them sits
  under `/api/v1/` (docs: https://canvas.instructure.com/doc/api/files.html).
- "Reset link verifier" (`POST /api/v1/files/:id/reset_verifier`) is documented as
  `[DEPRECATED] This method is deprecated, effective 2026-07-07 (notice given 2026-04-08): The
  UUID-based verification method for file access is being deprecated. This endpoint will no
  longer be available" — as of this fetch, that effective date has already passed (docs:
  https://canvas.instructure.com/doc/api/files.html).

**Source.** https://canvas.instructure.com/doc/api/files.html, fetched 2026-09-10

### Uploading a file: the three steps

**What Canvas does.** Canvas documents two ways to get a file into Canvas: POSTing the file data
directly, in three steps, or handing Canvas a public URL to fetch. Both begin with the same first
POST to Canvas. This is the one part of the API where the second step of a flow is **not** a
request to the Canvas host at all, and getting the host, the auth, and the ordering wrong
produces a failure that looks like a permissions problem rather than a protocol error.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/files` | Step 1: notify Canvas of an upload, scoped to a course |
| POST | `/api/v1/users/self/files` | Step 1: notify Canvas of an upload, scoped to the caller's own files |
| POST | `/api/v1/accounts/:account_id/sis_imports` | Step 1 under a `pre_attachment` object, for a SIS import file |
| POST | `/api/v1/courses/:course_id/content_migrations` | Step 1 under a `pre_attachment` object, for a content migration file |
| POST | `/api/v1/courses/:course_id/quizzes/:quiz_id/submissions/self/files` | Step 1: notify Canvas of an upload, scoped to a quiz submission |

**Parameters.**
- Step 1 arguments (POST body, all contexts): `name` — "The filename of the file. Any UTF-8 name
  is allowed. Path components such as `/` and `\` will be treated as part of the filename, not a
  path to a sub-folder." `size` — "The size of the file, in bytes. This field is recommended, as
  it will let you find out if there's a quota issue before uploading the raw file." `content_type`
  — "The content type of the file. If not given, it will be guessed based on the file
  extension." `parent_folder_id` — "An error will be returned if this does not correspond to an
  existing folder. If this and `parent_folder_path` are sent an error will be returned. If
  neither is given, a default folder will be used." `parent_folder_path` — "The path separator is
  the forward slash `/`, never a back slash. The folder will be created if it does not already
  exist... If this and `parent_folder_id` are sent an error will be returned. If neither is
  given, a default folder will be used." `folder` — "[deprecated] Use `parent_folder_path`
  instead." `on_duplicate` — "If `overwrite`, then this file upload will overwrite any other file
  in the folder with the same name. If `rename`, then this file will be renamed if another file
  in the folder exists with the given name. If no parameter is given, the default is
  `overwrite`." `success_include[]` — "An array of additional information to include in the
  upload success response."
- Step 1a, URL-upload additions: `url` — "The full URL to the file to be uploaded. This URL must
  be publicly accessible." `submit_assignment` — "A boolean to indicate whether or not to
  automatically submit the assignment the file is associated with if it is associated with an
  assignment. Defaults to true."
- Step 1's response: `upload_url`, `upload_params` (a JSON object whose own keys are
  unspecified — the docs show `key` only as an example: "unspecified parameters; key above will
  not necesarily be present either").
- Step 2's only parameter beyond `upload_params`' own keys: `file` — "the file parameter which
  must be posted as the last parameter following all the others."
- Step 1a's response adds `progress`, holding `url` and `workflow_state` (example value
  `"running"`); on success "the created attachment's id will be returned in the results of the
  Progress object as `id`." Progress's own field list and polling endpoint are documented in
  `fundamentals.md`.
- Step 2 of the URL-upload flow, when `upload_url` is present: `target_url` replaces `file` as
  the one parameter added to `upload_params`' own keys.
- Step 3's response body (POST flow): `id`, `url`, `content-type`, `display_name`, `size`.
- Quiz submission files' own step 1 is a narrower copy of the general arguments: only `name` and
  `on_duplicate` — "The name of the quiz submission file" and "How to handle duplicate names" —
  no `size`, `content_type`, `parent_folder_id`, `parent_folder_path`, `folder`, or
  `success_include[]`. Its step 1 response wraps the usual `upload_url`/`upload_params` pair
  inside an `attachments` array rather than returning them at the top level.

**Traps.**
- Step 2 posts to whatever host `upload_url` names, and that host is not necessarily Canvas:
  "this upload URL might be another URL in the same domain, or a Amazon S3 bucket, or some other
  URL." The very next line adds "The access token is not sent with this request" — step 2 carries
  no Canvas API token at all (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html).
- `file` "must be posted as the last parameter following all the others" in step 2 — an ordering
  requirement of the multipart request itself, not an accident of how a particular HTTP client
  happens to serialize form fields (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html).
- Step 2's request is signed: "the request is signed, and will be denied if any parameters from
  the upload_params response are added, removed or modified. The parameters in upload_params may
  vary over time, and between Canvas installs" — every key `upload_params` returns must be
  forwarded verbatim, whether or not the caller recognizes it (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html).
- Step 3 is not optional even when step 2 succeeds: "the response will be either a 3XX redirect
  or 201 Created." For the 3XX case, "the application needs to perform a GET to this location in
  order to complete the upload, otherwise the new file may not be marked as available." Step 3 is
  the only one of the three steps that goes back to Canvas "authenticated using the normal API
  access token authentication" (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html).
- Step 3 is documented as a GET specifically for forwards-compatibility with the 201 case, stated
  outright: "While a POST would be truer to REST semantics, a GET is required for forwards
  compatibility with the 201 Created response" (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html).
- The URL-upload alternative has two response shapes, distinguished by one signal only: "You can
  distinguish the new behavior (and expected follow up) from the old behavior precisely by the
  presence or absence of the `upload_url` key" in the initial POST's response — there is no
  separate version flag (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html).
- When the URL-upload response does carry `upload_url`, step 2 still POSTs
  `multipart/form-data` to it "just as if you were performing a direct upload," with one named
  exception: "the file parameter is omitted." Every other `upload_params` key still applies
  (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html).
- The URL-upload flow's own "step 3" is not the POST flow's redirect-confirmation step at all —
  it is Progress polling: "a progress object is provided which can be periodically polled to
  check the status of the upload," with the attachment id read from the Progress object's
  `results.id` on completion. The two flows' three steps are not the same shape repeated twice
  (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html).
- The sentence telling a caller how to check the URL-upload's final status literally reads "it
  can use the file.file_uploads.html to query the status" — the filename of the very page being
  read, not a distinct endpoint name or a working link. This looks like a broken doc-generator
  cross-reference rather than an instruction to re-POST to this same documentation page; the
  intended target is almost certainly the Progress API (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html).
- Content type is `multipart/form-data` on step 2 in both flows — stated explicitly for each:
  "This second request must be POSTed as a multipart/form-data request" for the direct-POST flow,
  and "The Content-Type is still expected to be multipart/form-data" for the URL-upload flow
  (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html).
- SIS imports and content migrations route the same step-1 arguments through a nested
  `pre_attachment` object instead of the flat body every other context uses: "the arguments below
  are provided under a `pre_attachment` object in the initial POST... The `upload_url` and
  `upload_params` in the response will also be under a `pre_attachment` object" (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html).
- The endpoint a caller chooses for step 1 changes what the resulting file may be used for, not
  just where it lives: "only files posted to the submissions comments endpoint can be attached to
  a submissions comment" (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html).
- This page's own self-referencing student-submission-comment path,
  `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/comments/self/files`,
  orders its segments differently from `submission_comments.html`'s documented endpoint for the
  same action, `/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id/comments/files`
  — with `:user_id` as `self` that reads `.../submissions/self/comments/files`, `comments` and
  `self` swapped relative to the other page's `.../submissions/comments/self/files` (docs:
  https://canvas.instructure.com/doc/api/file.file_uploads.html; docs:
  https://canvas.instructure.com/doc/api/submission_comments.html).
- Quiz Submission Files' example response nests the entire step 1 payload one level deeper than
  every other context in this section: `{"attachments": [{"upload_url": ..., "upload_params":
  {...}}]}`, an array wrapper the general file-upload documentation never mentions and never
  shows for any other endpoint (docs:
  https://canvas.instructure.com/doc/api/quiz_submission_files.html).

**Source.** https://canvas.instructure.com/doc/api/file.file_uploads.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/submission_comments.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/quiz_submission_files.html, fetched 2026-09-10

### Where an uploaded file goes

**What Canvas does.** Every upload target that supports folders resolves its destination one of
two ways at step 1: `parent_folder_id` names an existing folder by id, or `parent_folder_path`
names one by slash-separated path, created on demand if it doesn't exist yet. Folders are also
their own first-class resource, with create/read/update/delete endpoints addressed by the same
two mechanisms, plus a `by_path` route that resolves a full path to the chain of `Folder` objects
along it, and a literal `root` id that names a context's root folder.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/folders` | Create a folder |
| POST | `/api/v1/folders/:folder_id/folders` | Create a folder inside another folder |
| GET | `/api/v1/folders/:id` | Get folder |
| GET | `/api/v1/courses/:course_id/folders/by_path/*full_path` | Resolve a folder path |
| GET | `/api/v1/courses/:course_id/folders` | List all folders (flat, recursive) |
| GET | `/api/v1/folders/:id/folders` | List folders (immediate children only) |
| PUT | `/api/v1/folders/:id` | Update folder |
| DELETE | `/api/v1/folders/:id` | Delete folder |
| POST | `/api/v1/folders/:folder_id/files` | Upload a file to a folder (a third step-1 target) |
| POST | `/api/v1/folders/:dest_folder_id/copy_file` | Copy a file from elsewhere in Canvas into a folder |
| PUT | `/api/v1/files/:id` | Update file (can move it via `parent_folder_id`) |

**Parameters.**
- `name` — required string, on Create folder; "The name of the folder."
- `parent_folder_id` — string, on Create folder; "An error will be returned if this does not
  correspond to an existing folder. If this and `parent_folder_path` are sent an error will be
  returned. If neither is given, a default folder will be used."
- `parent_folder_path` — string, on Create folder; "The path separator is the forward slash `/`,
  never a back slash. The parent folder will be created if it does not already exist. This
  parameter only applies to new folders in a context that has folders, such as a user, a course,
  or a group."
- `lock_at`, `unlock_at` — DateTime, on Create/Update folder.
- `locked`, `hidden` — boolean, on Create/Update folder.
- `position` — integer, on Update folder; "Set an explicit sort position for the folder."
- `force` — boolean, on Delete folder; "Set to 'true' to allow deleting a non-empty folder."
- `parent_folder_id` — string, on Update file; "The id of the folder to move this file into. The
  new folder must be in the same context as the original parent folder."
- `on_duplicate` — string, on Update file; "If the file is moved to a folder containing a file
  with the same name, or renamed to a name matching an existing file, the API call will fail
  unless this parameter is supplied." Allowed values: `overwrite`, `rename`.
- `source_file_id` — required string, on Copy a file; "The id of the source file."
- `on_duplicate` — string, on Copy a file; "What to do if a file with the same name already
  exists at the destination. If such a file exists and this parameter is not given, the call
  will fail." Allowed values: `overwrite`, `rename`.

**Traps.**
- "List folders" (`GET /api/v1/folders/:id/folders`) returns only that folder's immediate
  children; "List all folders" (`GET /api/v1/courses/:course_id/folders`) is documented
  separately as "a flat list containing all subfolders as well" for the whole course, user, or
  group — same-sounding names, different recursion (docs:
  https://canvas.instructure.com/doc/api/files.html).
- `on_duplicate` carries a different default on every endpoint that names it: file-upload step 1
  states "If no parameter is given, the default is overwrite"; Update file says the call "will
  fail unless this parameter is supplied" on a collision; Copy a file says the same — "If such a
  file exists and this parameter is not given, the call will fail" — with no default named at all
  (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html; docs:
  https://canvas.instructure.com/doc/api/files.html).
- `parent_folder_path`'s restriction is restated with slightly different wording on each endpoint
  that accepts it — file upload's copy reads "This parameter only applies to file uploads in a
  context that has folders, such as a user, a course, or a group," folder-create's copy reads
  "This parameter only applies to new folders in a context that has folders" — and neither
  sentence names accounts as such a context even though `POST /api/v1/accounts/:account_id/folders`
  exists (docs: https://canvas.instructure.com/doc/api/file.file_uploads.html; docs:
  https://canvas.instructure.com/doc/api/files.html).
- A folder's root can be addressed by the literal string `root` in place of a numeric id: "You
  can get the root folder from a context by using `root` as the :id." The page never says whether
  `root` is also accepted as a `parent_folder_id` value when creating something inside it (docs:
  https://canvas.instructure.com/doc/api/files.html).
- Delete folder "will result in comprehensive, irretrievable destruction" only for files (per
  Delete file's own wording); Delete folder's own text is narrower — "Remove the specified
  folder. You can only delete empty folders unless you set the `force` flag" — with no statement
  either way about whether the files inside a force-deleted non-empty folder are themselves
  recoverable (docs: https://canvas.instructure.com/doc/api/files.html).
- `POST /api/v1/folders/:folder_id/files` is a third, folder-scoped starting point for step 1 of
  the upload flow (see "Uploading a file: the three steps"), gated by its own permission: "Only
  those with the `Manage Files` permission on a course or group can upload files to a folder in
  that course or group" (docs: https://canvas.instructure.com/doc/api/files.html).

**Source.** https://canvas.instructure.com/doc/api/files.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/file.file_uploads.html, fetched 2026-09-10

### Exporting a whole course or assignment

**What Canvas does.** Content export is course-, group-, or user-scoped, never assignment-scoped
as its own resource: there is no per-assignment export endpoint. `export_type` picks a fixed
package format, and an optional `select` hash narrows what goes into it by object type and id —
`assignments` is one of the object types `select` accepts, which is how "export one assignment"
is actually expressed. Export is asynchronous: creating one returns a `ContentExport` whose
`progress_url` is polled, and whose `attachment.url` only exists once the export finishes.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/content_exports` | List content exports |
| GET | `/api/v1/groups/:group_id/content_exports` | List content exports, scoped to a group |
| GET | `/api/v1/users/:user_id/content_exports` | List content exports, scoped to a user |
| GET | `/api/v1/courses/:course_id/content_exports/:id` | Show content export |
| POST | `/api/v1/courses/:course_id/content_exports` | Export content from a course |
| POST | `/api/v1/groups/:group_id/content_exports` | Export content from a group |
| POST | `/api/v1/users/:user_id/content_exports` | Export content from a user |

**Parameters.**
- `export_type` — required string; "`common_cartridge`:: Export the contents of the course in
  the Common Cartridge (.imscc) format. `qti`:: Export quizzes from a course in the QTI format.
  `zip`:: Export files from a course, group, or user in a zip file." Allowed values:
  `common_cartridge`, `qti`, `zip`.
- `skip_notifications` — boolean; "Don't send the notifications about the export to the user.
  Default: false."
- `select` — Hash; "The select parameter allows exporting specific data. The keys are object
  types like `files`, `folders`, `pages`, etc. The value for each key is a list of object ids. An
  id can be an integer or a string... Common Cartridge supports all object types. Zip and QTI
  only support the object types as described below. `folders`:: Also supported for zip
  export_type. `files`:: Also supported for zip export_type. `quizzes`:: Also supported for qti
  export_type." Allowed values: `folders`, `files`, `attachments`, `quizzes`, `assignments`,
  `announcements`, `calendar_events`, `discussion_topics`, `modules`, `module_items`, `pages`,
  `rubrics`.
- `ContentExport` object fields: `id`, `created_at`, `export_type`, `attachment` (present "not
  before the export completes or after it becomes unavailable for download"), `progress_url`,
  `user_id`, `workflow_state` (`created`, `exporting`, `exported`, `failed`).

**Traps.**
- There is no `export_type` value for a single assignment, and no assignment-scoped
  `content_exports` endpoint at all — the only three `export_type` values are
  `common_cartridge`, `qti`, and `zip`. Exporting one assignment means
  `export_type=common_cartridge` with `select[assignments][]=<id>`, not a dedicated resource
  (docs: https://canvas.instructure.com/doc/api/content_exports.html).
- `select`'s object types are export-type-gated: "Zip and QTI only support the object types as
  described below" (files/folders for zip, quizzes for qti), while "Common Cartridge supports all
  object types." Requesting `select[assignments][]` under `export_type=zip` or `export_type=qti`
  is outside what the page documents as supported (docs:
  https://canvas.instructure.com/doc/api/content_exports.html).
- The finished export's download link is nested at `attachment.url`, and the same field's own
  comment says it is "not present before the export completes or after it becomes unavailable for
  download" — `progress_url` (see "Long jobs that answer later" in `fundamentals.md`) has to be
  polled to completion before `attachment` exists at all (docs:
  https://canvas.instructure.com/doc/api/content_exports.html).
- The example `ContentExport.attachment` value is itself a nested attachment API object
  (`{"url":"https://example.com/api/v1/attachments/789?download_frd=1"}`), not a full `File`
  object — no `id`, `display_name`, or `size` alongside it in the example (docs:
  https://canvas.instructure.com/doc/api/content_exports.html).

**Source.** https://canvas.instructure.com/doc/api/content_exports.html, fetched 2026-09-10
