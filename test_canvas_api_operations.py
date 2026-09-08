#!/usr/bin/env python3
"""Offline behavior tests for the optional Level 2 analysis program."""

import importlib.util
import io
import json
import os
import unittest
from unittest import mock

from test_canvas_api_guard import HOST, FakeResponse, GuardTestCase


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

    def test_ids_are_numeric_and_positive(self):
        for invalid in ("0", "-1", "course-12"):
            with self.assertRaises(operations.OperationError):
                operations.canvas_id(invalid, "course ID")

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
        download.assert_called_once_with("12", 7, "99", ".pdf")
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
        self.assertEqual(download.call_args_list[0][0], ("12", 1, "99", ".jpg"))
        self.assertEqual(download.call_args_list[1][0], ("12", 2, "99", ".docx"))
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
        self.assertEqual([call[0] for call in download.call_args_list], [("12", 1, "99", ".pdf"), ("12", 2, "99", ".png")])
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
        self.assertEqual([call[0] for call in download.call_args_list], [("12", 1, "90", ".docx"), ("12", 2, "90", ".jpg")])
        self.assertEqual(result["downloaded_file_count"], 2)
        self.assertEqual(result["no_attachment_submission_count"], 1)
        self.assertNotIn("do not return this", str(result))

    def test_level2_write_delegates_to_the_fixed_guard_with_a_phase(self):
        completed = mock.Mock()
        completed.return_value = mock.Mock(returncode=0,
                                           stdout='{"verification": "not-run"}\n', stderr="")
        with mock.patch.object(operations.subprocess, "run", completed), \
                mock.patch("sys.stdout", io.StringIO()):
            operations.guard_write("post", "courses/12/assignments", {"assignment": {"name": "Lab"}},
                                   "dry-run")
        command = completed.call_args[0][0]
        self.assertEqual(command[:3], [operations.GUARD, "post", "courses/12/assignments"])
        self.assertIn("--dry-run", command)
        self.assertNotIn("--yes", command)

    def test_only_the_seven_computing_operations_remain(self):
        self.assertEqual(sorted(operations.OPERATIONS), [
            "attach-rubric", "bulk-grade-with-rubric", "create-rubric",
            "download-assignment-submissions", "grade-with-rubric",
            "prepare-submission-review", "student-attention"])
        with open(SOURCE) as handle:
            source = handle.read()
        for gone in ("def current_courses", "def roster_count", "def find_student",
                     "def needs_grading", "def course_health", "def assignment_performance",
                     "def student_trajectory", "def set_assignment_dates",
                     "def excuse_submission", "def create_assignment",
                     "def create_or_update_page", "def create_announcement",
                     "def quote_query", "def compact_course", "def assignment_rows",
                     "def iso_time", "def page_body", "def announcement_body"):
            self.assertNotIn(gone, source, "%s should have moved to Level 1" % gone)

    def test_a_missing_guard_prints_one_line_and_never_a_traceback(self):
        with mock.patch.object(operations.subprocess, "run",
                               side_effect=FileNotFoundError(2, "No such file or directory")), \
                mock.patch("sys.stderr", io.StringIO()) as err:
            code = operations.main(["student-attention", "--course-id", "12"])
        self.assertEqual(code, 2)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertIn("canvas-api-operations: cannot run", err.getvalue())

    def test_an_uncertain_guard_write_is_raised_not_retried(self):
        refused = mock.Mock(returncode=3, stdout='{"verification": "failed"}\n',
                            stderr="canvas-api-guard: WRITE STATUS UNCERTAIN: read-back failed")
        with mock.patch.object(operations.subprocess, "run",
                               return_value=refused) as run, \
                mock.patch("sys.stdout", io.StringIO()) as out:
            with self.assertRaises(operations.GuardUncertain):
                operations.guard_write("put", "courses/12/assignments/22/submissions/34",
                                       {"submission": {"posted_grade": 9}}, "yes")
        self.assertEqual(run.call_count, 1)
        self.assertIn("verification", out.getvalue())     # the evidence is still shown

    def test_main_maps_an_uncertain_write_to_exit_3(self):
        def uncertain(args):
            raise operations.GuardUncertain("the write was sent and could not be verified")

        with mock.patch.dict(operations.OPERATIONS, {"student-attention": uncertain}), \
                mock.patch("sys.stderr", io.StringIO()) as err:
            code = operations.main(["student-attention", "--course-id", "12"])
        self.assertEqual(code, 3)
        self.assertIn("could not be verified", err.getvalue())

    def test_an_operation_that_prints_its_own_evidence_adds_no_trailing_null(self):
        def prints(args):
            print('{"result": "printed once"}')

        with mock.patch.dict(operations.OPERATIONS, {"student-attention": prints}), \
                mock.patch("sys.stdout", io.StringIO()) as out:
            code = operations.main(["student-attention", "--course-id", "12"])
        self.assertEqual(code, 0)
        self.assertNotIn("null", out.getvalue())


class TestGuardWriteContract(GuardTestCase):
    """The one contract between the layers: what the real guard prints for a `-o json` write
    is exactly what guard_write parses. Mocked stdout shapes cannot prove this."""

    def test_guard_write_parses_the_real_guards_json_write_output(self):
        path = "courses/12/assignments/22/submissions/34"
        body = {"submission": {"posted_grade": 95}}
        graded = {"id": 34, "user_id": 34, "grade": "95", "entered_grade": "95",
                  "score": 95.0, "entered_score": 95.0}
        responses = [FakeResponse(payload=dict(graded, grade="60", entered_grade="60",
                                               score=60.0, entered_score=60.0)),
                     FakeResponse(payload=graded), FakeResponse(payload=graded)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, captured = self.run_main([
                "put", path, "--yes", "-o", "json", "--verify-fields", "posted_grade",
                "-d", json.dumps(body)])
        self.assertEqual(code, 0)
        completed = mock.Mock(returncode=0, stdout=captured, stderr="")
        with mock.patch.object(operations.subprocess, "run", return_value=completed), \
                mock.patch("sys.stdout", io.StringIO()):
            evidence = operations.guard_write("put", path, body, "yes",
                                              ["--verify-fields", "posted_grade"])
        self.assertEqual(evidence["verification"], "passed")
        self.assertEqual(evidence["url"], "https://" + HOST + "/api/v1/" + path)
