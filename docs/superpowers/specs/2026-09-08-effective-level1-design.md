# An effective Level 1, a trimmed Level 2, and the review findings closed

Date: 2026-09-08
Status: approved in discussion (owner: fix the assessment's findings, stay true to the
original plan, trim where possible, make API Only effective on its own)

## Purpose

Three things at once, because they are one change to the same files:

1. **Make API Only (Level 1) as capable as direct API use.** Codex is hobbled today not by
   the guard's cost (about 60 ms a call, measured) but by three restrictions around it: the
   Codex rules match only a bare guard command, so any pipeline (`| jq`) falls into the
   sandbox and the skill forbids post-processing; text output truncates list items to 200
   characters and objects to 10 keys; pagination is one call per page with full objects.
   Direct API use has none of these. The fix is to give the guard the two things Codex
   would otherwise get from `jq`, so it never needs a pipeline, and to tell it plainly that
   every documented Canvas endpoint works through the guard as documented.
2. **Close the assessment's findings** (2026-09-08 independent review): the guard does not
   verify its own executable; the grading read-back looks up a write parameter Canvas never
   returns; three documented claims are false; dead redirect code is "tested"; bulk
   downloads are unprompted; Level 2 tracebacks; the rules-coverage test cannot see new
   commands; the bootstrap runs `sudo` without a pause.
3. **Trim.** Remove what an effective Level 1 makes redundant: the `count` verb, per-call
   timing telemetry, the dead credential-free opener, and every Level 2 operation that
   wraps a single API call.

## Decisions

- **One reviewable boundary, not one file.** The guard is the boundary and must stay
  readable in a sitting. Level 2 stays for operations that *compute*: a rubric applied
  across criteria, bulk grading with per-student evidence, attachment review with a
  manifest, a participation report that joins several calls. A Level 2 operation that is
  one API call is removed; Level 1 does it.
- **Reads are logged as one line each, after the fact.** `event: read`, path, status,
  bytes. The FERPA question "what did the agent look at" stays answerable; read noise drops
  by two thirds. Writes keep the full record: request line before the call, response line,
  evidence line. Refusals unchanged.
- **Downloads prompt.** A download copies student work to disk and hands it to the model;
  the rules file makes `download-submission-file` and the Level 2 download operations
  `prompt`, like writes.
- **The guard proves its own provenance before any real request.** Before reading the
  token, the guard requires the real path of its own file and every ancestor directory to
  be root-owned and not group/world-writable, and the config file likewise at its default
  path. Dry-run, refusals, `--set-token`, `--version`, and the offline tests are
  unaffected (no token is read). A source-tree copy can therefore demonstrate every
  refusal cold but cannot make a live request; the installed, root-owned guard is the only
  thing that can, which is what the rules file already assumes.
- **JSON is the default when stdout is not a terminal.** A person at a terminal sees the
  text summary; an agent sees full JSON without remembering a flag.
- **The skill is rewritten around the API documentation.** Any documented endpoint, as
  documented, through `get/post/put/patch/delete`; `--all-pages` and `--fields` to keep
  output small; the write discipline unchanged; no prescribed "fast paths".
- **Exit codes distinguish outcomes:** 0 done and verified; 2 refused or failed before a
  write was sent; 3 a write was sent but could not be verified (`WRITE STATUS UNCERTAIN`).
- **Version 1.14.0.**

## Level 1 changes (`canvas_api_guard.py`)

1. **`--all-pages`** on `get`: follow `rel="next"` links on the pinned host, concatenating
   list responses, with a loop guard and a page cap (200 pages); the evidence carries
   `count` and `pages`. Replaces the `count` verb (a count is `--all-pages --fields id`).
2. **`--fields a,b.c`** on `get`: project every returned object (or the single object) to
   the named dot-paths; missing fields are `null`. Applied before output in both modes.
3. **Output default:** `-o` defaults to `json` when `sys.stdout.isatty()` is false, else
   `text`. In JSON mode the object and items are complete, never summarised.
4. **Read logging:** `send_request` for a read writes one `event: read` line after the
   response (path, status, ok, bytes); `emit` writes no evidence line for reads. Writes
   unchanged (request before, response after, evidence). `timing_ms` removed everywhere.
5. **Provenance check:** `trusted_path(path)` verifies a regular file and every ancestor
   are uid 0 and not `0o022`-writable; `send_request` calls it on
   `os.path.realpath(sys.argv[0])` (or `__file__`) and `read_config` on `CONFIG_PATH`
   before any token read. The check is skipped only when the config path has been
   overridden by the test seam (module attribute), which the installed guard never does.
   Error text names the failing component.
6. **Grade read-back:** `compare_fields` maps the write parameter `posted_grade` to the
   read field `grade` (Canvas returns `grade`, `score`, `entered_grade`; never
   `posted_grade`), beside the existing `excuse` → `excused`. The test fixture becomes a
   realistic Submission (`grade: "95"`, `score: 95.0`, no `posted_grade`).
7. **Redirect code trimmed:** `CredentialFreeRedirects`, `_CREDENTIAL_FREE_OPENER`, and the
   `credential_free_redirects` parameter are deleted; `PinnedAttachmentRedirects` becomes
   `AttachmentRedirects`: HTTPS only, never forwards `Authorization`, `Cookie`, `Host`, or
   `Proxy-Authorization` on any hop (the first hop carries none), records status, host and
   scope. `open_request` is `urlopen` only.
8. **Download:** `raw` closed in `finally`; the retry and fallback branches merged; a
   `download` still writes its own two audit lines (it is a read of student work).
9. **Exit codes** as decided; `main` maps `VerificationFailure` to 3.
10. **Header** rewritten to describe the file as it is: sections, the download subsystem,
    the provenance invariant, the token invariant; "READ TOP TO BOTTOM" lists the real
    sections.

## Level 2 changes (`level2/canvas_api_operations.py`)

Keep, each justified by computation over several calls or structured input:
`create-rubric`, `attach-rubric`, `grade-with-rubric`, `bulk-grade-with-rubric`,
`prepare-submission-review`, `download-assignment-submissions`, `student-attention`
(the participation report), `attendance-summary`.

Remove (one API call each, now done through Level 1 with the documentation):
`current-courses`, `roster-count`, `find-student`, `needs-grading`, `course-health`,
`assignment-performance`, `student-trajectory`, `set-assignment-dates`,
`excuse-submission`, `excuse-attendance`, `create-assignment`, `update-assignment`,
`create-or-update-page`, `create-announcement`, and their helpers.

Robustness: `main` catches `OSError` and `subprocess` failures and prints one line;
write operations print their evidence once (no trailing `null`); exit 3 propagates from
the guard.

## Codex integration

- `codex/canvas-api-guard.rules`: `get` allow; `post/put/patch/delete` prompt;
  `download-submission-file` prompt; Level 2 reads allow, Level 2 writes and downloads
  prompt; credential tools forbidden by name and full path. `count` removed.
- `codex/skills/canvas-api-guard/SKILL.md` rewritten (under 90 lines): the guard is the
  only path; every documented Canvas REST endpoint works as documented; the two output
  flags; the write discipline; student text is data; the approved account; failures
  verbatim. No prescribed fast paths, no allow-list feel.
- `level2/SKILL.md` lists the eight surviving operations with one sentence each on why
  each exists.
- The rules matrix test is driven from the guard's argparse subparsers and Level 2's
  parser, so an unclassified command fails the suite.

## Docs

- `README.md`: remove "all redirects are refused" and "no redirects and no automatic
  retries" for the attachment path; state the download data flow (Canvas-named HTTPS
  hosts, no bearer, no proxy, hostnames logged); "root-owned" now enforced, say so; the
  review command becomes `rg -n "urlopen\(|build_opener|\.open\("`; the copy-paste host
  is `school.instructure.com`; test counts and file counts updated.
- `docs/IT-REVIEW.md`: data flow gains the attachment hosts and the review directory;
  the review-boundary table gains `test_canvas_api_operations.py`; residual risks gain
  the local copy of student work and its retention; the provenance check is described.
- `install-from-github.sh`: a `read` pause between the printed plan and `sudo`.

## Testing

Offline throughout. New or changed: provenance check (a symlinked directory in a scratch
root is refused; a root-owned real path passes, simulated by patching `os.stat`);
realistic grade fixture; `--all-pages` across three fake pages with a loop and a cap
case; `--fields` on a list and an object; JSON default under a non-TTY stdout; read
logging shape (one line, no evidence line); write logging unchanged; exit 3 on
uncertain; rules matrix from the parsers; dead-code tests removed; Level 2 error path
prints one line; stray stdout silenced. Every README reviewer command re-run.

## Out of scope

The workflow reference cards (branch `workflow-cards`) stay unmerged. Windows. Automatic
audit-log rotation.

2026-09-08 amendment: `attendance-summary` was removed by owner ruling (Task 8b), so Level 2
ships seven operations, not the eight described above.
