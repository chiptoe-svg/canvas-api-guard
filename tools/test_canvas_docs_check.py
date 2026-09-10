"""Offline tests for the Canvas documentation drift check.

The fetcher is injected everywhere, so this suite makes no network call.
"""
import unittest

import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "canvas_docs_check", pathlib.Path(__file__).with_name("canvas-docs-check.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


SOURCES = """# Sources

## references/quizzes.md

### https://example.invalid/doc/api/quizzes.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/quizzes
- GET /api/v1/courses/:course_id/quizzes/:id
params:
- quiz[title]
- quiz[published]

## references/rubrics-and-grades.md

### https://example.invalid/doc/api/rubrics.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/rubrics
params:
- rubric[title]
"""


class ParseSources(unittest.TestCase):
    def test_it_reads_every_block_with_its_reference_file(self):
        records = check.parse_sources(SOURCES)
        self.assertEqual([r["file"] for r in records],
                         ["references/quizzes.md", "references/rubrics-and-grades.md"])
        self.assertEqual(records[0]["url"], "https://example.invalid/doc/api/quizzes.html")
        self.assertEqual(records[0]["fetched"], "2026-09-10")

    def test_it_keeps_endpoints_and_params_apart(self):
        first = check.parse_sources(SOURCES)[0]
        self.assertEqual(first["endpoints"],
                         ["POST /api/v1/courses/:course_id/quizzes",
                          "GET /api/v1/courses/:course_id/quizzes/:id"])
        self.assertEqual(first["params"], ["quiz[title]", "quiz[published]"])

    def test_a_block_with_no_claims_parses_as_empty_not_as_an_error(self):
        records = check.parse_sources(
            "## references/x.md\n\n### https://example.invalid/a.html\nfetched: 2026-09-10\n")
        self.assertEqual(records[0]["endpoints"], [])
        self.assertEqual(records[0]["params"], [])


class Missing(unittest.TestCase):
    def setUp(self):
        self.record = check.parse_sources(SOURCES)[0]

    def test_nothing_is_missing_when_the_page_still_has_it_all(self):
        page = ("POST /api/v1/courses/:course_id/quizzes and "
                "GET /api/v1/courses/:course_id/quizzes/:id take quiz[title] and quiz[published]")
        self.assertEqual(check.missing(self.record, page), [])

    def test_a_dropped_parameter_is_reported(self):
        page = ("POST /api/v1/courses/:course_id/quizzes and "
                "GET /api/v1/courses/:course_id/quizzes/:id take quiz[title]")
        self.assertEqual(check.missing(self.record, page), [("param", "quiz[published]")])

    def test_a_dropped_endpoint_is_reported(self):
        """This is also the guard against path-prefix collision, and it is the reason
        `missing` cannot use a plain substring test. `/quizzes` is a substring of
        `/quizzes/:id`, so a substring test reports the collection endpoint as present
        forever after it is removed - the exact drift this tool exists to catch. If you
        simplify `_appears` back to `in`, this test goes red. Verified 2026-09-10."""
        page = "GET /api/v1/courses/:course_id/quizzes/:id takes quiz[title] and quiz[published]"
        self.assertEqual(check.missing(self.record, page),
                         [("endpoint", "POST /api/v1/courses/:course_id/quizzes")])

    def test_the_verb_is_not_required_to_sit_beside_the_path(self):
        """Rendered pages put the verb in a table cell away from the path, so only the
        path is matched. A page that lists the path under a heading still passes."""
        page = ("### Create a quiz\n`/api/v1/courses/:course_id/quizzes`\n"
                "`/api/v1/courses/:course_id/quizzes/:id`\nquiz[title] quiz[published]")
        self.assertEqual(check.missing(self.record, page), [])

    def test_a_parameter_is_not_matched_inside_a_longer_name(self):
        """A short unbracketed parameter like per_page is a substring of per_page_max, and
        `id` is a substring of `identifier`. Without a boundary check a removed parameter
        reads as present forever - the same false negative `_appears` prevents for paths."""
        record = check.parse_sources(
            "## references/x.md\n\n### https://example.invalid/a.html\nfetched: 2026-09-10\n"
            "params:\n- per_page\n- id\n")[0]
        self.assertEqual(check.missing(record, "per_page_max is documented, the identifier went"),
                         [("param", "per_page"), ("param", "id")])


class Report(unittest.TestCase):
    def test_a_clean_run_says_so_and_exits_zero(self):
        def fetch(url):
            return ("POST /api/v1/courses/:course_id/quizzes "
                    "GET /api/v1/courses/:course_id/quizzes/:id quiz[title] quiz[published] "
                    "POST /api/v1/courses/:course_id/rubrics rubric[title]")
        text, code = check.report(check.parse_sources(SOURCES), fetch)
        self.assertEqual(code, 0)
        self.assertIn("2 pages checked", text)
        self.assertIn("nothing missing", text)

    def test_a_miss_is_named_with_its_reference_file_and_exits_one(self):
        def fetch(url):
            if "rubrics" in url:
                return "POST /api/v1/courses/:course_id/rubrics rubric[title]"
            return "GET /api/v1/courses/:course_id/quizzes/:id quiz[title]"
        text, code = check.report(check.parse_sources(SOURCES), fetch)
        self.assertEqual(code, 1)
        self.assertIn("references/quizzes.md", text)
        self.assertIn("MISSING endpoint  POST /api/v1/courses/:course_id/quizzes", text)
        self.assertIn("MISSING param     quiz[published]", text)
        self.assertNotIn("references/rubrics-and-grades.md", text)

    def test_a_fetch_failure_is_an_error_not_a_crash_and_exits_one(self):
        def fetch(url):
            raise OSError("connection refused")
        text, code = check.report(check.parse_sources(SOURCES), fetch)
        self.assertEqual(code, 1)
        self.assertIn("ERROR", text)
        self.assertIn("connection refused", text)


if __name__ == "__main__":
    unittest.main()
