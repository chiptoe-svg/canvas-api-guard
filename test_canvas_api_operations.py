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

    def test_student_attention_orders_transparent_signals_without_names(self):
        pages = {
            "courses/12/analytics/student_summaries?per_page=100": {
                "items": [
                    {"id": 1, "page_views": 20, "participations": 4,
                     "tardiness_breakdown": {"missing": 0, "late": 3, "on_time": 5, "total": 8}},
                    {"id": 2, "page_views": 2, "participations": 0,
                     "tardiness_breakdown": {"missing": 2, "late": 0, "on_time": 1, "total": 3}},
                ], "next": None,
            }
        }
        with mock.patch.object(operations, "guard_get", side_effect=lambda path: pages[path]):
            report = operations.student_attention(Args())
        self.assertEqual([student["student_id"] for student in report["students"]], [2, 1])
        self.assertNotIn("name", report["students"][0])
        self.assertIn("not a risk score", report["definition"])

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
