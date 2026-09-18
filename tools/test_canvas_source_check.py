"""Offline tests for the Canvas source drift check.

The fetcher is injected everywhere, so this suite makes no network call.
"""
import unittest

import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "canvas_source_check", pathlib.Path(__file__).with_name("canvas-source-check.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


RUBY = """
class RubricAssessment < ActiveRecord::Base
  RETENTION = 180

  def update_artifact
    return if artifact.blank?
  end

  def assessment_count
    3
  end
end
"""

SUBMISSION = """
  def hide_grade_from_student?(for_plagiarism: false)
    return false if for_plagiarism
  end
"""


def fetcher(pages, seen=None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        for tail, body in pages.items():
            if url.endswith(tail):
                if isinstance(body, Exception):
                    raise body
                return body
        raise LookupError("404 %s" % url)
    return fetch


class TestParsing(unittest.TestCase):
    def test_a_citation_with_a_symbol_is_split(self):
        found = check.parse_citations(
            "as in (source: `app/models/rubric_assessment.rb#update_artifact`, lines 209-230).",
            "ref.md")
        self.assertEqual(found, [{"origin": "ref.md",
                                  "path": "app/models/rubric_assessment.rb",
                                  "symbol": "update_artifact"}])

    def test_a_citation_without_a_symbol_keeps_none(self):
        found = check.parse_citations("(source: `lib/api/v1/assignment.rb`, line 344)", "ref.md")
        self.assertEqual(found[0]["symbol"], None)

    def test_text_with_no_citation_yields_nothing(self):
        self.assertEqual(check.parse_citations("no citations here `code` at all", "ref.md"), [])


class TestAnchoring(unittest.TestCase):
    def test_a_method_definition_anchors(self):
        self.assertEqual(check.anchored("update_artifact", RUBY), "def")

    def test_a_constant_anchors(self):
        self.assertEqual(check.anchored("RETENTION", RUBY), "const")

    def test_a_class_anchors(self):
        self.assertEqual(check.anchored("RubricAssessment", RUBY), "class")

    def test_a_predicate_ending_in_a_question_mark_anchors(self):
        """\\b would never match `def hide_grade_from_student?(`, because ? is not a word char."""
        self.assertEqual(check.anchored("hide_grade_from_student?", SUBMISSION), "def")

    def test_a_prefix_does_not_match_a_longer_name(self):
        """`assess` must not be satisfied by `def assessment_count`."""
        self.assertIsNone(check.anchored("assess", RUBY))

    def test_a_symbol_present_only_as_prose_is_weak(self):
        self.assertEqual(check.anchored("update_artifact", "# update_artifact is called later"),
                         "text")

    def test_an_absent_symbol_does_not_anchor(self):
        self.assertIsNone(check.anchored("no_such_method", RUBY))


class TestReport(unittest.TestCase):
    def cite(self, path, symbol, origin="ref.md"):
        return {"origin": origin, "path": path, "symbol": symbol}

    def test_a_resolved_anchor_reports_nothing_and_exits_zero(self):
        text, code = check.report([self.cite("a/rubric_assessment.rb", "update_artifact")],
                                  fetcher({"rubric_assessment.rb": RUBY}))
        self.assertEqual(code, 0)
        self.assertIn("every anchor still resolves", text)

    def test_a_missing_anchor_is_named_and_exits_one(self):
        text, code = check.report([self.cite("a/rubric_assessment.rb", "gone_method")],
                                  fetcher({"rubric_assessment.rb": RUBY}))
        self.assertEqual(code, 1)
        self.assertIn("MISSING", text)
        self.assertIn("gone_method", text)

    def test_an_unreadable_file_is_an_error_not_a_crash(self):
        text, code = check.report([self.cite("a/moved.rb", "whatever")], fetcher({}))
        self.assertEqual(code, 1)
        self.assertIn("ERROR", text)

    def test_a_weak_anchor_is_reported_without_failing(self):
        text, code = check.report([self.cite("a/notes.rb", "update_artifact")],
                                  fetcher({"notes.rb": "# update_artifact happens here"}))
        self.assertEqual(code, 0)
        self.assertIn("WEAK", text)
        self.assertIn("need a person", text)

    def test_a_citation_without_a_symbol_only_requires_the_file(self):
        text, code = check.report([self.cite("a/rubric_assessment.rb", None)],
                                  fetcher({"rubric_assessment.rb": RUBY}))
        self.assertEqual(code, 0)
        self.assertIn("1 citations across 1 files", text)

    def test_a_missing_file_still_fails_a_symbolless_citation(self):
        _, code = check.report([self.cite("a/moved.rb", None)], fetcher({}))
        self.assertEqual(code, 1)

    def test_each_path_is_fetched_once_however_often_it_is_cited(self):
        seen = []
        cites = [self.cite("a/rubric_assessment.rb", "update_artifact"),
                 self.cite("a/rubric_assessment.rb", "RETENTION"),
                 self.cite("a/rubric_assessment.rb", "RubricAssessment")]
        _, code = check.report(cites, fetcher({"rubric_assessment.rb": RUBY}, seen))
        self.assertEqual(code, 0)
        self.assertEqual(len(seen), 1, seen)

    def test_the_ref_is_used_in_the_url(self):
        seen = []
        check.report([self.cite("a/rubric_assessment.rb", "update_artifact")],
                     fetcher({"rubric_assessment.rb": RUBY}, seen), ref="release/2026-09-10")
        self.assertIn("/release/2026-09-10/a/rubric_assessment.rb", seen[0])


if __name__ == "__main__":
    unittest.main()
