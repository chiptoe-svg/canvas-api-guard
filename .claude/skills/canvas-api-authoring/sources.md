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

## references/assignments.md

### https://canvas.instructure.com/doc/api/assignments.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/assignments
- GET /api/v1/courses/:course_id/assignments/:id
- GET /api/v1/courses/:course_id/assignments
- PUT /api/v1/courses/:course_id/assignments/:id
- DELETE /api/v1/courses/:course_id/assignments/:id
- GET /api/v1/courses/:course_id/assignments/:assignment_id/overrides
- GET /api/v1/courses/:course_id/assignments/:assignment_id/overrides/:id
- POST /api/v1/courses/:course_id/assignments/:assignment_id/overrides
- PUT /api/v1/courses/:course_id/assignments/:assignment_id/overrides/:id
- DELETE /api/v1/courses/:course_id/assignments/:assignment_id/overrides/:id
params:
- assignment[name]
- assignment[position]
- assignment[assignment_group_id]
- assignment[points_possible]
- assignment[grading_type]
- pass_fail
- percent
- letter_grade
- gpa_scale
- points
- not_graded
- assignment[description]
- assignment[notify_of_update]
- assignment[submission_types][]
- online_quiz
- none
- on_paper
- discussion_topic
- external_tool
- online_upload
- online_text_entry
- online_url
- media_recording
- student_annotation
- assignment[allowed_extensions][]
- assignment[external_tool_tag_attributes]
- assignment[annotatable_attachment_id]
- assignment[quiz_lti]
- assignment[turnitin_enabled]
- assignment[vericite_enabled]
- assignment[grading_standard_id]
- assignment[omit_from_final_grade]
- assignment[hide_in_gradebook]
- assignment[due_at]
- assignment[lock_at]
- assignment[unlock_at]
- assignment[only_visible_to_overrides]
- assignment[assignment_overrides][]
- assignment_override[student_ids][]
- assignment_override[title]
- assignment_override[group_id]
- assignment_override[course_section_id]
- assignment_override[due_at]
- assignment_override[unlock_at]
- assignment_override[lock_at]
- group_category_id
- AssignmentOverride
- assignment[allowed_attempts]
- unpublishable
- workflow_state
- assignment[published]
- draft state
- assignment[peer_reviews]
- assignment[automatic_peer_reviews]
- assignment[peer_review]
- assignment[peer_review][points_possible]
- assignment[peer_review][grading_type]
- assignment[peer_review][due_at]
- assignment[peer_review][lock_at]
- assignment[peer_review][unlock_at]
- assignment[peer_review][peer_review_overrides][]

### https://canvas.instructure.com/doc/api/assignment_groups.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/assignment_groups
- GET /api/v1/courses/:course_id/assignment_groups/:assignment_group_id
- POST /api/v1/courses/:course_id/assignment_groups
- PUT /api/v1/courses/:course_id/assignment_groups/:assignment_group_id
- DELETE /api/v1/courses/:course_id/assignment_groups/:assignment_group_id
params:
- name
- position
- group_weight
- sis_source_id
- integration_data
- rules
- drop_lowest
- drop_highest
- never_drop
- move_assignments_to

### https://canvas.instructure.com/doc/api/assignment_extensions.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/assignments/:assignment_id/extensions
params:
- assignment_extensions[][user_id]
- assignment_extensions[][extra_attempts]
- 403
- 400

### https://canvas.instructure.com/doc/api/peer_reviews.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/assignments/:assignment_id/peer_reviews
- GET /api/v1/sections/:section_id/assignments/:assignment_id/peer_reviews
- POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:submission_id/peer_reviews
- DELETE /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:submission_id/peer_reviews
- POST /api/v1/courses/:course_id/assignments/:assignment_id/allocate
params:
- include[]
- submission_comments
- user
- user_id
- PeerReview
- assessor_id
- asset_id
- asset_type
- id
- workflow_state
- assigned
- completed

### https://canvas.instructure.com/doc/api/late_policy.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:id/late_policy
- POST /api/v1/courses/:id/late_policy
- PATCH /api/v1/courses/:id/late_policy
params:
- late_policy[missing_submission_deduction_enabled]
- late_policy[missing_submission_deduction]
- late_policy[late_submission_deduction_enabled]
- late_policy[late_submission_deduction]
- late_policy[late_submission_interval]
- late_policy[late_submission_minimum_percent_enabled]
- late_policy[late_submission_minimum_percent]
- bad_request
- hour
- course_id
- created_at
- updated_at

### https://canvas.instructure.com/doc/api/learning_object_dates.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/assignments/:assignment_id/date_details
- PUT /api/v1/courses/:course_id/assignments/:assignment_id/date_details
params:
- include[]
- exclude[]
- due_at
- unlock_at
- lock_at
- only_visible_to_overrides
- assignment_overrides[]

## references/quizzes.md

### https://canvas.instructure.com/doc/api/quizzes.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/quizzes
- GET /api/v1/courses/:course_id/quizzes
- GET /api/v1/courses/:course_id/quizzes/:id
- PUT /api/v1/courses/:course_id/quizzes/:id
- DELETE /api/v1/courses/:course_id/quizzes/:id
- POST /api/v1/courses/:course_id/quizzes/:id/reorder
- POST /api/v1/courses/:course_id/quizzes/:id/validate_access_code
params:
- quiz[title]
- quiz[description]
- quiz[quiz_type]
- quiz_type
- practice_quiz
- assignment
- graded_survey
- survey
- quiz[assignment_group_id]
- quiz[notify_of_update]
- search_term
- question_types
- anonymous_submissions
- quiz[time_limit]
- quiz[allowed_attempts]
- quiz[scoring_policy]
- keep_highest
- keep_latest
- quiz[one_question_at_a_time]
- quiz[cant_go_back]
- quiz[hide_results]
- always
- until_after_last_attempt
- quiz[show_correct_answers]
- quiz[show_correct_answers_last_attempt]
- quiz[show_correct_answers_at]
- quiz[hide_correct_answers_at]
- quiz[one_time_results]
- quiz[shuffle_answers]
- quiz[access_code]
- quiz[ip_filter]
- access_code
- quiz[published]
- unpublishable
- locked_for_user
- lock_info
- lock_explanation
- quiz[lock_at]
- quiz[unlock_at]
- order[][id]
- order[][type]
- question
- group
- points_possible

### https://canvas.instructure.com/doc/api/quiz_questions.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/questions
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/questions/:id
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/questions
- PUT /api/v1/courses/:course_id/quizzes/:quiz_id/questions/:id
- DELETE /api/v1/courses/:course_id/quizzes/:quiz_id/questions/:id
params:
- question[question_name]
- question[question_text]
- question[quiz_group_id]
- question[question_type]
- calculated_question
- essay_question
- file_upload_question
- fill_in_multiple_blanks_question
- matching_question
- multiple_answers_question
- multiple_choice_question
- multiple_dropdowns_question
- numerical_question
- short_answer_question
- text_only_question
- true_false_question
- question[position]
- question[points_possible]
- question[correct_comments]
- question[incorrect_comments]
- question[neutral_comments]
- question[text_after_answers]
- question[answers]
- answer_text
- answer_weight
- answer_comments
- text_after_answers
- answer_match_left
- answer_match_right
- matching_answer_incorrect_matches
- numerical_answer_type
- exact_answer
- range_answer
- precision_answer
- exact
- margin
- approximate
- precision
- start
- end
- blank_id
- id
- quiz_submission_id
- quiz_submission_attempt

### https://canvas.instructure.com/doc/api/quiz_question_groups.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/groups
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/groups
- PUT /api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id
- DELETE /api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/groups/:id/reorder
params:
- quiz_groups[][name]
- quiz_groups[][pick_count]
- quiz_groups[][question_points]
- quiz_groups[][assessment_question_bank_id]
- order[][id]
- order[][type]
- question
- pick_count

### https://canvas.instructure.com/doc/api/assessment_question_banks.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/question_banks
- GET /api/v1/question_banks/:id
- GET /api/v1/question_banks/:id/questions
params:
- context_type
- Course
- Account
- context_id
- include_question_count
- variables
- formulas
- AssessmentQuestion

### https://canvas.instructure.com/doc/api/quiz_submissions.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/submissions
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/submission
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/submissions
- PUT /api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id/complete
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/submissions/:id/time
params:
- include[]
- submission
- quiz
- user
- access_code
- preview
- quiz_submissions[][attempt]
- quiz_submissions[][fudge_points]
- quiz_submissions[][questions]
- score
- comment
- attempt
- validation_token
- end_at
- time_left
- workflow_state
- untaken
- pending_review
- complete
- settings_only

### https://canvas.instructure.com/doc/api/quiz_submission_questions.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/quiz_submissions/:quiz_submission_id/questions
- POST /api/v1/quiz_submissions/:quiz_submission_id/questions
- GET /api/v1/quiz_submissions/:quiz_submission_id/questions/:id/formatted_answer
- PUT /api/v1/quiz_submissions/:quiz_submission_id/questions/:id/flag
- PUT /api/v1/quiz_submissions/:quiz_submission_id/questions/:id/unflag
params:
- include[]
- quiz_question
- attempt
- validation_token
- access_code
- quiz_questions[]
- answer
- flagged
- answers
- answer_id
- match_id

### https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/assignment_overrides
- GET /api/v1/courses/:course_id/new_quizzes/assignment_overrides
params:
- quiz_assignment_overrides[][quiz_ids][]
- due_dates
- all_dates
- base
- id

### https://canvas.instructure.com/doc/api/quiz_extensions.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/extensions
params:
- quiz_extensions[][user_id]
- quiz_extensions[][extra_attempts]
- quiz_extensions[][extra_time]
- quiz_extensions[][manually_unlocked]
- quiz_extensions[][extend_from_now]
- quiz_extensions[][extend_from_end_at]

### https://canvas.instructure.com/doc/api/course_quiz_extensions.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/quiz_extensions
params:
- user_id
- extra_attempts
- extra_time
- manually_unlocked
- extend_from_now
- extend_from_end_at

### https://canvas.instructure.com/doc/api/quiz_ip_filters.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/ip_filters
params:

### https://canvas.instructure.com/doc/api/quiz_reports.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/reports
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/reports
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/reports/:id
- DELETE /api/v1/courses/:course_id/quizzes/:quiz_id/reports/:id
params:
- includes_all_versions
- quiz_report[report_type]
- student_analysis
- item_analysis
- quiz_report[includes_all_versions]
- include
- file
- progress
- generatable
- anonymous
- workflow_state
- queued

### https://canvas.instructure.com/doc/api/quiz_statistics.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/quizzes/:quiz_id/statistics
params:
- all_versions
- multiple_attempts_exist
- question_statistics
- submission_statistics
- True/False
- Multiple Choice
- File Upload
- Formula
- Essay
- Multiple Dropdowns
- Fill In Multiple Blanks

### https://canvas.instructure.com/doc/api/new_quizzes.html
fetched: 2026-09-10
endpoints:
params:

### https://canvas.instructure.com/doc/api/new_quiz_items.html
fetched: 2026-09-10
endpoints:
params:
