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

### https://canvas.instructure.com/doc/api/assignments.html
fetched: 2026-09-10
params:
- submission_types
- online_quiz
- discussion_topic
- quiz_id
- is_quiz_assignment

### https://canvas.instructure.com/doc/api/quizzes.html
fetched: 2026-09-10
params:
- quiz_type
- assignment
- graded_survey
- practice_quiz
- survey
- quiz[assignment_group_id]
- speedgrader_url
- assignment_id

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

## references/rubrics-and-grades.md

### https://canvas.instructure.com/doc/api/rubrics.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/rubrics
- PUT /api/v1/courses/:course_id/rubrics/:id
- GET /api/v1/courses/:course_id/rubrics
- GET /api/v1/courses/:course_id/rubrics/:id
- DELETE /api/v1/courses/:course_id/rubrics/:id
- POST /api/v1/courses/:course_id/rubric_associations
- PUT /api/v1/courses/:course_id/rubric_associations/:id
- DELETE /api/v1/courses/:course_id/rubric_associations/:id
- POST /api/v1/courses/:course_id/rubric_associations/:rubric_association_id/rubric_assessments
- PUT /api/v1/courses/:course_id/rubric_associations/:rubric_association_id/rubric_assessments/:id
- DELETE /api/v1/courses/:course_id/rubric_associations/:rubric_association_id/rubric_assessments/:id
params:
- rubric[title]
- rubric[free_form_criterion_comments]
- rubric[criteria]
- rubric[skip_updating_points_possible]
- rubric_association_id
- include[]
- assessments
- graded_assessments
- peer_assessments
- associations
- assignment_associations
- course_associations
- account_associations
- style
- full
- comments_only
- id
- description
- long_description
- points
- criterion_use_range
- ratings
- criterion_id
- rubric_association[rubric_id]
- rubric_association[association_id]
- rubric_association[association_type]
- Assignment
- Course
- Account
- rubric_association[title]
- rubric_association[use_for_grading]
- rubric_association[hide_score_total]
- rubric_association[purpose]
- grading
- bookmark
- rubric_association[bookmarked]
- rubric_assessment
- rubric_assessment[criterion_id][points]
- rubric_assessment[criterion_id][comments]
- rubric_assessment[user_id]
- rubric_assessment[assessment_type]
- peer_review
- provisional_grade
- provisional
- final
- graded_anonymously

### https://canvas.instructure.com/doc/api/submissions.html
fetched: 2026-09-10
endpoints:
- PUT /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id
- GET /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id
- GET /api/v1/courses/:course_id/assignments/:assignment_id/submissions
- POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions/update_grades
- POST /api/v1/courses/:course_id/submissions/update_grades
params:
- submission[posted_grade]
- submission[excuse]
- submission[late_policy_status]
- late
- missing
- extended
- none
- submission[seconds_late_override]
- submission[peer_review]
- submission[sticker]
- apple
- basketball
- bell
- book
- bookbag
- briefcase
- bus
- calendar
- chem
- design
- pencil
- beaker
- paintbrush
- computer
- column
- pen
- tablet
- telescope
- calculator
- paperclip
- composite_notebook
- scissors
- ruler
- clock
- globe
- grad
- gym
- mail
- microscope
- mouse
- music
- notebook
- page
- panda1
- panda2
- panda3
- panda4
- panda5
- panda6
- panda7
- panda8
- panda9
- presentation
- science
- science2
- star
- tag
- tape
- target
- trophy
- prefer_points_over_scheme
- include[]
- submission_comments
- visibility
- sub_assignment_submissions
- peer_review_submissions
- provisional_grades
- group
- grade_data[<student_id>][posted_grade]
- grade_data[<student_id>][excuse]
- grade_data[<student_id>][rubric_assessment]
- grade_data[<assignment_id>][<student_id>]
- rubric_assessment[criterion_id][rating_id]
- posted_at
- assignment_id
- assignment
- course
- attempt
- body
- grade
- grade_matches_current_submission
- html_url
- preview_url
- score
- submission_type
- submitted_at
- url
- user_id
- grader_id
- graded_at
- user
- assignment_visible
- excused
- points_deducted
- seconds_late
- workflow_state
- extra_attempts
- anonymous_id
- read_status
- redo_request
- comment[text_comment]
- comment[attempt]
- comment[group_comment]
- comment[media_comment_id]
- comment[media_comment_type]
- audio
- video
- comment[file_ids][]
- id
- author_id
- author_name
- author
- comment
- created_at
- edited_at
- media_comment

### https://canvas.instructure.com/doc/api/grading_standards.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/grading_standards
- GET /api/v1/courses/:course_id/grading_standards
- GET /api/v1/courses/:course_id/grading_standards/:grading_standard_id
- PUT /api/v1/courses/:course_id/grading_standards/:grading_standard_id
- DELETE /api/v1/courses/:course_id/grading_standards/:grading_standard_id
params:
- title
- points_based
- scaling_factor
- grading_scheme_entry[][name]
- grading_scheme_entry[][value]
- id
- context_type
- context_id
- grading_scheme
- name
- value
- calculated_value

### https://canvas.instructure.com/doc/api/grading_periods.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/grading_periods
- GET /api/v1/courses/:course_id/grading_periods/:id
- PUT /api/v1/courses/:course_id/grading_periods/:id
- DELETE /api/v1/courses/:course_id/grading_periods/:id
params:
- grading_periods[][start_date]
- grading_periods[][end_date]
- grading_periods[][weight]
- close_date
- is_closed

### https://canvas.instructure.com/doc/api/enrollments.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/enrollments
- GET /api/v1/users/:user_id/enrollments
params:
- grading_period_id
- current_grade
- final_grade
- current_score
- final_score
- current_points
- unposted_current_grade
- unposted_final_grade
- unposted_current_score
- unposted_final_score
- unposted_current_points
- override_grade
- override_score
- has_grading_periods
- totals_for_all_grading_periods_option
- current_grading_period_title
- current_grading_period_id
- current_period_override_grade
- current_period_override_score
- current_period_unposted_current_score
- current_period_unposted_final_score
- current_period_unposted_current_grade
- current_period_unposted_final_grade

### https://canvas.instructure.com/doc/api/courses.html
fetched: 2026-09-10
endpoints:
- PUT /api/v1/courses/:id
- GET /api/v1/courses/:course_id/settings
- PUT /api/v1/courses/:course_id/settings
params:
- course[post_manually]
- course[hide_final_grades]
- allow_final_grade_override
- hide_final_grades
- grading_standard_enabled
- grading_standard_id
- course[grading_standard_id]

### https://canvas.instructure.com/doc/api/gradebook_history.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/gradebook_history/days
- GET /api/v1/courses/:course_id/gradebook_history/:date
- GET /api/v1/courses/:course_id/gradebook_history/:date/graders/:grader_id/assignments/:assignment_id/submissions
- GET /api/v1/courses/:course_id/gradebook_history/feed
params:
- date
- grader_id
- assignment_id
- user_id
- ascending
- graders
- assignments
- name
- current_grade
- current_graded_at
- current_grader
- grade_matches_current_submission
- graded_at
- grader
- id
- new_grade
- new_graded_at
- new_grader
- previous_grade
- previous_graded_at
- previous_grader
- score
- user_name
- submission_type
- url
- workflow_state
- submission_id
- versions

## references/submissions-and-files.md

### https://canvas.instructure.com/doc/api/submissions.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/assignments/:assignment_id/submissions
- GET /api/v1/sections/:section_id/assignments/:assignment_id/submissions
- GET /api/v1/courses/:course_id/students/submissions
- GET /api/v1/sections/:section_id/students/submissions
- GET /api/v1/courses/:course_id/assignments/:assignment_id/submission_summary
- GET /api/v1/sections/:section_id/assignments/:assignment_id/submission_summary
- GET /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id
- GET /api/v1/sections/:section_id/assignments/:assignment_id/submissions/:user_id
- GET /api/v1/courses/:course_id/assignments/:assignment_id/anonymous_submissions/:anonymous_id
- GET /api/v1/sections/:section_id/assignments/:assignment_id/anonymous_submissions/:anonymous_id
- POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id/files
- POST /api/v1/sections/:section_id/assignments/:assignment_id/submissions/:user_id/files
params:
- include[]
- grouped
- assignment_id
- user_id
- grader_id
- canvadoc_document_id
- submitted_at
- score
- attempt
- body
- grade
- grade_matches_current_submission
- preview_url
- redo_request
- url
- late
- assignment_visible
- workflow_state
- submitted
- unsubmitted
- graded
- pending_review
- submission_history
- submission_comments
- submission_html_comments
- rubric_assessment
- assignment
- visibility
- course
- user
- group
- read_status
- student_entered_score
- student_ids[]
- assignment_ids[]
- post_to_sis
- submitted_since
- graded_since
- grading_period_id
- enrollment_state
- active
- concluded
- state_based_on_date
- order
- id
- graded_at
- order_direction
- ascending
- descending
- total_scores
- sub_assignment_submissions
- peer_review_submissions
- include_deactivated
- ungraded
- not_submitted
- full_rubric_assessment
- anonymous_id
- submission[file_ids][]

### https://canvas.instructure.com/doc/api/files.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/files/:id/public_url
- GET /files/:file_id/download
- GET /courses/:course_id/files/:file_id/download
- GET /api/v1/files/:id
- GET /api/v1/courses/:course_id/files/:id
- POST /api/v1/courses/:course_id/folders
- POST /api/v1/folders/:folder_id/folders
- GET /api/v1/folders/:id
- GET /api/v1/courses/:course_id/folders/by_path/*full_path
- GET /api/v1/courses/:course_id/folders
- GET /api/v1/folders/:id/folders
- PUT /api/v1/folders/:id
- DELETE /api/v1/folders/:id
- POST /api/v1/folders/:folder_id/files
- POST /api/v1/folders/:dest_folder_id/copy_file
- PUT /api/v1/files/:id
- POST /api/v1/accounts/:account_id/folders
params:
- submission_id
- preview_url
- include[]
- user
- replacement_chain_context_type
- replacement_chain_context_id
- url
- download_frd=1
- name
- parent_folder_id
- parent_folder_path
- lock_at
- unlock_at
- locked
- hidden
- position
- force
- on_duplicate
- overwrite
- rename
- source_file_id
- root

### https://canvas.instructure.com/doc/api/file.file_uploads.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/files
- POST /api/v1/users/self/files
- POST /api/v1/accounts/:account_id/sis_imports
- POST /api/v1/courses/:course_id/content_migrations
- POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions/comments/self/files
params:
- name
- size
- content_type
- parent_folder_id
- parent_folder_path
- folder
- on_duplicate
- success_include[]
- url
- submit_assignment
- upload_url
- upload_params
- key
- file
- progress
- workflow_state
- running
- id
- target_url
- content-type
- display_name
- pre_attachment

### https://canvas.instructure.com/doc/api/submission_comments.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id/comments/files

### https://canvas.instructure.com/doc/api/quiz_submission_files.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/quizzes/:quiz_id/submissions/self/files
params:
- name
- on_duplicate
- attachments
- upload_url
- upload_params

### https://canvas.instructure.com/doc/api/content_exports.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/content_exports
- GET /api/v1/groups/:group_id/content_exports
- GET /api/v1/users/:user_id/content_exports
- GET /api/v1/courses/:course_id/content_exports/:id
- POST /api/v1/courses/:course_id/content_exports
- POST /api/v1/groups/:group_id/content_exports
- POST /api/v1/users/:user_id/content_exports
params:
- export_type
- common_cartridge
- qti
- zip
- skip_notifications
- select
- folders
- files
- attachments
- quizzes
- assignments
- announcements
- calendar_events
- discussion_topics
- modules
- module_items
- pages
- rubrics
- id
- created_at
- attachment
- progress_url
- user_id
- workflow_state
- created
- exporting
- exported
- failed

## references/course-content.md

### https://canvas.instructure.com/doc/api/announcements.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/announcements
params:
- context_codes[]
- include
- sections
- sections_user_count
- start_date
- end_date
- available_after

### https://canvas.instructure.com/doc/api/discussion_topics.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/discussion_topics
- PUT /api/v1/courses/:course_id/discussion_topics/:topic_id
- GET /api/v1/courses/:course_id/discussion_topics
params:
- title
- message
- is_announcement
- published
- specific_sections
- lock_comment
- podcast_enabled
- podcast_has_student_posts
- only_announcements
- delayed_post_at
- lock_at

### https://canvas.instructure.com/doc/api/modules.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/modules
- GET /api/v1/courses/:course_id/modules/:id
- POST /api/v1/courses/:course_id/modules
- PUT /api/v1/courses/:course_id/modules/:id
- DELETE /api/v1/courses/:course_id/modules/:id
- PUT /api/v1/courses/:course_id/modules/:id/relock
- GET /api/v1/courses/:course_id/modules/:module_id/items
- GET /api/v1/courses/:course_id/modules/:module_id/items/:id
- POST /api/v1/courses/:course_id/modules/:module_id/items
- PUT /api/v1/courses/:course_id/modules/:module_id/items/:id
- DELETE /api/v1/courses/:course_id/modules/:module_id/items/:id
- PUT /api/v1/courses/:course_id/modules/:module_id/items/:id/done
- POST /api/v1/courses/:course_id/modules/:module_id/items/:id/mark_read
params:
- module[name]
- module[unlock_at]
- module[position]
- module[require_sequential_progress]
- module[prerequisite_module_ids][]
- module[publish_final_grade]
- module[published]
- module_item[title]
- module_item[type]
- File
- Page
- Discussion
- Assignment
- Quiz
- SubHeader
- ExternalUrl
- ExternalTool
- module_item[content_id]
- module_item[position]
- module_item[indent]
- module_item[page_url]
- module_item[external_url]
- module_item[new_tab]
- module_item[iframe][width]
- module_item[iframe][height]
- module_item[module_id]
- module_item[completion_requirement][type]
- must_view
- must_contribute
- must_submit
- must_mark_done
- min_score
- min_percentage
- AiExperience
- module_item[completion_requirement][min_score]
- module_item[published]

### https://canvas.instructure.com/doc/api/pages.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/pages
- GET /api/v1/courses/:course_id/pages
- GET /api/v1/courses/:course_id/pages/:url_or_id
- PUT /api/v1/courses/:course_id/pages/:url_or_id
- GET /api/v1/courses/:course_id/pages/:url_or_id/revisions
- GET /api/v1/courses/:course_id/pages/:url_or_id/revisions/latest
- GET /api/v1/courses/:course_id/pages/:url_or_id/revisions/:revision_id
- POST /api/v1/courses/:course_id/pages/:url_or_id/revisions/:revision_id
- GET /api/v1/courses/:course_id/front_page
- PUT /api/v1/courses/:course_id/front_page
params:
- wiki_page[title]
- wiki_page[body]
- wiki_page[editing_roles]
- teachers
- students
- members
- public
- wiki_page[notify_of_update]
- wiki_page[published]
- wiki_page[front_page]
- wiki_page[publish_at]
- sort
- order
- search_term
- published
- revision_id
- summary
- hide_from_students

### https://canvas.instructure.com/doc/api/courses.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/accounts/:account_id/courses
- PUT /api/v1/courses/:id
params:
- course[default_view]
- feed
- wiki
- modules
- syllabus
- assignments

### https://canvas.instructure.com/doc/api/tabs.html
fetched: 2026-09-10
endpoints:
- GET /api/v1/courses/:course_id/tabs
- PUT /api/v1/courses/:course_id/tabs/:tab_id
params:
- include[]
- course_subject_tabs
- position
- hidden
- visibility
- public
- members
- admins
- none
- type
- internal
- external
