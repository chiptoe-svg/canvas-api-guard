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
- rel="current"
- rel="next"
- rel="prev"
- rel="first"
- rel="last"
- access_token

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
- 429

### https://canvas.instructure.com/doc/api/file.endpoint_attributes.html
fetched: 2026-09-10
params:
- data-api-endpoint
- data-api-returntype
- Assignment
- Discussion
- Page
- File
- Folder
- Quiz
- Module
- SessionlessLaunchUrl

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
- needs_grading_count
- syllabus_body
- syllabus_versions
- public_description
- total_scores
- current_grading_period_scores
- grading_periods
- term
- account
- course_progress
- sections
- storage_quota_used_mb
- total_students
- passback_status
- favorites
- teachers
- observed_users
- course_image
- banner_image
- concluded
- post_manually
- all_courses
- permissions
- lti_context_id
- workflow_state
- unpublished
- available
- completed
- deleted

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
- StudentEnrollment
- TeacherEnrollment
- TaEnrollment
- DesignerEnrollment
- ObserverEnrollment
- active
- invited
- completed
- inactive
- deleted
- rejected

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
- students
- avatar_url
- enrollments
- total_students
- passback_status
- permissions

### https://canvas.instructure.com/doc/api/progress.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/progress/:id
params:
- id
- context_id
- context_type
- user_id
- tag
- completion
- workflow_state
- created_at
- updated_at
- message
- results
- url
- queued
- running
- completed
- failed

### https://canvas.instructure.com/doc/api/file.changelog.html
fetched: 2026-09-10
