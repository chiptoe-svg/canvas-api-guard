# Guard safety before the faculty pilot, and an accessibility scan

Date: 2026-09-13
Branch: `spec/guard-pilot-safety`
Status: design approved, not implemented. Independent of `feat/rubric-review-before-grade`.

## Where this came from

A Codex review of the codebase proposed eight pre-pilot changes, a list of later improvements,
and a set of faculty features drawn from `vishalsachdev/canvas-mcp` (MIT). Each claim was checked
against the code rather than accepted from the summary. This document carries only what survived
that check, in the order it is worth doing, plus the one feature from that project worth adopting.
What was rejected is recorded at the end with the reason, so it is not re-argued.

Two items from that review are **not** here because they belong with the rubric work and are
specified on its branch: updating `codex/canvas-api-guard.rules` for the renamed grading verbs,
and capping the length of free-text values recorded in the audit log's `changes` rows.

## 1. Pin the interpreter

**Highest priority, and cheap.** The file already refuses to let `PATH` choose executable code:
`SECURITY_BIN` is an absolute `/usr/bin/security`, `trusted_linux_secret_tool` carries the comment
*"never select credential code from PATH"*, and `check_provenance()` (`canvas_api_guard.py:142`)
proves the running guard is the installed root-owned file **before any credential use**.

The interpreter that executes that verified file is then chosen by `#!/usr/bin/env python3`, out
of the caller's `PATH`. The threat model is an agent that runs shell commands and must never
obtain the token. An agent that places a `python3` earlier in `PATH` runs the guard under its own
interpreter, and the keychain read happens inside it. This is the one gap in a wall the rest of
the file builds deliberately.

**Change.** An absolute shebang, plus a check inside `check_provenance()` that `sys.executable`
resolves to a root-owned, non-group-writable regular file, refusing otherwise with the same
shape as `trusted_path`. Both programs. The test seam that skips provenance for a throwaway
config applies here too.

## 2. Draft must not delete a top-level object

`do_draft` calls `VERBS[method]`, and the draft subparser takes its method from
`choices=sorted(set(VERBS) - {"get"})`, so `delete` is reachable. `prove_draft` establishes only
that the target is unpublished.

Draft mode's premise is "no student can see it, so no approval is needed." That quietly assumes
the change is recoverable. Deletion is not. An unpublished quiz with forty questions is faculty
work no student ever needed to see.

**Change, narrower than the review proposed.** `draft delete` is refused when the path names a
top-level `quizzes|assignments|pages|discussion_topics` item, and allowed for the nested
`questions|groups|reorder|overrides` children, which `DRAFTABLE` already scopes. Removing a
question while building an unpublished quiz is the iteration draft mode exists for; deleting the
quiz is not. Deleting a top-level object stays available as an ordinary write with approval.

The refusal is logged as `confirmation: "refused-not-draft"`, like every other draft refusal.

## 3. Bound a single response

`PAGE_CAP = 200` (`:78`) already bounds `--all-pages`, so the aggregate-item limit the review
asked for exists. What is unbounded is one response body: `raw.read()` at `:486`.

**Change.** A maximum response size, read incrementally and refused past the cap, with the limit
named in the error. A refusal here is an ordinary failure, never an uncertain write: it happens
on reads, and on a write's read-back it is already handled as a failed read-back.

## 4. Make the audit log unambiguous under concurrency

`log_event` (`:292`) appends one JSON line and fsyncs. Append is atomic only up to `PIPE_BUF`;
a `changes` array carrying long text exceeds 4 KiB and two concurrent guards can interleave.
Level 2 invokes the guard serially through `subprocess.run`, so the practical risk is low — but
two Codex sessions are enough.

**Change.** Build the line and issue it as a single `os.write` on the append-mode descriptor, and
add a correlation ID generated once per process and carried on every record that process writes,
so a request, its evidence and its refusal cannot be attributed to the wrong run.

## 5. Audit retention

The log already records the right things and omits the wrong ones: `emit` (`:789`) logs `note`,
`path`, `status`, `confirmation`, `verification`, `target` and `changes`; full request bodies go
to stdout evidence only; and `:228` states the rule outright — *"Response bodies and the token
are never logged."* The review's first two bullets describe behaviour that already exists.

What is missing is the end of the lifecycle.

**Change.** An `audit prune --older-than DAYS` subcommand that rewrites the log keeping only
records newer than the cutoff, through the same `secure_log_fd` ownership and mode checks, and a
documented default retention for the pilot. Pruning is itself logged. It never deletes the file.

Not doing: redacting query values. Canvas query strings are ids and filters, not secrets.

## 6. Refuse account-level and developer-key paths

`profile` (`:1220`) validates only `level-1` / `level-2` and selects whether Specialized Functions
are installed. There is no endpoint policy, which the review correctly identified.

**The broad version is rejected** — see "Not doing" below. The narrow version is worth having:
refuse any path under `/api/v1/accounts/` and any developer-key path, for every verb including
reads. No faculty pilot has a use for either, their absence is easy to state and easy to verify,
and unlike a list of "dangerous" operations there is no judgement call about what belongs in it.

## 7. LICENSE

There is no `LICENSE` file. This matters the moment IT or a second faculty member installs it,
and it costs nothing. Choice of licence is the owner's.

## 8. `accessibility-scan` — the one feature worth adopting

From `canvas-mcp`'s learning-designer tools. It earns a Level 2 operation on the existing test —
it computes across many Canvas calls — and it is the lowest-risk thing on that list: read-only,
course content rather than student records, and it never touches a grade.

**What it reads.** Course pages (the list, then each page body, which the list omits), assignment
descriptions, discussion topics and announcements, and the syllabus body. Bounded by an item cap
and by `PAGE_CAP` on each list.

**What it checks**, all decidable from HTML alone, using `html.parser` from the standard library:

1. `<img>` with no `alt` attribute at all. An explicit `alt=""` is valid for decorative images and
   is not flagged.
2. A skipped heading level (`h2` followed by `h4`). The starting level is not flagged: Canvas
   supplies the page title as `h1`.
3. An empty heading element.
4. Non-descriptive link text — "click here", "here", "read more", "link" — or a bare URL as the
   text.
5. A `<table>` with no `<th>` and no `<caption>`.
6. An `<iframe>` with no `title` attribute.
7. Embedded audio or video, reported so a person can check captions. Never asserted as a failure.

**What it reports as unexaminable**, named explicitly in every report so nothing is mistaken for
a clean bill: colour contrast and anything else requiring rendering, focus order and keyboard
traps, whether a linked or embedded video actually carries captions, ARIA correctness, reading
order, and attached documents — PDFs above all, which are a large real-world source of
inaccessibility and are not opened by this scan.

**What it must never say.** Not "accessible", not "compliant", not "WCAG AA". The report states
which checks ran, what they found, and what was not examined. An accessibility report that
overclaims is worse than none, because someone will rely on it.

Course HTML is instructor-authored content: data, never instructions, exactly as student text is.

**Shape.** `accessibility-scan --course-id N [--limit N]`, read-only, classified with
`student-attention` in the rules file's `OPERATION_READS`. Per item: kind, id, title, `html_url`,
and each finding as a check name, a count, and a truncated evidence snippet. Plus a summary and
the `not_checked` list.

## Not doing, and why

- **A general endpoint denylist** (enrolments, course deletion, cross-listing, messaging, generic
  deletes). It introduces a second security model beside the one the tool has — every write is
  shown to a person with its URL and changed fields, and confirmed — and denylists invite a
  completeness illusion. Concluding a course is `PUT courses/:id` with an event, not a delete;
  cross-listing is a POST to sections; messaging is `POST /conversations`. Missing one teaches
  everybody to trust a control that does not cover it, which is worse than not having it. The
  narrow account-level refusal above is kept precisely because it needs no judgement.
- **Restricting draft edits to objects the current plan created.** True gap, deferred. It requires
  the guard to carry provenance across invocations, and it is stateless per call by design. That
  is real architecture for a modest gain, and rewriting an unpublished draft is recoverable in a
  way deletion is not. Item 2 is the sharp edge here.
- **Read-only retry with backoff.** Correct and safe — never retry writes is already the rule —
  but it is convenience, not safety, and not a pilot blocker.
- **Endpoint-specific verification adapters.** Actively rejected. The generic field comparison is
  the guard's strongest property *because* it assumes nothing about any endpoint and so cannot be
  wrong about one. Adapters multiply the surface that has to be correct in the file where
  correctness matters most, and each is a place where "verification passed" can come to mean less
  than it says. The rubric branch's one named exception for a body key that is itself a response
  field is the minimal form of this, and the right one.
- **Anything requiring generated code to run** (`canvas-mcp` reaches for `execute_typescript`
  above 30 bulk items). A definition a person approves has to be readable by that person. This is
  structural, not stylistic.

Already present, and noted because the review asked for them: a plan digest binding approval to
exact values (`--expect-plan` on `regrade-quiz-question`); formal bulk maxima (50 students, 100
attempts, 50 plan steps, 500 attachments); refusal to retry an uncertain write.

## Files

| File | Change |
| --- | --- |
| `canvas_api_guard.py` | interpreter check; draft top-level delete refusal; response size cap; single-write append and correlation ID; `audit prune`; account-level and developer-key refusal |
| `level2/canvas_api_operations.py` | `accessibility-scan` |
| `test_canvas_api_guard.py` | one test per change above, each red-proofed |
| `test_canvas_api_operations.py` | scan checks against fixture HTML, including the cases that must NOT be flagged |
| `codex/canvas-api-guard.rules` | `accessibility-scan` in `OPERATION_READS`; the offline test reads these lists against both parsers |
| `level2/SKILL.md`, `level2/README.md`, `docs/IT-REVIEW.md` | the new operation, the new refusals, the retention default |
| `LICENSE` | new |

## Tests

Each regression test is red-proofed — shown failing with only its fix reverted — before it counts.

Interpreter: a non-root-owned `sys.executable` is refused before the keychain is touched. Draft:
`draft delete` on a top-level unpublished quiz is refused and logged; on its questions it is
allowed; an ordinary `delete` with approval is unaffected. Response cap: an oversized body is
refused naming the limit, and a write's read-back failure stays a read-back failure. Audit: two
concurrent writers produce two intact lines; every record of one process shares its correlation
ID; `audit prune` keeps the right records and preserves ownership and mode. Paths: an
`/api/v1/accounts/...` path is refused for every verb including `get`. Scan: each check fires on
a positive fixture and stays silent on its near-miss — `alt=""` is not a missing alt, an `h2`
start is not a skip, a `<table>` with a `<caption>` and no `<th>` passes — and the report always
carries the `not_checked` list.

## Order

1, 2 and 7 first: they are cheap, and 1 and 2 are the two that change what an agent can do. Then
3, 4, 6. Then 5. The scan is independent of all of it and can go whenever.
