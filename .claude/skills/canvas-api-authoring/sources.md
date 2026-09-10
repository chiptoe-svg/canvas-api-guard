# Sources

Every documentation page these references draw on, with the endpoints and parameter names taken
from it. `tools/canvas-docs-check.py` reads this file and reports anything that no longer
appears on its page.

Coverage is exactly what is recorded here. A parameter used in a reference but not recorded here
is not checked, so recording the claim is part of writing the section.

Base URL: `https://canvas.instructure.com/doc/api/`

## references/fundamentals.md

### https://canvas.instructure.com/doc/api/file.pagination.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:id/discussion_topics.json
params:
- per_page
- Link

### https://canvas.instructure.com/doc/api/file.object_ids.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/sis_course_id:A1234/assignments
params:
- sis_account_id
- sis_course_id
- sis_group_id
- sis_group_category_id
- sis_integration_id
- sis_login_id
- sis_section_id
- sis_term_id
- sis_user_id

### https://canvas.instructure.com/doc/api/file.throttling.html
fetched: 2026-09-10
params:
- X-Request-Cost
- X-Rate-Limit-Remaining

### https://canvas.instructure.com/doc/api/file.endpoint_attributes.html
fetched: 2026-09-10
params:
- data-api-endpoint
- data-api-returntype

### https://canvas.instructure.com/doc/api/courses.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses
- GET /api/v1/courses/:id
- PUT /api/v1/courses/:id
params:
- include[]
- course[start_at]
- course[end_at]
- course[restrict_enrollments_to_course_dates]

### https://canvas.instructure.com/doc/api/enrollments.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/enrollments
- GET /api/v1/sections/:section_id/enrollments
- GET /api/v1/users/:user_id/enrollments
params:
- type[]
- state[]
- role[]

### https://canvas.instructure.com/doc/api/sections.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/sections
- PUT /api/v1/sections/:id
params:
- include[]
- course_section[start_at]
- course_section[end_at]
- course_section[restrict_enrollments_to_section_dates]

### https://canvas.instructure.com/doc/api/progress.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/progress/:id
params:
- workflow_state
- completion
- results
- tag

### https://canvas.instructure.com/doc/api/file.changelog.html
fetched: 2026-09-10
