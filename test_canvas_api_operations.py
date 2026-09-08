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
