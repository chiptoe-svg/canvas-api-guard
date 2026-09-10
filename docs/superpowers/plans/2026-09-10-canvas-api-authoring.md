# Canvas API Authoring Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a build-side skill that is this repo's source of truth for how Canvas works for instructor tasks, with the passthrough vs plan vs function vs guard-verb decision in front of it.

**Architecture:** A short `SKILL.md` routes from instructor intent to one of seven references. Six references are pure Canvas knowledge organised by task arc, written from the official documentation with parameters copied verbatim. The seventh is the design decision procedure. A `sources.md` records every documentation URL with the endpoints and parameters taken from it, and a hand-run checker re-fetches those pages and reports drift.

**Tech Stack:** Markdown; Python 3 standard library only (`urllib.request`, `re`, `unittest`) for the checker.

**Spec:** `docs/superpowers/specs/2026-09-10-canvas-api-authoring-design.md`

## Global Constraints

- Everything lands under `.claude/skills/canvas-api-authoring/` except the checker, which is `tools/canvas-docs-check.py`.
- **Do not modify** `canvas_api_guard.py`, `level2/canvas_api_operations.py`, `install.sh`, `install-from-github.sh`, `codex/`, `level2/SKILL.md`, or `README.md`. This work installs nothing and changes no released behaviour.
- **No `/usr/local/libexec/` command line appears in any file in the skill.** Verified by grep in every task. Naming a verb or flag in prose is permitted **only** in `references/passthrough-or-function.md`; the six Canvas references name no local verb or flag at all.
- **Parameters are copied verbatim** from the documentation page, including bracket nesting such as `quiz[title]` and `rubric_association[use_for_grading]`. Never paraphrase, never recall, never invent.
- **Every trap carries its evidence** inline as either `(docs: <url>)` or `(repo: <path>)`. A trap with no evidence does not ship.
- **Nothing is live-tested against Canvas.** There is no token in this environment. Claims are documentation-grounded; claims taken from this repo's tested code are labelled repo-verified.
- Documentation base URL is `https://canvas.instructure.com/doc/api/`. Every page fetched on **2026-09-10**.
- Python must run under `python3` with no third-party imports.
- Prose is plain and declarative, matching the house voice of `codex/skills/canvas-api-guard/SKILL.md`: short sentences, no marketing, no hedging.

### The section template every Canvas reference follows

Each reference is a sequence of sections. Each section is one thing an instructor wants to do, and has exactly these five parts in this order:

```markdown
### <The task in the instructor's own terms>

**What Canvas does.** <How Canvas models this. The concepts, the object
relationships, the lifecycle. Two to six sentences.>

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/quizzes` | Create a quiz |

**Parameters.** <Verbatim names, as a list or table. Note which are
create-only or update-only where the documentation says so.>

**Traps.** <Each one a bullet: what an obvious guess gets wrong, and why,
with evidence. `(docs: <url>)` or `(repo: <path>)`.>

**Source.** <full url>, fetched 2026-09-10
```

### The `sources.md` record format

The checker parses this file, so the format is exact. Blank lines between blocks are ignored.

```markdown
## references/<reference file name>

### https://canvas.instructure.com/doc/api/<page>.html
fetched: 2026-09-10
endpoints:
- POST /api/v1/courses/:course_id/quizzes
- GET /api/v1/courses/:course_id/quizzes/:id
params:
- quiz[title]
- quiz[published]
```

Rules: a `##` line names the reference file the following blocks belong to. A `###` line is a documentation URL. `fetched:` is an ISO date. `endpoints:` and `params:` introduce `- ` lists that run until the next key, heading, or blank-line-then-non-list. An endpoint entry is `VERB path`; the checker matches on the path only, because rendered pages do not reliably keep the verb adjacent to the path.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `.claude/skills/canvas-api-authoring/SKILL.md` | What this is, routing table, live capability lookup |
| `.claude/skills/canvas-api-authoring/sources.md` | Provenance and the machine-checkable claim set |
| `.claude/skills/canvas-api-authoring/references/passthrough-or-function.md` | The four-way design decision |
| `.claude/skills/canvas-api-authoring/references/fundamentals.md` | Cross-cutting Canvas mechanics |
| `.claude/skills/canvas-api-authoring/references/assignments.md` | Assignment arc |
| `.claude/skills/canvas-api-authoring/references/quizzes.md` | Classic quiz arc, New Quizzes stub |
| `.claude/skills/canvas-api-authoring/references/rubrics-and-grades.md` | Rubrics, grading, final grades |
| `.claude/skills/canvas-api-authoring/references/submissions-and-files.md` | Submissions, attachments, upload |
| `.claude/skills/canvas-api-authoring/references/course-content.md` | Announcements, modules, pages, home page |
| `tools/canvas-docs-check.py` | Hand-run drift check over `sources.md` |
| `tools/test_canvas_docs_check.py` | Offline tests for the checker |

Tasks 4 through 9 are independent of one another and may run in parallel. Each appends its own `##` block to `sources.md`, so parallel workers touch different regions of one file; the reviewer resolves any conflict by concatenation, since block order does not matter to the checker.

---

## Task 1: Skill skeleton and SKILL.md

**Files:**
- Create: `.claude/skills/canvas-api-authoring/SKILL.md`
- Create: `.claude/skills/canvas-api-authoring/sources.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the directory layout, the routing table that Tasks 3-9 fill in behind, and the `sources.md` header that every later task appends under.

- [ ] **Step 1: Verify the CodeGraph queries in the capability section actually work**

Before writing them down, run them. Do not write a query into `SKILL.md` that you have not seen return the right thing.

Run the CodeGraph context tool with task `canvas_api_guard CLI verbs, subcommands and flags: what operations the guard exposes`.

Expected: results including `VERBS` at `canvas_api_guard.py:1159` and `OPERATIONS` at `level2/canvas_api_operations.py:838`. If the line numbers have moved, that is fine and expected; record no line numbers in `SKILL.md`.

Run: `python3 canvas_api_guard.py --help` and `python3 level2/canvas_api_operations.py --help`

Expected: both print a subcommand list and exit 0.

- [ ] **Step 2: Write SKILL.md**

Create `.claude/skills/canvas-api-authoring/SKILL.md` with this frontmatter and structure. Fill the prose; the headings and the routing table rows are fixed.

```markdown
---
name: canvas-api-authoring
description: How Canvas works and what its REST API supports for the things an instructor does - quizzes, assignments, rubrics and grades, submissions and files, announcements, modules and pages. Use when writing or changing a Canvas function, a guard verb, or Canvas skill text, and when deciding whether a Canvas task should be a passthrough call, a plan, a named function, or a new guard verb.
---

# Canvas API authoring

## What this is

The build-side source of truth for how Canvas works, taken from the official Canvas REST API
documentation. It exists so that a Canvas function, a guard verb, or a line of skill text is
written from what Canvas documents rather than from a guess, because a guessed parameter name
costs a refused write or an unverifiable one.

It is not a runtime skill. Nothing here is installed, and no instructor ever reads it.

## What this is not

It is not a record of what the local tooling can do. Every capability claim about
`canvas_api_guard.py` or `canvas_api_operations.py` goes stale the moment either changes, so
none is written here. Look it up instead - see below.

Nothing here has been run against a live Canvas instance. Every claim is documentation-grounded.
A claim taken from this repo's own tested code is labelled repo-verified where it appears.

## Look up current capability, never recall it

Two sources, and they answer different questions.

**What exists** is a symbol, and CodeGraph returns it in one call. Ask `codegraph_context` for
`canvas_api_guard CLI verbs, subcommands and flags: what operations the guard exposes`. It
returns the guard's `VERBS` table and Level 2's `OPERATIONS` table together.

**How it behaves** is not a symbol. Whether a write is refused, whether a body may be multipart,
what a read-back can prove - all of that is branching logic. CodeGraph will not tell you. Read
`--help` on the program, then the tests that name the behaviour.

Do not trust either tool past its boundary, and do not answer a capability question from memory.

## Where to look

| If you are | Read |
| --- | --- |
| deciding passthrough, plan, function, or guard verb | `references/passthrough-or-function.md` |
| working out how Canvas models a course at all | `references/fundamentals.md` |
| creating, configuring or publishing an assignment | `references/assignments.md` |
| building, publishing or scoring a quiz | `references/quizzes.md` |
| building a rubric, grading with it, or touching final grades | `references/rubrics-and-grades.md` |
| finding, downloading or uploading student work and files | `references/submissions-and-files.md` |
| posting an announcement, or building modules, pages or a home page | `references/course-content.md` |

Start with `references/passthrough-or-function.md`. The shape of the thing you are building
decides more than any endpoint detail does.

## Provenance

`sources.md` records every documentation page these references draw on, the date it was fetched,
and the endpoints and parameter names taken from it. `tools/canvas-docs-check.py` re-fetches
those pages and reports anything that no longer appears. Run it by hand when you want to know
whether Canvas has moved. It changes nothing.
```

- [ ] **Step 3: Write the sources.md header**

Create `.claude/skills/canvas-api-authoring/sources.md`:

```markdown
# Sources

Every documentation page these references draw on, with the endpoints and parameter names taken
from it. `tools/canvas-docs-check.py` reads this file and reports anything that no longer
appears on its page.

Coverage is exactly what is recorded here. A parameter used in a reference but not recorded here
is not checked, so recording the claim is part of writing the section.

Base URL: `https://canvas.instructure.com/doc/api/`
```

- [ ] **Step 4: Verify the constraint holds**

Run: `grep -rn '/usr/local/libexec/' .claude/skills/canvas-api-authoring/ ; echo "exit $?"`
Expected: no matches, `exit 1` from grep.

Run: `head -4 .claude/skills/canvas-api-authoring/SKILL.md`
Expected: the frontmatter opens with `---` and a `name: canvas-api-authoring` line.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/canvas-api-authoring/SKILL.md .claude/skills/canvas-api-authoring/sources.md
git commit -m "feat(skill): canvas-api-authoring skeleton, routing and provenance"
```

---

## Task 2: The drift checker

**Files:**
- Create: `tools/canvas-docs-check.py`
- Test: `tools/test_canvas_docs_check.py`

**Interfaces:**
- Consumes: the `sources.md` record format from Global Constraints.
- Produces: `parse_sources(text) -> list[dict]` with keys `file`, `url`, `fetched`, `endpoints`, `params`; `missing(record, page) -> list[tuple[str, str]]` of `(kind, claim)`; `report(records, fetch) -> tuple[str, int]` returning the printed text and the exit code. `fetch(url) -> str` is injected so the tests run offline.

- [ ] **Step 1: Write the failing tests**

Create `tools/test_canvas_docs_check.py`:

```python
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

    def test_a_claim_is_not_matched_inside_a_longer_word_on_its_left(self):
        """`_appears` originally checked only the trailing boundary, so `page` matched inside
        `per_page` and the enum value `available` matched inside `unavailable`. Short enum
        values and bare field names are recorded as claims, so both edges need checking."""
        record = check.parse_sources(
            "## references/x.md\n\n### https://example.invalid/a.html\nfetched: 2026-09-10\n"
            "params:\n- page\n- available\n")[0]
        self.assertEqual(
            check.missing(record, "per_page is documented and the course is unavailable"),
            [("param", "page"), ("param", "available")])

    def test_a_path_still_matches_inside_a_full_url(self):
        """A path claim begins with `/`, which is already its own left boundary. Checking the
        left edge unconditionally would make every path inside a rendered absolute URL read as
        missing, turning a silent false negative into a noisy false positive."""
        record = check.parse_sources(
            "## references/x.md\n\n### https://example.invalid/a.html\nfetched: 2026-09-10\n"
            "endpoints:\n- GET /api/v1/courses\n")[0]
        self.assertEqual(
            check.missing(record, "see https://canvas.example.com/api/v1/courses for more"), [])


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


class Entities(unittest.TestCase):
    """Canvas documentation pages are fetched as raw HTML, so a claim containing a quote,
    an ampersand or an angle bracket does not appear literally in the bytes. Matching
    without decoding reports such a claim missing while the page plainly shows it, and the
    only way an author can get a green run is to record a weaker claim than the truth."""

    def test_a_quoted_claim_matches_through_html_entities(self):
        record = check.parse_sources(
            "## references/x.md\n\n### https://example.invalid/a.html\nfetched: 2026-09-10\n"
            'params:\n- rel="next"\n')[0]
        page = "<p>the header carries rel=&quot;next&quot; when more pages remain</p>"
        text, code = check.report([record], lambda url: page)
        self.assertEqual(code, 0)
        self.assertIn("nothing missing", text)

    def test_a_genuinely_absent_quoted_claim_is_still_reported(self):
        """Decoding must not turn the check into one that always passes."""
        record = check.parse_sources(
            "## references/x.md\n\n### https://example.invalid/a.html\nfetched: 2026-09-10\n"
            'params:\n- rel="last"\n')[0]
        page = "<p>the header carries rel=&quot;next&quot; when more pages remain</p>"
        text, code = check.report([record], lambda url: page)
        self.assertEqual(code, 1)
        self.assertIn('MISSING param     rel="last"', text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tools -p 'test_canvas_docs_check.py' -v`

Expected: FAIL. The module file does not exist yet, so the import at the top raises `FileNotFoundError`.

- [ ] **Step 3: Write the checker**

Create `tools/canvas-docs-check.py`, executable:

```python
#!/usr/bin/env python3
"""Report Canvas documentation drift against the claims recorded in the skill's sources.md.

Build-side only. No Canvas token, no Canvas instance, no student data: this reads the public
Canvas documentation host and nothing else. It is never installed, and it writes nothing.

Pages are fetched as raw HTML and are decoded before matching, so a claim may be recorded
exactly as the documentation renders it. A miss means one of two things and this tool cannot
tell them apart: Canvas moved, or the reference was wrong when it was written. Both need
a person.
"""
import argparse
import html
import re
import sys
import urllib.request

DEFAULT_SOURCES = ".claude/skills/canvas-api-authoring/sources.md"
KEYS = ("endpoints", "params")

FILE_RE = re.compile(r"^## (\S+)\s*$")
URL_RE = re.compile(r"^### (https://\S+)\s*$")
FETCHED_RE = re.compile(r"^fetched:\s*(\S+)\s*$")
ITEM_RE = re.compile(r"^-\s+(.+?)\s*$")
VERB_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(\S+)$")


def parse_sources(text):
    """Read the sources record format into a list of dicts.

    Each dict has file, url, fetched, endpoints and params.
    """
    records, current_file, current, key = [], None, None, None
    for line in text.splitlines():
        match = FILE_RE.match(line)
        if match:
            current_file, current, key = match.group(1), None, None
            continue
        match = URL_RE.match(line)
        if match:
            current = {"file": current_file, "url": match.group(1), "fetched": None,
                       "endpoints": [], "params": []}
            records.append(current)
            key = None
            continue
        if current is None:
            continue
        match = FETCHED_RE.match(line)
        if match:
            current["fetched"] = match.group(1)
            key = None
            continue
        stripped = line.strip()
        if stripped[:-1] in KEYS and stripped.endswith(":"):
            key = stripped[:-1]
            continue
        match = ITEM_RE.match(line)
        if match and key:
            current[key].append(match.group(1))
            continue
        if stripped:
            key = None
    return records


def _path_of(endpoint):
    """The path part of a 'VERB /api/v1/...' entry, or the entry unchanged."""
    match = VERB_RE.match(endpoint)
    return match.group(2) if match else endpoint


def _joins(char):
    """True if char would make an adjacent claim part of a longer name or path."""
    return char == "/" or char.isalnum() or char == "_" or char == "-"


def _appears(claim, page):
    """True if claim occurs in page whole, not as part of a longer name.

    Both kinds of claim need this. Canvas paths nest, so /courses/:course_id/quizzes is a
    substring of /courses/:course_id/quizzes/:id. Short names nest too: page sits inside
    per_page, id inside grid, and the enum value available inside unavailable. A plain
    substring test would keep reporting any of them as present long after it was removed,
    which is the one drift this tool exists to catch.

    Each edge is checked only when the claim's own character on that edge is a word
    character. A path begins with `/`, which is already its own left boundary, so checking
    its left edge would make it read as missing inside a rendered absolute URL. A bracketed
    parameter ends with `]`, which is likewise its own right boundary.
    """
    if not claim:
        return True
    check_left = claim[0].isalnum() or claim[0] == "_"
    check_right = claim[-1].isalnum() or claim[-1] == "_"
    start = 0
    while True:
        found = page.find(claim, start)
        if found < 0:
            return False
        left = page[found - 1:found] if found else ""
        right = page[found + len(claim):found + len(claim) + 1]
        if not (check_left and _joins(left)) and not (check_right and _joins(right)):
            return True
        start = found + 1


def missing(record, page):
    """Claims in record that no longer appear in page, as (kind, claim) pairs.

    Endpoints match on the path alone: a rendered page routinely puts the verb in a table
    cell away from the path, so requiring them adjacent would report drift that is not there.
    """
    gone = []
    for endpoint in record["endpoints"]:
        if not _appears(_path_of(endpoint), page):
            gone.append(("endpoint", endpoint))
    for param in record["params"]:
        if not _appears(param, page):
            gone.append(("param", param))
    return gone


def report(records, fetch):
    """Check every record and return the printed text and the exit code."""
    lines, bad, shown = [], 0, None
    for record in records:
        try:
            page = fetch(record["url"])
        except Exception as error:  # any fetch failure is a result, not a crash
            if record["file"] != shown:
                shown = record["file"]
                lines.append(shown)
            lines.append("  %s" % record["url"])
            lines.append("    ERROR  %s" % error)
            bad += 1
            continue
        gone = missing(record, html.unescape(page))
        if not gone:
            continue
        if record["file"] != shown:
            shown = record["file"]
            lines.append(shown)
        lines.append("  %s (fetched %s)" % (record["url"], record["fetched"]))
        for kind, claim in gone:
            lines.append("    MISSING %-9s %s" % (kind, claim))
        bad += 1
    lines.append("")
    lines.append("%d pages checked, %d with something missing" % (len(records), bad))
    if not bad:
        lines.append("nothing missing")
    return "\n".join(lines), (1 if bad else 0)


def _fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sources", default=DEFAULT_SOURCES,
                        help="path to sources.md (default: %s)" % DEFAULT_SOURCES)
    args = parser.parse_args(argv)
    with open(args.sources) as handle:
        records = parse_sources(handle.read())
    if not records:
        sys.stderr.write("canvas-docs-check: no source records in %s\n" % args.sources)
        return 2
    text, code = report(records, _fetch)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `chmod +x tools/canvas-docs-check.py && python3 -m unittest discover -s tools -p 'test_canvas_docs_check.py' -v`

Expected: PASS, 15 tests, OK.

- [ ] **Step 4b: Confirm by inspection that the tool writes nothing**

Run: `grep -n "open(" tools/canvas-docs-check.py`

Expected: exactly one match, the `open(args.sources)` read in `main`, with no mode argument. The tool reports; a human decides. This is checked by eye rather than by a unit test, because a test that greps its own module's source for a quoted mode string fails on unrelated edits.

- [ ] **Step 5: Confirm the existing suite is untouched**

Run: `python3 -m unittest test_canvas_api_guard test_canvas_api_operations 2>&1 | tail -5`

Expected: OK. This task adds files and changes nothing the suite covers, so any failure here is pre-existing and must be reported, not fixed in this task.

- [ ] **Step 6: Commit**

```bash
git add tools/canvas-docs-check.py tools/test_canvas_docs_check.py
git commit -m "feat(tools): hand-run Canvas documentation drift check"
```

---

## Task 3: The design decision reference

**Files:**
- Create: `.claude/skills/canvas-api-authoring/references/passthrough-or-function.md`
- Read for evidence: `level2/README.md`, `level2/SKILL.md`, `codex/skills/canvas-api-guard/SKILL.md`

**Interfaces:**
- Consumes: the routing table row written in Task 1.
- Produces: nothing later tasks depend on. Independent of Tasks 4-9.

- [ ] **Step 1: Get the current operation list from CodeGraph, not from memory**

Run the CodeGraph search tool for `OPERATIONS`, and the context tool as in Task 1 Step 1.

Expected: the live `OPERATIONS` dict. Use it to confirm the precedent list below still matches reality. If an operation has been added or removed since 2026-09-10, write what is actually there.

- [ ] **Step 2: Write the reference**

Create the file with these five sections, in this order. This reference is the one place a local verb or flag may be named in prose; no `/usr/local/libexec/` command line may appear.

1. `## The question` — one paragraph. Every Canvas task is one of four shapes, and picking the wrong one costs either a needless program or an unsafe one.

2. `## Start here: is it one documented call?` — the default and the bar. Quote the standing rule from `level2/README.md`: an operation that would be a single documented API call is deliberately absent. State the two things that are not reasons to leave this option: a different projection of the same read is `--fields`, and a complete collection is `--all-pages`.

3. `## Four outcomes` — a table, then a subsection each.

| Outcome | Choose it when |
| --- | --- |
| A documented passthrough call | one endpoint does it |
| A plan through `run-plan` | ordered writes with no computation between them |
| A named Level 2 function | a result must be computed, validated or proven beyond what one read-back reaches |
| A new guard verb | what is needed is a property at the credential boundary |

   Each subsection states the test to apply and one worked example from the repo. For the plan outcome, be explicit that `run-plan` changed this decision: before it, several ordered writes argued for a function, and now they do not.

   For the function outcome, list the five things that still earn one: a result computed or joined across reads before any write is proposed; verification needing evidence a single read-back cannot reach; structured input validated against live Canvas state first; a safety invariant that must hold across the whole job; local files and their provenance.

   For the guard verb outcome, give both existing examples and their reasons: `draft` because the guard itself must hold the authority to refuse, `download-submission-file` because it must use the token without exposing it. State plainly that this is the rarest outcome and that wanting convenience is never the reason.

4. `## Worked precedent` — a table of the eight operations that exist as of 2026-09-10 with the reason each earned its place, drawn from the table in `level2/README.md`. Head it with a line saying this is history as of that date, and that the live list comes from CodeGraph.

5. `## What does not justify a function` — ergonomics, a wrapper over one call, a shape a projection already gives, and a sequence a plan already gives.

- [ ] **Step 3: Verify the constraints**

Run: `grep -rn '/usr/local/libexec/' .claude/skills/canvas-api-authoring/ ; echo "exit $?"`
Expected: no matches, `exit 1`.

Run: `grep -c 'run-plan\|draft\|download-submission-file' .claude/skills/canvas-api-authoring/references/passthrough-or-function.md`
Expected: a non-zero count. This reference is supposed to name them.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/canvas-api-authoring/references/passthrough-or-function.md
git commit -m "feat(skill): the passthrough, plan, function or guard-verb decision"
```

---

## Tasks 4-9: The six Canvas references

These six tasks are identical in shape and independent of each other. Each one:

1. Fetches its documentation pages, listed per task below.
2. Writes its reference file using the section template from Global Constraints, with the section headings listed in that task.
3. Appends its `##` block to `.claude/skills/canvas-api-authoring/sources.md` recording every page, every endpoint path and every parameter name the reference states.
4. Runs the checker against only its own block and confirms zero missing.
5. Runs the grep constraints.
6. Commits.

**The shared step list.** Every one of Tasks 4 through 9 runs exactly these steps, with `<REF>` the reference file name and the pages and headings taken from that task.

- [ ] **Step 1: Fetch every documentation page for this reference**

Fetch each URL listed in the task. For each, ask for every endpoint verb and path verbatim, every parameter name verbatim including bracket nesting, and any stated behaviour about ordering, defaults, publishing or side effects.

Do not proceed on a page that failed to fetch, and do not fill a gap from memory. If a page redirects, follow it and record the URL you actually read; `file_uploads.html` redirects to `file.file_uploads.html`, and others may too.

- [ ] **Step 2: Write the reference**

Create `.claude/skills/canvas-api-authoring/references/<REF>` with the section headings listed in the task, each following the five-part template. Copy every parameter name verbatim. Give every trap its `(docs: <url>)` or `(repo: <path>)` evidence.

- [ ] **Step 3: Record the claims in sources.md**

Append to `.claude/skills/canvas-api-authoring/sources.md` a `## references/<REF>` block, then one `### <url>` block per page with `fetched: 2026-09-10`, an `endpoints:` list of every endpoint the reference names, and a `params:` list of every parameter name the reference names. The format is exact; see Global Constraints.

- [ ] **Step 4: Run the drift check and confirm the recording is right**

```bash
python3 tools/canvas-docs-check.py --sources .claude/skills/canvas-api-authoring/sources.md
```

Expected: exit 0 and `nothing missing`. A miss here means the reference states something the page does not, which is a defect in the reference, not in Canvas. Fix the reference. This is the red-proof for a prose task: it is the check that the claims came from the page rather than from recall.

- [ ] **Step 5: Verify the constraints**

Run: `grep -rn '/usr/local/libexec/' .claude/skills/canvas-api-authoring/ ; echo "exit $?"`
Expected: no matches, `exit 1`.

Run: `grep -n 'canvas_api_guard\|canvas_api_operations\|--all-pages\|--fields\|run-plan\|--dry-run' .claude/skills/canvas-api-authoring/references/<REF> | grep -v 'repo:' ; echo "exit $?"`
Expected: no output, `exit 1`. The six Canvas references name no local verb or flag outside a line carrying a `repo:` evidence citation, since a repo file path may legitimately contain one of these strings.

Run: `grep -c 'fetched 2026-09-10' .claude/skills/canvas-api-authoring/references/<REF>`
Expected: one per section, matching the section count.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/canvas-api-authoring/references/<REF> .claude/skills/canvas-api-authoring/sources.md
git commit -m "feat(skill): <REF> Canvas reference"
```

---

### Task 4: `fundamentals.md`

**Pages to fetch:**
- `https://canvas.instructure.com/doc/api/file.pagination.html`
- `https://canvas.instructure.com/doc/api/file.object_ids.html`
- `https://canvas.instructure.com/doc/api/file.throttling.html`
- `https://canvas.instructure.com/doc/api/file.endpoint_attributes.html`
- `https://canvas.instructure.com/doc/api/courses.html`
- `https://canvas.instructure.com/doc/api/enrollments.html`
- `https://canvas.instructure.com/doc/api/sections.html`
- `https://canvas.instructure.com/doc/api/progress.html`
- `https://canvas.instructure.com/doc/api/file.changelog.html`

**Sections:**
- `### Finding the course and who is in it`
- `### Getting a whole collection back` (pagination, `Link` headers, `per_page`)
- `### Asking for more of an object` (`include[]` and its cost)
- `### Naming a thing that is not a Canvas id` (SIS ids and the `sis_...:` prefix form)
- `### Published, unpublished, and workflow_state`
- `### Dates, and who they apply to` (the base object's dates versus overrides)
- `### HTML fields and what Canvas does to them`
- `### A quiz is an assignment underneath, and so is a graded discussion`
- `### Long jobs that answer later` (the Progress object)
- `### When the API pushes back` (throttling, and where the change log lives)

---

### Task 5: `assignments.md`

**Pages to fetch:**
- `https://canvas.instructure.com/doc/api/assignments.html`
- `https://canvas.instructure.com/doc/api/assignment_groups.html`
- `https://canvas.instructure.com/doc/api/assignment_extensions.html`
- `https://canvas.instructure.com/doc/api/peer_reviews.html`
- `https://canvas.instructure.com/doc/api/late_policy.html`
- `https://canvas.instructure.com/doc/api/learning_object_dates.html`

**Sections:**
- `### Creating an assignment`
- `### Choosing how students turn it in` (`submission_types` and what each implies)
- `### Where it sits and what it is worth` (assignment groups, weighting, `points_possible`, `grading_type`)
- `### Dates, and giving one student different ones` (overrides, `only_visible_to_overrides`)
- `### Editing an assignment that already has submissions`
- `### Publishing and unpublishing`
- `### Peer review`
- `### Late and missing policy`
- `### Deleting an assignment`

---

### Task 6: `quizzes.md`

**Pages to fetch:**
- `https://canvas.instructure.com/doc/api/quizzes.html`
- `https://canvas.instructure.com/doc/api/quiz_questions.html`
- `https://canvas.instructure.com/doc/api/quiz_question_groups.html`
- `https://canvas.instructure.com/doc/api/quiz_submissions.html`
- `https://canvas.instructure.com/doc/api/quiz_submission_questions.html`
- `https://canvas.instructure.com/doc/api/quiz_assignment_overrides.html`
- `https://canvas.instructure.com/doc/api/quiz_extensions.html`
- `https://canvas.instructure.com/doc/api/course_quiz_extensions.html`
- `https://canvas.instructure.com/doc/api/quiz_reports.html`
- `https://canvas.instructure.com/doc/api/quiz_statistics.html`
- `https://canvas.instructure.com/doc/api/quiz_ip_filters.html`
- `https://canvas.instructure.com/doc/api/assessment_question_banks.html`
- `https://canvas.instructure.com/doc/api/new_quizzes.html` (stub section only)
- `https://canvas.instructure.com/doc/api/new_quiz_items.html` (stub section only)

**Sections:**
- `### Creating the quiz shell` (`quiz_type` and what each one does to the gradebook)
- `### Adding questions` (one subsection listing every `question_type` with its `answers[]` shape verbatim)
- `### Randomising with question groups` (and picking from a question bank)
- `### What the quiz is worth` (that `points_possible` is derived from the questions, not set)
- `### Time limits, attempts and what students see afterwards`
- `### Accommodations and access` (extensions, IP filters, access codes)
- `### Giving one student different dates` (quiz assignment overrides)
- `### Publishing`
- `### Attempts and their answers`
- `### Statistics and reports`
- `### New Quizzes is a different API` — the stub. State that it is a separate service with its own endpoints, that the Classic endpoints above do not reach it, name the pages, and say what an instructor sees that tells the two apart. Claim no coverage.

---

### Task 7: `rubrics-and-grades.md`

**Pages to fetch:**
- `https://canvas.instructure.com/doc/api/rubrics.html`
- `https://canvas.instructure.com/doc/api/submissions.html`
- `https://canvas.instructure.com/doc/api/grading_standards.html`
- `https://canvas.instructure.com/doc/api/grading_periods.html`
- `https://canvas.instructure.com/doc/api/enrollments.html`
- `https://canvas.instructure.com/doc/api/courses.html`
- `https://canvas.instructure.com/doc/api/gradebook_history.html`

**Sections:**
- `### Creating a rubric` (the indexed Hash shape of `rubric[criteria]`, verbatim, and the ratings inside it)
- `### Attaching a rubric to something` (`rubric_association`, `purpose`, `use_for_grading`)
- `### Grading a submission`
- `### Grading against a rubric` (`rubric_assessment` and its key shape)
- `### Comments on a grade`
- `### Grade versus posted grade` (posting policy, hidden grades)
- `### What letter a score becomes` (grading standards)
- `### Grading periods`
- `### Final grades, and overriding one`
- `### Who changed a grade and when` (gradebook history)

Two traps here are repo-verified rather than documentation-derived, and must be labelled as such: Canvas documents no read for a single rubric association, so a read-back of a newly created one may 404 (repo: `level2/SKILL.md`); and a rubric criterion is not a field of the submission object, so proving a criterion needs its own read (repo: `level2/README.md`).

---

### Task 8: `submissions-and-files.md`

**Pages to fetch:**
- `https://canvas.instructure.com/doc/api/submissions.html`
- `https://canvas.instructure.com/doc/api/submission_comments.html`
- `https://canvas.instructure.com/doc/api/files.html`
- `https://canvas.instructure.com/doc/api/file.file_uploads.html`
- `https://canvas.instructure.com/doc/api/content_exports.html`
- `https://canvas.instructure.com/doc/api/quiz_submission_files.html`

**Sections:**
- `### Listing submissions for an assignment`
- `### Listing submissions across several assignments at once`
- `### Finding who has not been graded`
- `### One student's submission, and its attempts`
- `### The files a student attached`
- `### Downloading an attachment`
- `### Uploading a file: the three steps` — document all three verbatim, including that step two posts to a host Canvas names in the response rather than to the Canvas host, that it takes no token, and that it answers with a redirect whose Location must then be confirmed. Document the URL alternative and the Progress polling it uses.
- `### Where an uploaded file goes` (folders, `parent_folder_path`, `on_duplicate`)
- `### Exporting a whole course or assignment`

---

### Task 9: `course-content.md`

**Pages to fetch:**
- `https://canvas.instructure.com/doc/api/announcements.html`
- `https://canvas.instructure.com/doc/api/discussion_topics.html`
- `https://canvas.instructure.com/doc/api/modules.html`
- `https://canvas.instructure.com/doc/api/pages.html`
- `https://canvas.instructure.com/doc/api/courses.html`
- `https://canvas.instructure.com/doc/api/tabs.html`

**Sections:**
- `### Posting an announcement` (that an announcement is a discussion topic with `is_announcement`, and what the announcements endpoint is for)
- `### Delaying an announcement until a date`
- `### Creating a page`
- `### Editing a page, and its url versus its title`
- `### Publishing a page`
- `### Making a page the course home page` (both halves: the page's `front_page`, and the course's `default_view`)
- `### Building a module`
- `### Putting things in a module` (module items, `type`, `content_id`, `page_url`, indent)
- `### Requirements and prerequisites`
- `### Publishing a module, and what that does to its items`
- `### Which tabs students see`

---

## Task 10: Final assembly check

**Files:**
- Modify, only if a check fails: any file in `.claude/skills/canvas-api-authoring/`

**Interfaces:**
- Consumes: everything from Tasks 1-9.
- Produces: a verified skill.

- [ ] **Step 1: Run the drift check over the whole sources file**

```bash
python3 tools/canvas-docs-check.py --sources .claude/skills/canvas-api-authoring/sources.md
```

Expected: exit 0, `nothing missing`, and a page count matching the total pages listed across Tasks 4-9.

- [ ] **Step 2: Confirm every routing table target exists**

```bash
cd .claude/skills/canvas-api-authoring && \
  grep -o 'references/[a-z-]*\.md' SKILL.md | sort -u | while read f; do
    test -f "$f" && echo "ok   $f" || echo "GONE $f"; done
```

Expected: seven `ok` lines, no `GONE`.

- [ ] **Step 3: Confirm the no-local-content constraint across the whole skill**

```bash
grep -rn '/usr/local/libexec/' .claude/skills/canvas-api-authoring/ ; echo "libexec exit $?"
grep -rn 'canvas_api_guard\|canvas_api_operations\|--all-pages\|--fields\|--dry-run' \
  .claude/skills/canvas-api-authoring/references/ | grep -v passthrough-or-function | grep -v 'repo:'
echo "leak exit $?"
```

Expected: `libexec exit 1` with no matches, and `leak exit 1` with no output.

- [ ] **Step 4: Confirm every trap carries evidence**

```bash
for f in .claude/skills/canvas-api-authoring/references/*.md; do
  n=$(awk '/^\*\*Traps\.\*\*/,/^\*\*Source\.\*\*/' "$f" |
      grep '^- ' | grep -cv '(docs:\|(repo:')
  echo "$n $f"
done
```

Run it per file rather than over a glob, because an awk range across a concatenated stream can run past the end of one file into the next.

Expected: every line starts with `0`. Every bullet in a Traps block cites either a documentation URL or a repo path. Any non-zero count names a file whose traps need evidence added.

- [ ] **Step 5: Confirm the existing test suite still passes**

```bash
python3 -m unittest test_canvas_api_guard test_canvas_api_operations 2>&1 | tail -5
python3 -m unittest discover -s tools -p 'test_canvas_docs_check.py' 2>&1 | tail -3
```

Expected: OK from both. Nothing in this plan touches guard or Level 2 code, so a failure in the first is pre-existing and must be reported rather than fixed here.

- [ ] **Step 6: Read SKILL.md end to end as a stranger**

Confirm by reading, not by grep: the routing table sends a reader somewhere useful for each of the seven rows; the capability section names the CodeGraph query and the help commands and states the boundary between them; and nothing in the file claims what the guard can currently do.

- [ ] **Step 7: Commit**

```bash
git add -A .claude/skills/canvas-api-authoring/
git commit -m "chore(skill): canvas-api-authoring assembly checks pass"
```

---

## Self-review notes

**Spec coverage.** Build-side location, Task 1. Canvas-first content with no guard constraint, Tasks 4-9 plus the Step 5 grep. Live capability lookup, Task 1 Steps 1-2. CodeGraph surface versus behaviour boundary, Task 1 Step 2. Intent-first organisation, the section headings in Tasks 4-9. Verbatim parameters with sources, Global Constraints plus Step 3 of each. Drift check on demand, Task 2. Nothing live-tested, stated in `SKILL.md`. Classic quizzes with New Quizzes stubbed, Task 6. Four-way decision, Task 3. Layout, the File Structure table. Testing section, Task 10.

**Known adaptation.** Six of the ten tasks produce prose, which has no red-green cycle. Their red-proof is Step 4: the drift checker fails when a reference states something its cited page does not, which is exactly the failure mode that matters. Task 2 is real code and is written test-first.

**Task 2's code was run before this plan was committed.** Both blocks were extracted from this document and executed on 2026-09-10. The first draft had a real defect: `missing` used a substring test, so a removed collection endpoint stayed invisible whenever its `/:id` sibling survived. Two tests caught it. The fix is `_appears`, and reverting it to `in` returns those two tests to red, which is the red-proof. As it now stands in this document, all ten tests pass. An implementer copying these blocks gets working code, but should still run Step 2 and watch it fail for the right reason before writing the module.
