#!/usr/bin/env python3
"""Offline behavior tests for the optional Level 2 analysis program."""

import importlib.util
import os
import unittest
from unittest import mock


SOURCE = os.path.join(os.path.dirname(__file__), "level2", "canvas_api_operations.py")
SPEC = importlib.util.spec_from_file_location("canvas_api_operations", SOURCE)
operations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operations)


class Args(object):
    course_id = "12"
    student_id = "34"
    limit = 20


class TestLevel2Operations(unittest.TestCase):
    def test_level2_has_no_credential_or_http_client_code(self):
        with open(SOURCE) as handle:
            source = handle.read()
        self.assertIn('GUARD = "/usr/local/libexec/canvas_api_guard.py"', source)
        self.assertNotIn("read_token", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("http.client", source)

    def test_student_attention_orders_signals_and_fetches_only_flagged_names(self):
        summaries = [
            {"id": 1, "page_views": 20, "participations": 4,
             "tardiness_breakdown": {"missing": 0, "late": 3, "on_time": 5, "total": 8}},
            {"id": 2, "page_views": 2, "participations": 0,
             "tardiness_breakdown": {"missing": 2, "late": 0, "on_time": 1, "total": 3}},
        ]
        identities = [{"id": 1, "name": "Jordan Lee", "sortable_name": "Lee, Jordan"},
                      {"id": 2, "name": "Casey Kim", "sortable_name": "Kim, Casey"}]
        def read(path):
            return summaries if "student_summaries" in path else identities
        with mock.patch.object(operations, "all_items", side_effect=read) as get:
            report = operations.student_attention(Args())
        self.assertEqual([student["student_id"] for student in report["students"]], [2, 1])
        self.assertEqual(report["students"][0]["name"], "Casey Kim")
        self.assertIn("user_ids[]=2", get.call_args_list[1][0][0])
        self.assertNotIn("courses/12/users?per_page=100", get.call_args_list[1][0][0])
        self.assertIn("not a risk score", report["definition"])

    def test_current_courses_uses_the_server_side_teacher_and_term_filters(self):
        with mock.patch.object(operations, "all_items", return_value=[
                {"id": 12, "course_code": "GC1010", "name": "Orientation",
                 "term": {"id": 8, "name": "Fall", "start_at": "2026-08-01", "end_at": "2026-12-01"}},
        ]) as read:
            report = operations.current_courses(Args())
        self.assertEqual(report["courses"][0]["course_code"], "GC1010")
        self.assertIn("enrollment_type=teacher", read.call_args[0][0])
        self.assertIn("include[]=term", read.call_args[0][0])

    def test_roster_count_deduplicates_users_in_multiple_sections(self):
        with mock.patch.object(operations, "all_items", return_value=[{"id": 1}, {"id": 1}, {"id": 2}]):
            report = operations.roster_count(Args())
        self.assertEqual(report["active_student_count"], 2)

    def test_find_student_escapes_query_and_returns_only_matching_identity_fields(self):
        with mock.patch.object(operations, "all_items", return_value=[
                {"id": 2, "name": "Jordan Lee", "sortable_name": "Lee, Jordan", "sis_user_id": "C123"},
        ]) as read:
            args = Args()
            args.query = "Jordan & Lee"
            report = operations.find_student(args)
        self.assertIn("Jordan%20%26%20Lee", read.call_args[0][0])
        self.assertEqual(report["matches"][0]["student_id"], 2)

    def test_needs_grading_returns_compact_assignment_queue(self):
        with mock.patch.object(operations, "all_items", return_value=[
                {"id": 1, "name": "Done", "needs_grading_count": 0},
                {"id": 2, "name": "Lab", "due_at": "2026-09-01", "needs_grading_count": 3},
        ]):
            report = operations.needs_grading(Args())
        self.assertEqual(report["total_needing_grading"], 3)
        self.assertEqual(report["assignments"], [{"assignment_id": 2, "title": "Lab",
                                                    "due_at": "2026-09-01", "needs_grading_count": 3}])

    def test_assignment_performance_uses_missing_then_late_rates(self):
        with mock.patch.object(operations, "all_items", return_value=[
                {"assignment_id": 3, "title": "Later", "tardiness_breakdown": {"missing": .1, "late": .8}},
                {"assignment_id": 2, "title": "Missing", "tardiness_breakdown": {"missing": .3, "late": .1}},
        ]):
            report = operations.assignment_performance(Args())
        self.assertEqual([row["assignment_id"] for row in report["assignments"]], [2, 3])

    def test_ids_are_numeric_and_positive(self):
        for invalid in ("0", "-1", "course-12"):
            with self.assertRaises(operations.OperationError):
                operations.canvas_id(invalid, "course ID")

    def test_specialized_assignment_definition_has_an_allowlist(self):
        body = operations.assignment_body({"name": "Lab", "points_possible": 20,
                                            "published": False}, True)
        self.assertEqual(body["assignment"]["name"], "Lab")
        with self.assertRaises(operations.OperationError):
            operations.assignment_body({"name": "Lab", "admin_only": True}, True)

    def test_rubric_definition_is_converted_to_the_canvas_indexed_shape(self):
        body = operations.rubric_body({"title": "Lab rubric", "criteria": [{
            "description": "Craft", "points": 10,
            "ratings": [{"description": "Complete", "points": 10},
                        {"description": "Incomplete", "points": 0}]}]})
        self.assertEqual(body["rubric"]["criteria"]["0"]["description"], "Craft")
        self.assertEqual(body["rubric_association"]["purpose"], "bookmark")

    def test_rubric_grade_uses_only_live_criterion_ids(self):
        rubric = {"data": [{"id": "criterion_1", "points": 10}]}
        student, criteria, total = operations.grade_payload(
            {"student_id": 4, "criteria": {"criterion_1": {"points": 8}}}, rubric)
        self.assertEqual((student, total), ("4", 8))
        self.assertEqual(criteria["criterion_1"]["points"], 8)
        with self.assertRaises(operations.OperationError):
            operations.grade_payload({"student_id": 4,
                                      "criteria": {"criterion_404": {"points": 8}}}, rubric)

    def test_live_rubric_requires_the_assignment_association_to_grade(self):
        args = Args()
        args.assignment_id = "22"
        assignment = {"rubric_settings": {"id": 9, "rubric_association_id": 10}}
        rubric = {"data": [{"id": "criterion_1", "points": 10}],
                  "associations": [{"id": 10, "use_for_grading": True}]}
        with mock.patch.object(operations, "guard_get",
                               side_effect=[{"object": assignment}, {"object": rubric}]):
            _, resolved, association = operations.live_rubric(args)
        self.assertEqual(resolved["data"][0]["id"], "criterion_1")
        self.assertEqual(association, "10")

    def test_prepare_submission_review_accepts_one_pdf_and_does_not_grade(self):
        args = Args()
        args.assignment_id = "22"
        assignment = {"id": 22, "name": "Week 2 Notes"}
        submission = {"id": 99, "user_id": 34, "user": {"name": "Jordan Lee"},
                      "attachments": [{"id": 7, "display_name": "notes.pdf",
                                       "content-type": "application/pdf"}]}
        evidence = {"path": "/private/review.pdf", "sha256": "a" * 64, "bytes": 12}
        with mock.patch.object(operations, "guard_get", side_effect=[{"object": assignment}, {"object": submission}]), \
                mock.patch.object(operations, "guard_download_attachment", return_value=evidence) as download:
            result = operations.prepare_submission_review(args)
        download.assert_called_once_with(7, "99", ".pdf")
        self.assertEqual(result["student"]["name"], "Jordan Lee")
        self.assertIn("no grade has been written", result["next_step"])

    def test_prepare_submission_review_accepts_multiple_document_types_but_refuses_empty(self):
        args = Args()
        args.assignment_id = "22"
        empty = {"id": 99, "user_id": 34, "attachments": []}
        with mock.patch.object(operations, "guard_get", side_effect=[{"object": {}}, {"object": empty}]), \
                mock.patch.object(operations, "guard_download_attachment") as download:
            with self.assertRaises(operations.OperationError):
                operations.prepare_submission_review(args)
        download.assert_not_called()
        attachments = [{"id": 1, "display_name": "page.jpg", "content-type": "image/jpeg"},
                       {"id": 2, "display_name": "notes.docx", "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}]
        submission = {"id": 99, "user_id": 34, "attachments": attachments}
        with mock.patch.object(operations, "guard_get", side_effect=[{"object": {}}, {"object": submission}]), \
                mock.patch.object(operations, "guard_download_attachment", return_value={"path": "/private/file"}) as download:
            result = operations.prepare_submission_review(args)
        self.assertEqual(download.call_args_list[0][0], (1, "99", ".jpg"))
        self.assertEqual(download.call_args_list[1][0], (2, "99", ".docx"))
        self.assertEqual(len(result["attachments"]), 2)

    def test_submission_review_keeps_earlier_attempt_files_once(self):
        args = Args()
        args.assignment_id = "22"
        submission = {"id": 99, "user_id": 34, "user": {"name": "Jordan Lee"}, "attempt": 2,
                      "attachments": [{"id": 2, "display_name": "revision.png"}],
                      "submission_history": [
                          {"attempt": 1, "attachments": [{"id": 1, "display_name": "notes.pdf"}]},
                          {"attempt": 2, "attachments": [{"id": 2, "display_name": "revision.png"}]}]}
        with mock.patch.object(operations, "guard_get", side_effect=[{"object": {"id": 22}}, {"object": submission}]), \
                mock.patch.object(operations, "guard_download_attachment", return_value={"path": "/private/file"}) as download:
            result = operations.prepare_submission_review(args)
        self.assertEqual([call[0] for call in download.call_args_list], [(1, "99", ".pdf"), (2, "99", ".png")])
        self.assertEqual([row["attempt"] for row in result["attachments"]], [1, 2])

    def test_batch_download_collects_all_students_and_attempts_without_submission_text(self):
        args = Args()
        args.assignment_id = "22"
        submissions = [
            {"id": 90, "user_id": 30, "attempt": 2,
             "attachments": [{"id": 2, "display_name": "photo.jpg"}],
             "submission_history": [{"attempt": 1, "attachments": [{"id": 1, "display_name": "draft.docx"}]}]},
            {"id": 91, "user_id": 31, "workflow_state": "unsubmitted", "body": "do not return this", "attachments": []},
        ]
        with mock.patch.object(operations, "guard_get", return_value={"object": {"id": 22, "name": "Week 2"}}), \
                mock.patch.object(operations, "all_items", return_value=submissions) as listed, \
                mock.patch.object(operations, "guard_download_attachment", return_value={"path": "/private/file"}) as download:
            result = operations.download_assignment_submissions(args)
        self.assertIn("include[]=submission_history", listed.call_args[0][0])
        self.assertEqual([call[0] for call in download.call_args_list], [(1, "90", ".docx"), (2, "90", ".jpg")])
        self.assertEqual(result["downloaded_file_count"], 2)
        self.assertEqual(result["no_attachment_submission_count"], 1)
        self.assertNotIn("do not return this", str(result))

    def test_date_helper_rejects_invalid_or_new_quiz_dates_before_a_write(self):
        args = Args()
        args.assignment_id = "22"
        args.definition = "unused"
        args.dry_run = True
        args.yes = False
        definition = {"available_at": "2026-09-10T10:00:00-04:00",
                      "due_at": "2026-09-09T10:00:00-04:00"}
        with mock.patch.object(operations, "definition_file", return_value=definition), \
                mock.patch.object(operations, "guard_get", return_value={"object": {}}), \
                mock.patch.object(operations, "guard_write") as write:
            with self.assertRaises(operations.OperationError):
                operations.set_assignment_dates(args)
        write.assert_not_called()
        with mock.patch.object(operations, "definition_file", return_value={"due_at": "2026-09-09T10:00:00-04:00"}), \
                mock.patch.object(operations, "guard_get", return_value={"object": {"is_quiz_assignment": True}}), \
                mock.patch.object(operations, "guard_write") as write:
            with self.assertRaises(operations.OperationError):
                operations.set_assignment_dates(args)
        write.assert_not_called()

    def test_excuse_uses_canvas_excuse_request_and_named_submission(self):
        args = Args()
        args.assignment_id = "22"
        args.definition = "unused"
        args.dry_run = True
        args.yes = False
        responses = [{"object": {"id": 22, "name": "Roll Call Attendance"}},
                     {"object": {"user_id": 34, "excused": False,
                                  "user": {"name": "Jordan Lee"}}},
                     {"object": {"id": 12}}]
        with mock.patch.object(operations, "definition_file", return_value={"student_id": 34}), \
                mock.patch.object(operations, "guard_get", side_effect=responses), \
                mock.patch.object(operations, "guard_write") as write:
            operations.excuse_attendance(args)
        self.assertEqual(write.call_args[0][0:3], ("put", "courses/12/assignments/22/submissions/34?include[]=user",
                                                     {"submission": {"excuse": True}}))

    def test_level2_write_delegates_to_the_fixed_guard_with_a_phase(self):
        completed = mock.Mock()
        completed.return_value = mock.Mock(returncode=0,
                                           stdout='{"verification": "not-run"}\n', stderr="")
        with mock.patch.object(operations.subprocess, "run", completed):
            operations.guard_write("post", "courses/12/assignments", {"assignment": {"name": "Lab"}},
                                   "dry-run")
        command = completed.call_args[0][0]
        self.assertEqual(command[:3], [operations.GUARD, "post", "courses/12/assignments"])
        self.assertIn("--dry-run", command)
        self.assertNotIn("--yes", command)
