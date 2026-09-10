# Fundamentals

How Canvas models a course, and the conventions the rest of the API shares: pagination, ids,
dates, HTML fields, and the objects that don't look like what they are.

### Finding the course and who is in it

**What Canvas does.** A course is fetched by listing or by id. Who is enrolled in it is a
separate lookup: enrollments are their own object, fetched per course, per section, or per user,
not embedded in the course response by default.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses` | List courses |
| GET | `/api/v1/courses/:id` | Get a single course |
| GET | `/api/v1/courses/:course_id/enrollments` | List enrollments for a course |
| GET | `/api/v1/sections/:section_id/enrollments` | List enrollments for a section |
| GET | `/api/v1/users/:user_id/enrollments` | List enrollments for a user |

**Parameters.**
- `type[]` — filters by enrollment type: `StudentEnrollment`, `TeacherEnrollment`,
  `TaEnrollment`, `DesignerEnrollment`, `ObserverEnrollment`
- `state[]` — filters by enrollment workflow state
- `role[]` — filters by a custom course-level role

**Traps.**
- `state[]` has a documented default: if omitted, `active` and `invited` enrollments are
  returned — a plain `GET .../enrollments` with no `state[]` silently hides completed,
  inactive, deleted, and rejected enrollments (docs:
  https://canvas.instructure.com/doc/api/enrollments.html).
- Enrollments are three separate endpoints (by course, by section, by user), not one endpoint
  with a scope parameter — "who is in this course" and "what is this user enrolled in" are
  different calls (docs: https://canvas.instructure.com/doc/api/enrollments.html).

**Source.** https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/enrollments.html, fetched 2026-09-10

### Getting a whole collection back

**What Canvas does.** Any endpoint that returns a collection paginates it. The response carries
a `Link` header with absolute URLs tagged `rel="current"`, `rel="next"`, `rel="prev"`,
`rel="first"`, and sometimes `rel="last"`. Canvas says these links "should be treated as
opaque" — follow them rather than constructing page URLs by hand.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:id/discussion_topics.json` | The documentation's own worked example of a paginated response |

**Parameters.**
- `per_page` — items per page; documented default is 10, with "an unspecified limit to how big
  you can set `per_page` to"
- `Link` — the response header carrying the pagination URLs

**Traps.**
- `rel="last"` is not guaranteed: it "may also be excluded if the total count is too expensive
  to compute" — code that always expects a last link to jump to the end of a collection can
  break on a large one (docs: https://canvas.instructure.com/doc/api/file.pagination.html).
- The first page has no `rel="prev"` link at all; not every rel value appears on every response
  (docs: https://canvas.instructure.com/doc/api/file.pagination.html).
- If an `access_token` query parameter was used to authenticate, it "will not be included in the
  returned links, and must be re-appended" before the caller follows them
  (docs: https://canvas.instructure.com/doc/api/file.pagination.html).
- `per_page`'s ceiling is not a fixed documented number — check the `Link` header rather than
  assume a large `per_page` returned everything in one page
  (docs: https://canvas.instructure.com/doc/api/file.pagination.html).

**Source.** https://canvas.instructure.com/doc/api/file.pagination.html, fetched 2026-09-10

### Asking for more of an object

**What Canvas does.** A plain GET on a course or section is deliberately thin: it does not
return people, aggregates, or extra bodies unless asked. `include[]` is how an endpoint is asked
for more. The list-courses and single-course endpoints share nearly the same `include[]` menu —
the docs describe the single-course one as accepting "the same include[] parameters as the list
action plus:" — but "nearly" matters: one value from the list menu is missing on the
single-course endpoint, and it adds three of its own. The sections endpoint has an entirely
separate, much smaller menu.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses` | List courses, with `include[]` |
| GET | `/api/v1/courses/:id` | Get a single course, with an almost-identical `include[]` |
| GET | `/api/v1/courses/:course_id/sections` | List course sections, with `include[]` |

**Parameters.**
- `include[]` on `GET /api/v1/courses` (list): `needs_grading_count`, `syllabus_body`,
  `syllabus_versions`, `public_description`, `total_scores`, `current_grading_period_scores`,
  `grading_periods`, `term`, `account`, `course_progress`, `sections`, `storage_quota_used_mb`,
  `total_students`, `passback_status`, `favorites`, `teachers`, `observed_users`,
  `course_image`, `banner_image`, `concluded`, `post_manually`
- `include[]` on `GET /api/v1/courses/:id` (single course): the same 21 values as the list
  endpoint, minus `grading_periods`, plus `all_courses`, `permissions`, and `lti_context_id`.
  Written out in full: `needs_grading_count`, `syllabus_body`, `syllabus_versions`,
  `public_description`, `total_scores`, `current_grading_period_scores`, `term`, `account`,
  `course_progress`, `sections`, `storage_quota_used_mb`, `total_students`, `passback_status`,
  `favorites`, `teachers`, `observed_users`, `all_courses`, `permissions`, `course_image`,
  `banner_image`, `concluded`, `lti_context_id`, `post_manually`
- `include[]` on `GET /api/v1/courses/:course_id/sections`: `students`, `avatar_url`,
  `enrollments`, `total_students`, `passback_status`, `permissions`

**Traps.**
- The single-course endpoint's `include[]` is not a separate menu from the list endpoint's — it
  is nearly the same set. Reading it as unrelated (because it is not byte-identical) is as wrong
  as assuming it is byte-identical: `grading_periods` works on the list endpoint but not on the
  single-course one, while `all_courses`, `permissions`, and `lti_context_id` work on the
  single-course endpoint but not on the list one. Everything else in both 21/23-value lists is
  shared (docs: https://canvas.instructure.com/doc/api/courses.html — the "Accepts the same
  include[] parameters as the list action plus:" sentence immediately above the single-course
  endpoint's parameter table; note an almost identical sentence appears earlier on the same page
  for a single *user* endpoint, which is not this one).
- `total_students` and `passback_status` are named identically in the courses `include[]`
  enumerations and the sections `include[]` enumeration, but they are independently-documented
  per object type — passing one on an endpoint that does not declare it is not guaranteed to do
  anything (docs: https://canvas.instructure.com/doc/api/courses.html; docs:
  https://canvas.instructure.com/doc/api/sections.html).
- `include[]` values are not shared across object types: `students` and `avatar_url` exist only
  on the sections endpoint, not on either courses endpoint
  (docs: https://canvas.instructure.com/doc/api/sections.html).
- Neither page states a cost for any individual `include[]` value, but `total_students` is a
  count, and pagination's own documentation warns that a total count "may... be too expensive to
  compute" when Canvas has to produce one — treat a long `include[]` list as added work per
  request, not a free flag (docs: https://canvas.instructure.com/doc/api/file.pagination.html).

**Source.** https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/sections.html, fetched 2026-09-10

### Naming a thing that is not a Canvas id

**What Canvas does.** Most path slots that take a numeric Canvas id — `:id`, `:course_id`, and
the like — also accept a SIS id in their place, written as `sis_<type>_id:<value>`. There is no
separate parameter and no separate endpoint; it is a different string in the same slot.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/sis_course_id:A1234/assignments` | The documentation's own worked example of the substitution |

**Parameters.** The documented SIS id prefixes: `sis_account_id`, `sis_course_id`,
`sis_group_id`, `sis_group_category_id`, `sis_integration_id`, `sis_login_id`,
`sis_section_id`, `sis_term_id`, `sis_user_id`.

**Traps.**
- The value has to be UTF-8 encoded and then URI-escaped, including a literal `/` inside it —
  the documented example turns `CS/101.11é` into `CS%2F101%2E11%C3%A9`. Passing a SIS id with a
  slash unescaped breaks the path (docs: https://canvas.instructure.com/doc/api/file.object_ids.html).
- `sis_integration_id` is documented for users and courses only, not for every object type that
  has a SIS id — the prefix form is not uniform across all nine SIS types
  (docs: https://canvas.instructure.com/doc/api/file.object_ids.html).

**Source.** https://canvas.instructure.com/doc/api/file.object_ids.html, fetched 2026-09-10

### Published, unpublished, and workflow_state

**What Canvas does.** A course carries a `workflow_state`, and the documented values are
`unpublished`, `available`, `completed`, and `deleted`. "Published" is not a separate boolean
next to `workflow_state` for a course — it is one of those state values. Other Canvas object
types carry their own `workflow_state` with their own value set; this reference confirms only
the course one and the Progress one (see "Long jobs that answer later") directly.

**Endpoints.** None — `workflow_state` is a field on objects whose endpoints are listed
elsewhere in this reference, not an endpoint of its own.

**Parameters.** None recorded for this section.

**Traps.**
- A course's `workflow_state` values (`unpublished`, `available`, `completed`, `deleted`) are
  not a Canvas-wide enum. The Progress object, documented separately, uses `queued`, `running`,
  `completed`, `failed` for the same field name — matching values (`completed`) do not imply a
  shared vocabulary (docs: https://canvas.instructure.com/doc/api/courses.html; docs:
  https://canvas.instructure.com/doc/api/progress.html).
- `completed` and `deleted` are both terminal-sounding but distinct: nothing in the fetched
  courses documentation says a completed course is removed. Do not treat "the term ended" and
  "the course is gone" as the same state without checking which value is actually returned
  (docs: https://canvas.instructure.com/doc/api/courses.html).

**Source.** https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10

### Dates, and who they apply to

**What Canvas does.** A course carries its own `start_at`/`end_at`. A section can carry its own
`start_at`/`end_at` too, but a section's dates do nothing to enrollment access by themselves —
Canvas describes the section flag as restricting "user enrollments to the start and end dates of
the section," and that restriction is switched on separately from the course-level one.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:id` | Update a course, including its dates |
| PUT | `/api/v1/sections/:id` | Update a section, including its dates |

**Parameters.**
- `course[start_at]`, `course[end_at]`, `course[restrict_enrollments_to_course_dates]`
- `course_section[start_at]`, `course_section[end_at]`,
  `course_section[restrict_enrollments_to_section_dates]`

**Traps.**
- Setting `course_section[start_at]`/`course_section[end_at]` without also setting
  `course_section[restrict_enrollments_to_section_dates]` leaves the section dates as inert
  metadata — the restriction is a separate switch
  (docs: https://canvas.instructure.com/doc/api/sections.html).
- The course-level switch and the section-level switch are two different, independently-named
  parameters (`restrict_enrollments_to_course_dates` vs.
  `restrict_enrollments_to_section_dates`). Turning on one does not turn on the other
  (docs: https://canvas.instructure.com/doc/api/courses.html; docs:
  https://canvas.instructure.com/doc/api/sections.html).

**Source.** https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/sections.html, fetched 2026-09-10

### HTML fields and what Canvas does to them

**What Canvas does.** Fields Canvas treats as HTML — a course's `syllabus_body`, fetched via
`include[]=syllabus_body` — are not returned as plain markup. Canvas can annotate a link inside
that HTML that points at one of its own objects with two extra attributes:
`data-api-endpoint` ("A URL where the linked object can be accessed via the API") and
`data-api-returntype` ("The type of data returned"). The documented return types are
`Assignment`, `Discussion`, `Page`, `File`, `Folder`, `Quiz`, `Module`, and
`SessionlessLaunchUrl`; a return type is wrapped in brackets, e.g. `[Assignment]`, when the
linked endpoint returns a list rather than one object.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:id` | Get a course; `include[]=syllabus_body` returns an HTML field that can carry these attributes |

**Parameters.** `include[]` (`syllabus_body`), `data-api-endpoint`, `data-api-returntype`.

**Traps.**
- The documented example only shows the attributes added to a link that already points at a
  Canvas object (a wiki page). The documentation does not claim every anchor tag inside an HTML
  field gets these attributes — an external link is not shown getting them
  (docs: https://canvas.instructure.com/doc/api/file.endpoint_attributes.html).
- `data-api-returntype` lists `Quiz`, `Discussion`, and `Assignment` as three separate values,
  not aliases of one another. Code that parses this attribute to decide "is this thing
  gradable" cannot collapse them into one type without extra logic
  (docs: https://canvas.instructure.com/doc/api/file.endpoint_attributes.html).

**Source.** https://canvas.instructure.com/doc/api/file.endpoint_attributes.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10

### A quiz is an assignment underneath, and so is a graded discussion

**What Canvas does.** Canvas's HTML-link annotation (see the previous section) tags
API-linked content with a `data-api-returntype` of `Assignment`, `Discussion`, or `Quiz` as
three distinct, separately-documented values, not synonyms of each other. Whether a graded quiz
or a graded discussion additionally allocates an underlying Assignment record — for grading,
grade passback, and assignment-group membership — is real Canvas behaviour that instructors and
integrations rely on, but it is not documented on any of the nine pages this reference was built
from. None of them describe the Quiz, Discussion, or Assignment object schema.

**Endpoints.** None — no page fetched for this reference documents a Quiz, Discussion, or
Assignment endpoint.

**Parameters.** None recorded for this section beyond `data-api-returntype`, already recorded
under "HTML fields and what Canvas does to them."

**Traps.**
- Do not treat this reference as confirmation of how a graded quiz or graded discussion appears
  in the gradebook or the assignments list. That mechanism is outside what the nine pages in
  this task document; it needs to be verified against Canvas's own Quizzes and Assignments API
  pages before anything is built on it
  (docs: https://canvas.instructure.com/doc/api/file.endpoint_attributes.html — the only fact
  this section can actually ground is that the three return types are listed separately).

**Source.** https://canvas.instructure.com/doc/api/file.endpoint_attributes.html, fetched 2026-09-10

### Long jobs that answer later

**What Canvas does.** Some Canvas operations don't finish inside the request that starts them.
Canvas responds to the triggering call and hands back a reference to a Progress object; the
caller polls that object separately to find out when the job is actually done. The Progress
object "Return[s] completion and status information about an asynchronous job."

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/progress/:id` | Query the state of a long-running job |

**Parameters.** Progress is read-only; there is nothing to send. Its fields: `id`,
`context_id`, `context_type`, `user_id`, `tag`, `completion`, `workflow_state`, `created_at`,
`updated_at`, `message`, `results`, `url`.

**Traps.**
- `workflow_state` on a Progress object is not the same value space as a course's
  `workflow_state`: the documented values are `queued`, `running`, `completed`, `failed`, with
  no `unpublished` or `deleted` (docs: https://canvas.instructure.com/doc/api/progress.html).
- `results` is documented as "omitted when job is still pending" — not present as `null`, but
  absent. Code that expects a `results` key to always exist will fail on a still-running job
  (docs: https://canvas.instructure.com/doc/api/progress.html).

**Source.** https://canvas.instructure.com/doc/api/progress.html, fetched 2026-09-10

### When the API pushes back

**What Canvas does.** Canvas enforces a dynamic per-caller cost budget rather than a fixed
requests-per-minute cap. Every request debits a cost from the caller's quota, the quota
replenishes over time, and concurrent requests carry an additional penalty on top of their own
cost, credited back once the request completes. Separately, this documentation page does not
carry the API's own history of changes — it points elsewhere for that.

**Endpoints.** None — throttling headers are attached to every response, not one endpoint, and
the change log is not an endpoint at all.

**Parameters.** Response headers: `X-Request-Cost` ("a floating point number of the amount that
request deducted from your remaining quota"), `X-Rate-Limit-Remaining` (returned when throttling
applies).

**Traps.**
- Hitting the limit does not return an ordinary error to retry blindly — it is HTTP `429`
  ("Forbidden (Rate Limit Exceeded)"), and the documented guidance is to "be prepared for this
  error, and retry the request at a later time," not immediately
  (docs: https://canvas.instructure.com/doc/api/file.throttling.html).
- The documented risk factor is concurrency, not raw call volume: "any API client that makes no
  more than one simultaneous request is unlikely to be throttled"
  (docs: https://canvas.instructure.com/doc/api/file.throttling.html).
- This reference's own change-log page is not the change log. It states only that the API
  change log — "for additions, changes, deprecations, and removals" — lives on the separate
  Canvas Community site, and it carries a notice that the docs host itself is being relocated
  (docs: https://canvas.instructure.com/doc/api/file.changelog.html).

**Source.** https://canvas.instructure.com/doc/api/file.throttling.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/file.changelog.html, fetched 2026-09-10
