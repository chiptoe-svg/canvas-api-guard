# Stage A: Edge Seam and Quiz Regrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Name the guard's edge seam in place so a host-side agent service can import the one guard file and replace six names, prove with a repeatable probe that a stock installation is byte-identical before and after, and add the one Level 2 operation the agent's write allowlist needs that does not yet exist: regrading a classic-quiz question for a whole class.

**Architecture:** The guard stays one stdlib file. Two lines change its behaviour: the installed opener disables environment proxies (the choice the attachment path already makes), and the bearer is attached only when the credential read returns one. A named `build_opener()` and a header paragraph make the seam explicit; a test class pins the six names and proves each is looked up at call time. A probe script under `tools/` exports a base commit and diffs audit records, stdout, stderr, exit codes and help against the working tree. The regrade operation lives in Level 2 like the others: reads and computes, then individually audited guard writes with per-attempt read-back.

**Tech Stack:** Python 3.9+ stdlib, POSIX sh, unittest

**Spec:** docs/superpowers/specs/2026-09-08-shared-core-host-and-agent-design.md (branch `spec/shared-core-host-and-agent`)

## Global Constraints

- One guard file: `canvas_api_guard.py` stays the single reviewable boundary; no new modules, no third-party imports, no policy class, no new config keys, no new audit fields.
- The token is read in exactly one function (`read_token`) and used on exactly one line (the `Authorization` header in `send_request`). `read_token` may now return `None`, meaning "no bearer: an edge's transport supplies the credential"; the host implementation never returns `None`.
- Exactly one `urllib.request.urlopen(` in the guard (inside `open_request`), plus exactly two `urllib.request.build_opener(` calls: the one inside the new `build_opener()` function, and the attachment opener in `open_attachment_request`, which is never proxied and is not part of the seam. `urllib.request.install_opener(build_opener())` is called once at import.
- The stock audit record key sets are pinned and must not change:
  - `read`: `bytes, event, ok, path, pid, source, status, timestamp, verb`
  - `request` (write): `confirmation, dry_run, event, kind, path, pid, request_body, source, timestamp, url, verb`
  - `response`: `bytes, event, ok, path, pid, source, status, timestamp, verb`
  - `evidence`: `changes, confirmation, event, note, path, pid, source, status, target, timestamp, verb, verification`
  - `refusal`: `confirmation, event, kind, path, pid, source, timestamp, verb`
- Exit codes unchanged: `0` verified; `2` refused or failed before a write was sent; `3` a write was sent and could not be verified.
- Existing tests pass unchanged, with one named exception: the version pin `test_the_version_is_1_14_0` becomes `test_the_version_is_1_15_0` in Task 1. Any other task that needs to edit an existing assertion stops and reports why.
- Version `1.15.0` (`USER_AGENT = "canvas-api-guard/1.15.0"`): the opener change is a behaviour change for a host that set `https_proxy`.
- Every commit ends with:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` then
  `Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp`
- No test touches the network or a real credential store: `urllib.request.urlopen` is replaced everywhere, `read_token` is patched, and `CONFIG_PATH` points at a throwaway file.
- Execution happens ONLY in the worktree `/Users/admin/projects/canvas_apiguard/.worktrees/stage-a`, on branch `stage-a-seam-regrade`, already created from `origin/main` at 310733d. Never run anything in the main checkout, which another session shares. Run `git status --porcelain --untracked-files=no` before every commit and stop if a file you did not touch is modified. `git add` only this task's files; never `git commit -a`.

## File Structure

| Path | Responsibility | Status |
|---|---|---|
| `canvas_api_guard.py` | the guard; gains `build_opener()`, an optional bearer, and an "Edge seam" header paragraph | modified |
| `test_canvas_api_guard.py` | gains `TestEdgeSeam` and `TestAuditFormat` | modified |
| `tools/replay-probe.py` | exports a base commit and diffs stock-install behaviour against the working tree | created |
| `README.md`, `docs/IT-REVIEW.md` | one paragraph each on the edge seam and the probe | modified |
| `level2/canvas_api_operations.py` | gains `regrade-quiz-question` | modified |
| `test_canvas_api_operations.py`, `level2/SKILL.md`, `level2/README.md`, `codex/canvas-api-guard.rules` | the operation's tests, docs and Codex rule | modified |

---

### Task 1: The edge seam, named in place

**Files:** Modify `canvas_api_guard.py` (header after the "WHAT IT DOES GIVE" paragraph, ~line 40; `USER_AGENT` line 50; the `install_opener` line 348; `send_request` line 469). Test `test_canvas_api_guard.py` (new class `TestEdgeSeam`, placed after `TestRedirectsAreRefused`). Modify `README.md` and `docs/IT-REVIEW.md` (one paragraph each).

**Interfaces:**
- Consumes: `RefuseRedirects`, `read_token`, `check_provenance`, `confirm`, `CONFIG_PATH`, `DEFAULT_DIR` as they exist.
- Produces: `build_opener() -> urllib.request.OpenerDirector`; `read_token()` may return `None`; the six-name seam documented in the header: `read_token`, `build_opener`, `confirm`, `check_provenance`, `CONFIG_PATH`, `DEFAULT_DIR`.

- [ ] **Step 1: Write the failing tests**

Add after `class TestRedirectsAreRefused` in `test_canvas_api_guard.py`:

```python
class TestEdgeSeam(GuardTestCase):
    """The six names an importing edge replaces. Each is looked up on the module at call time,
    so replacing it changes what the guard does; nothing else about the host path moves."""

    SEAM = ("read_token", "build_opener", "confirm", "check_provenance", "CONFIG_PATH", "DEFAULT_DIR")

    def test_the_seam_names_exist_and_are_named_in_the_header(self):
        for name in self.SEAM:
            self.assertTrue(hasattr(guard, name), name)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_api_guard.py")) as handle:
            header = handle.read().split("import argparse")[0]
        self.assertIn("EDGE SEAM", header)
        for name in self.SEAM:
            self.assertIn(name, header, "%s is not named in the header's edge seam paragraph" % name)

    def test_the_installed_opener_refuses_redirects_and_uses_no_environment_proxy(self):
        opener = urllib.request._opener
        self.assertTrue(any(isinstance(h, guard.RefuseRedirects) for h in opener.handlers))
        proxy = next(h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler))
        self.assertEqual(proxy.proxies, {})
        fresh = guard.build_opener()
        self.assertTrue(any(isinstance(h, guard.RefuseRedirects) for h in fresh.handlers))
        self.assertEqual(next(h for h in fresh.handlers
                              if isinstance(h, urllib.request.ProxyHandler)).proxies, {})

    def test_a_credential_read_of_none_sends_no_bearer_and_logs_the_same_line(self):
        with mock.patch.object(guard, "read_token", lambda: None), \
                mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload={"id": 1})) as urlopen:
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)
        sent = urlopen.call_args[0][0]
        self.assertNotIn("authorization", {name.lower() for name, _ in sent.header_items()})
        line = self.log_lines()[-1]
        self.assertEqual(sorted(line), ["bytes", "event", "ok", "path", "pid", "source",
                                        "status", "timestamp", "verb"])

    def test_the_host_credential_read_is_still_the_bearer(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload={"id": 1})) as urlopen:
            self.run_main(["get", "courses/1"])
        sent = urlopen.call_args[0][0]
        self.assertEqual(sent.get_header("Authorization"), "Bearer " + TOKEN)

    def test_check_provenance_and_confirm_are_looked_up_at_call_time(self):
        def refuse():
            raise guard.GuardError("edge provenance refused")
        with mock.patch.object(guard, "check_provenance", refuse), \
                mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 2)
        self.assertIn("edge provenance refused", self.last_stderr)
        urlopen.assert_not_called()

        def approve(cfg, lines):
            cfg.confirmation = "edge:test"
        responses = [FakeResponse(payload={"id": 1, "name": "A"}),
                     FakeResponse(payload={"id": 1, "name": "X"}),
                     FakeResponse(payload={"id": 1, "name": "X"})]
        with mock.patch.object(guard, "confirm", approve), \
                mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["put", "courses/1", "-d", '{"course": {"name": "X"}}'])
        self.assertEqual(code, 0)
        self.assertEqual([l["confirmation"] for l in self.log_lines() if l["event"] == "request"],
                         ["edge:test"])
```

Note for the implementer: `self.last_stderr` and `TOKEN` already exist in the test module (used by other tests). If `confirm`'s signature differs from `(cfg, lines)`, read `confirm` first and match it exactly; do not change `confirm`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest test_canvas_api_guard.TestEdgeSeam -v`
Expected: `test_the_seam_names_exist_and_are_named_in_the_header` fails on `build_opener`; `test_the_installed_opener_refuses_redirects_and_uses_no_environment_proxy` fails (no `ProxyHandler` with empty proxies, and no `build_opener`); `test_a_credential_read_of_none_sends_no_bearer_and_logs_the_same_line` fails with `TypeError` (`"Bearer " + None`). The other two pass already.

- [ ] **Step 3: Make the two code changes and name the seam**

In `canvas_api_guard.py`:

1. Replace the line `urllib.request.install_opener(urllib.request.build_opener(RefuseRedirects))` with:

```python
def build_opener():
    """The opener every pinned API call goes through: no environment proxy, and no redirect.

    An edge that fronts the guard with its own transport (a credential-injecting gateway with
    a pinned address and CA bundle) installs its own opener in place of this one."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirects)

urllib.request.install_opener(build_opener())
```

2. Replace `headers["Authorization"] = "Bearer " + read_token()                   # the only use` with:

```python
    token = read_token()                     # the only credential read; None = an edge's
    if token is not None:                    # transport carries the credential instead
        headers["Authorization"] = "Bearer " + token                       # the only use
```

3. Update the comment block above `read_token` (line ~136, "read_token() is the only credential reader...") to add one sentence: "It returns the token, or None when an edge supplies the credential in transport; the host implementation never returns None."

4. In the header, after the "WHAT IT DOES GIVE" paragraph and before the first `import`, add:

```
# EDGE SEAM. This file is also importable. An edge that runs the guard somewhere else - the
# NanoClaw host service in docs/superpowers/specs/2026-09-08-shared-core-host-and-agent-design.md
# - replaces exactly six module names and nothing else: read_token (the credential, or None
# when the edge's transport carries it), build_opener (the transport: it installs its own with
# urllib.request.install_opener), confirm (how a person approves a write), check_provenance
# (what "installed correctly" means there), and the two paths CONFIG_PATH and DEFAULT_DIR.
# Every other property - host pinning, refusal before credential, the audit lines, evidence
# read-back - is shared and must not diverge. tools/replay-probe.py proves the host is unchanged.
```

5. `USER_AGENT = "canvas-api-guard/1.15.0"`, and in `test_canvas_api_guard.py` rename
   `test_the_version_is_1_14_0` to `test_the_version_is_1_15_0` and change its expected string
   to `"canvas-api-guard/1.15.0"`. This is the one existing assertion this plan changes; the
   Global Constraints name it.

- [ ] **Step 4: Run the tests to verify they pass, and that nothing else moved**

Run: `python3 -m unittest 2>&1 | tail -3`
Expected: all tests pass, count = previous count + 5. If `test_the_guard_keeps_exactly_one_credential_free_opener` or any pre-existing test fails, stop: the constraint "existing tests pass unchanged" has been violated; report which assertion and why rather than editing it.

Also run: `grep -c "urllib.request.urlopen(" canvas_api_guard.py` → `1`; `grep -c "urllib.request.build_opener(" canvas_api_guard.py` → `2` (inside `build_opener()`, and the attachment opener).

- [ ] **Step 5: Docs**

README.md, in the section that describes the guard (near "The two-profile design" or wherever the file is characterised as one reviewable file), add one paragraph:

> The guard is also importable. A host-side agent service (see the shared-core spec) replaces six module names, listed under "EDGE SEAM" in the file header, and nothing else: the credential read, the transport opener, the write confirmation, the provenance check, and two paths. `tools/replay-probe.py main` shows that a stock installation's audit records, output, exit codes and help are byte-identical before and after a change; it runs on every change to the guard.

docs/IT-REVIEW.md, in the controls section, add one bullet under the installation controls or a new "Edge seam" bullet:

> The API opener now disables environment proxies (`ProxyHandler({})`), as attachment downloads already did: the pinned host is reached directly or not at all. The importable edge seam is six named module attributes; the host path never branches on them, and the replay probe pins the stock audit format.

- [ ] **Step 6: Commit**

```bash
git add canvas_api_guard.py test_canvas_api_guard.py README.md docs/IT-REVIEW.md
git commit -m "feat(guard): name the edge seam in place; the API opener uses no environment proxy

build_opener() is the pinned transport (ProxyHandler({}) + RefuseRedirects), installed once at
import; an edge installs its own. read_token() may return None, meaning the edge's transport
carries the credential; the host never does. The header names the six replaceable names.
TestEdgeSeam proves each is looked up at call time and that the stock read line is unchanged.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ac/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

(Use the exact trailer from Global Constraints; the URL above must read `claude.ai`.)

---

### Task 2: The replay probe and the pinned audit format

**Files:** Create `tools/replay-probe.py`. Test `test_canvas_api_guard.py` (new class `TestAuditFormat` after `TestEdgeSeam`; one test in `TestInstallerPlan` or a new `TestTools` that checks the probe's syntax and that it runs against `HEAD`).

**Interfaces:**
- Consumes: the guard's `main(argv)`, `CONFIG_PATH`, `DEFAULT_LOG`, `read_token`, `_SOURCE` (the test seam the suite already resets).
- Produces: `tools/replay-probe.py BASE_COMMIT` exits 0 when the working tree matches BASE for a stock install, 1 with a diff otherwise.

- [ ] **Step 1: Write the failing audit-format test**

```python
class TestAuditFormat(GuardTestCase):
    """The stock audit record, key by key. IT has reviewed this format; a change here is a
    change to what every existing installation writes, and must be a deliberate one."""

    READ = ["bytes", "event", "ok", "path", "pid", "source", "status", "timestamp", "verb"]
    REQUEST = ["confirmation", "dry_run", "event", "kind", "path", "pid", "request_body",
               "source", "timestamp", "url", "verb"]
    EVIDENCE = ["changes", "confirmation", "event", "note", "path", "pid", "source", "status",
                "target", "timestamp", "verb", "verification"]
    REFUSAL = ["confirmation", "event", "kind", "path", "pid", "source", "timestamp", "verb"]

    def test_a_stock_read_write_dry_run_and_refusal_write_exactly_these_keys(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload={"id": 1})):
            self.run_main(["get", "courses/1"])
        responses = [FakeResponse(payload={"id": 1, "name": "A"}),
                     FakeResponse(payload={"id": 1, "name": "X"}),
                     FakeResponse(payload={"id": 1, "name": "X"})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            self.run_main(["put", "courses/1", "-d", '{"course": {"name": "X"}}', "--yes"])
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("dry run sent")):
            self.run_main(["put", "courses/1", "-d", '{"course": {"name": "X"}}', "--dry-run"])
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("refused write sent")):
            code, _ = self.run_main(["delete", "courses/1"])
        self.assertEqual(code, 2)
        keys = [(line["event"], sorted(line)) for line in self.log_lines()]
        self.assertEqual(keys, [
            ("read", self.READ),
            ("read", self.READ),                 # the write's pre-read
            ("request", self.REQUEST),
            ("response", self.READ),
            ("read", self.READ),                 # the write's read-back
            ("evidence", self.EVIDENCE),
            ("request", self.REQUEST),           # the dry run
            ("evidence", self.EVIDENCE),
            ("refusal", self.REFUSAL),
        ])
```

- [ ] **Step 2: Run it**

Run: `python3 -m unittest test_canvas_api_guard.TestAuditFormat -v`
Expected: PASS on the current tree (it pins today's format). If it fails, the observed key list is the truth: check the sequence against the Global Constraints table, correct the test's expected list only if the constraint table was wrong, and say so in the report.

- [ ] **Step 3: Create the probe**

`tools/replay-probe.py`:

```python
#!/usr/bin/env python3
"""Replay probe: is a stock installation of the guard byte-identical before and after?

    tools/replay-probe.py BASE_COMMIT        # compares BASE_COMMIT's guard with the working tree

Exports BASE_COMMIT with git archive into a temp dir, then runs the same seven scenarios
against both guards with urlopen and read_token replaced, the config exactly as install.sh
writes it, and diffs: audit records (timestamp and pid normalised), stdout, stderr, exit codes,
--help and --version. Exit 0 = identical, 1 = differs (the diff is printed), 2 = usage.
Nothing here touches the network, a credential store, or the installed guard.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from unittest import mock

CONFIG_TEXT = '{"host":"canvas.example.edu","profile":"level-1"}\n'   # install.sh's exact bytes
NORMALISE = ("timestamp", "pid")


class FakeResponse(object):
    def __init__(self, status=200, payload=None):
        self.status, self.headers = status, {}
        self._payload = json.dumps(payload if payload is not None else {}).encode("utf-8")

    def read(self):
        return self._payload

    def close(self):
        pass


class FakeStdout(io.StringIO):
    def isatty(self):
        return True


def load_guard(tree, tag):
    spec = importlib.util.spec_from_file_location("canvas_api_guard_" + tag,
                                                  os.path.join(tree, "canvas_api_guard.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(guard, argv, urlopen):
    guard._SOURCE = None
    out, err = FakeStdout(), io.StringIO()
    with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err), \
            mock.patch("sys.stdin", io.StringIO()), mock.patch("urllib.request.urlopen", urlopen):
        try:
            code = guard.main(argv)
        except SystemExit as exc:
            code = exc.code
    return {"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()}


def scenarios(guard):
    never = mock.Mock(side_effect=AssertionError("the network was touched"))
    course = lambda: FakeResponse(payload={"id": 1, "name": "Course One"})
    changed = lambda: FakeResponse(payload={"id": 1, "name": "X"})
    put = ["put", "courses/1", "-d", '{"course":{"name":"X"}}']
    return [
        ("help", ["--help"], never),
        ("version", ["--version"], never),
        ("get", ["get", "courses/1"], mock.Mock(return_value=course())),
        ("put_yes", put + ["--yes"], mock.Mock(side_effect=[course(), changed(), changed()])),
        ("put_dry_run", put + ["--dry-run"], never),
        ("get_json", ["get", "courses/1", "-o", "json"], mock.Mock(return_value=course())),
        ("refused_delete", ["delete", "courses/1"], never),
    ]


def probe(tree, tag):
    guard = load_guard(tree, tag)
    state = tempfile.mkdtemp(prefix="replay-probe-%s-" % tag)
    os.chmod(state, 0o700)
    log = os.path.join(state, "audit.jsonl")
    open(log, "w").close()
    os.chmod(log, 0o600)
    config = os.path.join(state, "config.json")
    with open(config, "w") as handle:
        handle.write(CONFIG_TEXT)
    guard.CONFIG_PATH, guard.DEFAULT_LOG, guard.read_token = config, log, (lambda: "tok-test")
    results = {name: run(guard, argv, urlopen) for name, argv, urlopen in scenarios(guard)}
    with open(log) as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    for record in records:
        for key in NORMALISE:
            record.pop(key, None)
    return {"results": results, "log": records}


def export(commit):
    tree = tempfile.mkdtemp(prefix="replay-probe-base-")
    archive = subprocess.run(["git", "archive", commit], stdout=subprocess.PIPE, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(tree)
    return tree


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    before, after = probe(export(argv[1]), "before"), probe(here, "after")
    text = [json.dumps(side, indent=1, sort_keys=True) for side in (before, after)]
    if text[0] == text[1]:
        print("replay probe: byte-identical to %s (%d audit lines, %d scenarios)"
              % (argv[1], len(after["log"]), len(after["results"])))
        return 0
    import difflib
    sys.stdout.writelines(difflib.unified_diff(text[0].splitlines(True), text[1].splitlines(True),
                                               "base " + argv[1], "working tree"))
    print("replay probe: DIFFERS from %s" % argv[1])
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

`chmod 755 tools/replay-probe.py`.

- [ ] **Step 4: Prove the probe discriminates, then that the tree is identical**

Run: `tools/replay-probe.py HEAD~1` (the commit before Task 1) → expected `byte-identical` (Task 1 changed no stock behaviour; the proxy handler is invisible with `urlopen` mocked, and that is documented).
Run: `tools/replay-probe.py f61027e` → expected `DIFFERS` with `token_source` and `approval_receipt` in the diff (that commit is the one the probe was built to catch; it is in history).

- [ ] **Step 5: A test that the probe runs**

Add to `test_canvas_api_guard.py`, in `TestInstallerPlan` (it already runs repository scripts):

```python
    def test_replay_probe_runs_and_reports_the_working_tree_identical_to_head(self):
        import subprocess
        proc = subprocess.run([os.path.join(self.ROOT, "tools", "replay-probe.py"), "HEAD"],
                              cwd=self.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("byte-identical", proc.stdout)
```

Note: this test compares the committed `HEAD` guard with the working-tree guard, so it is green whenever the guard's stock behaviour is committed; during development of a behaviour change it goes red, which is the point.

- [ ] **Step 6: Run the suite and commit**

Run: `python3 -m unittest 2>&1 | tail -2` → OK.

```bash
git add tools/replay-probe.py test_canvas_api_guard.py
git commit -m "test: pin the stock audit format; add tools/replay-probe.py

The probe exports a base commit and diffs a stock installation's audit records, output,
exit codes, help and version against the working tree with the network and the credential
store replaced. It reports f61027e as differing and the seam change as identical.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

---

### Task 3: The guard can prove a `resource[][field]` write

**Files:** Modify `canvas_api_guard.py` (`matches` at line 555, `USER_AGENT` at line 50). Test
`test_canvas_api_guard.py` (new `TestStructuredReadBack`).

**Interfaces:**
- Consumes: nothing.
- Produces: `combined_match(results) -> True|False|None`; `matches()` may now return `None`
  (`do_update`/`do_post` already test with `is False` / `is True`, so `None` is inert there).
  `USER_AGENT = "canvas-api-guard/1.15.0"`.

- [ ] **Step 1: Write the failing test** — append to `test_canvas_api_guard.py`, immediately before `class TestGuardHeader(unittest.TestCase):`

```python
class TestStructuredReadBack(GuardTestCase):
    """Canvas's resource[][field] write shapes (quiz answers, quiz_submissions) send a list or
    an object; the read-back holds the same shape. Comparing those as strings made every such
    write unprovable, so a correct write reported WRITE STATUS UNCERTAIN."""

    ANSWERS = [{"id": 1001, "text": "A", "weight": 100}, {"id": 1002, "text": "B", "weight": 0},
               {"id": 1003, "text": "C", "weight": 0}, {"id": 1004, "text": "D", "weight": 0}]

    def question(self, answers):
        return {"id": 789, "quiz_id": 5, "question_type": "multiple_choice_question",
                "points_possible": 2.0, "answers": answers}

    def regraded(self):
        return [dict(answer, weight=(100 if answer["id"] in (1003, 1004) else 0))
                for answer in self.ANSWERS]

    def test_an_answer_key_write_is_proved_answer_by_answer(self):
        after = self.question(self.regraded())
        body = {"question": {"answers": [{"id": a["id"], "text": a["text"], "weight": a["weight"]}
                                         for a in self.regraded()]}}
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResponse(payload=self.question(self.ANSWERS)),
                FakeResponse(payload=after), FakeResponse(payload=after)]):
            code, output = self.run_main(["put", "courses/12/quizzes/5/questions/789", "--yes",
                                          "-o", "json", "-d", json.dumps(body)])
        self.assertEqual(code, 0)
        evidence = json.loads(output)
        self.assertEqual(evidence["verification"], "passed")
        self.assertIs(evidence["changes"][0]["match"], True)

    def test_one_wrong_weight_still_disproves_the_whole_key(self):
        wrong = self.regraded()
        wrong[3] = dict(wrong[3], weight=0)
        body = {"question": {"answers": [{"id": a["id"], "weight": a["weight"]}
                                         for a in self.regraded()]}}
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResponse(payload=self.question(self.ANSWERS)),
                FakeResponse(payload=self.question(wrong)),
                FakeResponse(payload=self.question(wrong))]):
            code, output = self.run_main(["put", "courses/12/quizzes/5/questions/789", "--yes",
                                          "-o", "json", "-d", json.dumps(body)])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)

    def test_a_quiz_submission_score_write_is_proved_through_canvas_envelope(self):
        before = {"quiz_submissions": [{"id": 55, "user_id": 34, "attempt": 1, "score": 6.0,
                                        "workflow_state": "complete"}]}
        after = {"quiz_submissions": [dict(before["quiz_submissions"][0], score=8.0)]}
        body = {"quiz_submissions": [{"attempt": 1, "questions": {"789": {"score": 2.0}}}]}
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResponse(payload=before), FakeResponse(payload=after),
                FakeResponse(payload=after)]):
            code, output = self.run_main(["put", "courses/12/quizzes/5/submissions/55", "--yes",
                                          "-o", "json", "-d", json.dumps(body)])
        self.assertEqual(code, 0)
        evidence = json.loads(output)
        self.assertEqual(evidence["verification"], "passed")
        # attempt is echoed and proves the write reached the right attempt; the per-question
        # score is not a field of the submission object, so it stays unknown here and is read
        # back by Level 2 itself.
        self.assertIs(evidence["changes"][0]["match"], True)

    def test_the_wrong_attempt_read_back_is_uncertain(self):
        before = {"quiz_submissions": [{"id": 55, "attempt": 1, "score": 6.0}]}
        after = {"quiz_submissions": [{"id": 55, "attempt": 2, "score": 6.0}]}
        body = {"quiz_submissions": [{"attempt": 1, "questions": {"789": {"score": 2.0}}}]}
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResponse(payload=before), FakeResponse(payload=after),
                FakeResponse(payload=after)]):
            code, output = self.run_main(["put", "courses/12/quizzes/5/submissions/55", "--yes",
                                          "-o", "json", "-d", json.dumps(body)])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)

    def test_a_field_the_object_does_not_expose_still_proves_nothing(self):
        self.assertIsNone(guard.matches({"questions": {"789": {"score": 2.0}}}, {"id": 55}))
        self.assertIsNone(guard.matches([{"a": 1}], "not a list"))
```

(The version bump and the version-pin test change happened in Task 1; do not repeat them.)

- [ ] **Step 2: Run it to verify it fails** — `python3 -m unittest test_canvas_api_guard.TestStructuredReadBack test_canvas_api_guard.TestGuardHeader -v`
  Expect `AssertionError: 3 != 0` in `test_an_answer_key_write_is_proved_answer_by_answer` and in
  `test_a_quiz_submission_score_write_is_proved_through_canvas_envelope`,
  and `AssertionError: False is not None` in `test_a_field_the_object_does_not_expose_still_proves_nothing`.

- [ ] **Step 3: Implement** — in `canvas_api_guard.py`, insert `combined_match` immediately above
  `matches` and give `matches` its two structured branches (everything after them is untouched):

```python
def combined_match(results):
    """One verdict for a structured value: any disproved member disproves it; otherwise it is
    proved when at least one member was proved, and unknown when none was."""
    if any(result is False for result in results):
        return False
    return True if any(result is True for result in results) else None

def matches(requested, got):
    """Whether a read-back value proves the requested one: numbers within Canvas's rounding,
    letters case-insensitively, with posted_grade pass/fail read back as complete/incomplete.
    Canvas's resource[][field] write shapes (a quiz question's answers, a quiz_submissions
    envelope) send a list or an object where the read-back holds the same shape, so those are
    compared member by member: a key the read-back does not expose is unknown and disproves
    nothing, exactly as an unexposed top-level field is."""
    if isinstance(requested, dict):
        if not isinstance(got, dict):
            return None
        return combined_match([matches(requested[key], got[key])
                               for key in requested if key in got])
    if isinstance(requested, list):
        if not isinstance(got, list) or len(got) < len(requested):
            return None
        return combined_match([matches(requested[i], got[i]) for i in range(len(requested))])
    want, have = number_or_none(requested), number_or_none(got)
    if want is not None and have is not None:
        return abs(have - want) <= SCORE_TOLERANCE
    aliases = {"pass": "complete", "fail": "incomplete"}
    norm = lambda v: aliases.get(str(v).strip().lower(), str(v).strip().lower())
    return norm(got) == norm(requested)
```


- [ ] **Step 4: Run** — `python3 -m unittest 2>&1 | tail -3`
  Expect `OK` with the previous count plus five. Verified offline in a scratch copy against
  the 190-test tree: the change breaks none of them. Then run `tools/replay-probe.py HEAD~1`
  (from Task 2): expected `byte-identical`, since no stock scenario writes a structured value.

- [ ] **Step 5: Commit**

```
git status --porcelain --untracked-files=no    # only this task's files may be listed; stop otherwise
git add canvas_api_guard.py test_canvas_api_guard.py level2/canvas_api_operations.py test_canvas_api_operations.py level2/SKILL.md level2/README.md codex/canvas-api-guard.rules 2>/dev/null
git commit -m "fix: prove a Canvas resource[][field] write instead of refusing to

A quiz answer key and a quiz submission score are sent as a list or an
object, and the read-back holds the same shape. Comparing those as strings
made every such write report WRITE STATUS UNCERTAIN on a completely
successful write. They are now compared member by member, with an unexposed
key staying unknown, as an unexposed top-level field already was.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

---

### Task 4: The read side and the dry-run plan

**Files:** Modify `level2/canvas_api_operations.py` (new section after `bulk_grade_with_rubric`;
`OPERATIONS`; `parser()`; `USER_AGENT`). Test `test_canvas_api_operations.py`.

**Interfaces:**
- Consumes: `guard_get`, `all_items`, `exact_object`, `canvas_id`, `number`, `definition_file`,
  `student_identities`, `SCORE_TOLERANCE`, `OperationError`.
- Produces: `QUIZ_REGRADE_LIMIT = 100`, `CLASSIC_QUESTION_TYPES`, `ANSWER_FIELDS`,
  `regrade_definition(value) -> (quiz_id, question_id, [answer_id])`,
  `regrade_answer_key(question, answer_ids) -> [answer]`,
  `quiz_submissions(course_id, quiz_id) -> [submission]`,
  `attempt_row(course_id, assignment_id, submission, question, answer_ids) -> dict`,
  `regrade_plan(args) -> (quiz_id, question_id, answer_ids, question, rows, changed)`.

- [ ] **Step 1: Write the failing test** — append to `test_canvas_api_operations.py`, immediately before `class TestGuardWriteContract(GuardTestCase):`

```python
QUESTION = {"id": 789, "quiz_id": 5, "question_type": "multiple_choice_question",
            "points_possible": 2.0,
            "answers": [{"id": 1001, "text": "A", "weight": 100},
                        {"id": 1002, "text": "B", "weight": 0},
                        {"id": 1003, "text": "C", "weight": 0},
                        {"id": 1004, "text": "D", "weight": 0}]}
QUIZ = {"id": 5, "title": "Unit 2 Quiz", "quiz_type": "assignment", "assignment_id": 77,
        "points_possible": 10.0}
SUBMISSIONS = {"quiz_submissions": [
    {"id": 55, "user_id": 34, "attempt": 1, "score": 6.0, "workflow_state": "complete"},
    {"id": 56, "user_id": 35, "attempt": 2, "score": 8.0, "workflow_state": "complete"},
    {"id": 57, "user_id": 36, "attempt": 1, "score": 4.0, "workflow_state": "untaken"}]}
HISTORY = {
    "34": {"id": 900, "user_id": 34, "attempt": 1, "score": 6.0, "submission_history": [
        {"attempt": 1, "score": 6.0, "submission_data": [
            {"question_id": 789, "answer_id": 1003, "correct": False, "points": 0.0},
            {"question_id": 790, "answer_id": 2001, "correct": True, "points": 6.0}]}]},
    "35": {"id": 901, "user_id": 35, "attempt": 2, "score": 8.0, "submission_history": [
        {"attempt": 1, "score": 5.0, "submission_data": [
            {"question_id": 789, "answer_id": 1001, "correct": True, "points": 2.0}]},
        {"attempt": 2, "score": 8.0, "submission_data": [
            {"question_id": 789, "answer_id": 1001, "correct": True, "points": 2.0}]}]}}


class QuizRegradeFixtures(object):
    """Shared fixtures for the regrade tests. A plain mixin, not a TestCase: subclassing a
    TestCase would rerun every inherited test under the child's name."""

    def args(self, dry_run=True):
        args = Args()
        args.definition, args.dry_run, args.yes = "unused", dry_run, not dry_run
        return args

    def reads(self, path):
        if path.startswith("courses/12/quizzes/5/questions/789"):
            return {"object": QUESTION}
        if path == "courses/12/quizzes/5":
            return {"object": QUIZ}
        if path.startswith("courses/12/quizzes/5/submissions?page=1"):
            return {"object": SUBMISSIONS}
        if path.startswith("courses/12/quizzes/5/submissions?page="):
            return {"object": {"quiz_submissions": []}}
        if path.startswith("courses/12/assignments/77/submissions/"):
            return {"object": HISTORY[path.split("/")[4].split("?")[0]]}
        if path == "courses/12":
            return {"object": {"id": 12}}
        raise AssertionError("unexpected read %r" % path)

    def plan(self, definition=None):
        definition = definition or {"quiz_id": 5, "question_id": 789,
                                    "correct_answer_ids": [1003, 1004]}
        names = [{"id": 34, "name": "Jordan Lee", "sortable_name": "Lee, Jordan"},
                 {"id": 35, "name": "Casey Kim", "sortable_name": "Kim, Casey"}]
        with mock.patch.object(operations, "definition_file", return_value=definition), \
                mock.patch.object(operations, "guard_get", side_effect=self.reads), \
                mock.patch.object(operations, "all_items", return_value=names):
            return operations.regrade_plan(self.args())



class TestQuizRegradePlan(QuizRegradeFixtures, unittest.TestCase):
    """The read side: what would change, before anything is sent."""

    def test_the_plan_names_every_attempt_and_both_directions_of_the_delta(self):
        _, _, _, question, rows, changed = self.plan()
        self.assertEqual(question["id"], 789)
        # the untaken submission is never a candidate
        self.assertEqual([row["user_id"] for row in rows], [34, 35])
        gained, lost = rows[0], rows[1]
        self.assertEqual((gained["name"], gained["attempt"], gained["old_points"],
                          gained["new_points"], gained["delta"], gained["expected_score"]),
                         ("Jordan Lee", 1, 0.0, 2.0, 2.0, 8.0))
        # C and D are now correct, so A is not: this student loses the points
        self.assertEqual((lost["name"], lost["attempt"], lost["old_points"],
                          lost["new_points"], lost["delta"], lost["expected_score"]),
                         ("Casey Kim", 2, 2.0, 0.0, -2.0, 6.0))
        self.assertEqual(len(changed), 2)

    def test_the_new_answer_key_keeps_every_answer_and_only_changes_the_weights(self):
        answers = operations.regrade_answer_key(QUESTION, ["1003", "1004"])
        self.assertEqual(answers, [{"id": 1001, "text": "A", "weight": 0},
                                   {"id": 1002, "text": "B", "weight": 0},
                                   {"id": 1003, "text": "C", "weight": 100},
                                   {"id": 1004, "text": "D", "weight": 100}])

    def test_an_unsupported_question_type_is_refused_before_anything_is_read_back(self):
        with self.assertRaises(operations.OperationError) as caught:
            operations.regrade_answer_key(dict(QUESTION, question_type="essay_question"),
                                          ["1003"])
        self.assertEqual(str(caught.exception),
                         "regrade supports multiple_choice_question and true_false_question; "
                         "question 789 is essay_question")

    def test_an_answer_that_is_not_on_the_question_is_refused(self):
        with self.assertRaises(operations.OperationError) as caught:
            operations.regrade_answer_key(QUESTION, ["9999"])
        self.assertEqual(str(caught.exception),
                         "answer 9999 is not an answer of question 789 "
                         "(available: 1001, 1002, 1003, 1004)")

    def test_a_quiz_that_is_not_a_graded_classic_quiz_is_refused(self):
        def reads(path):
            return {"object": dict(QUIZ, quiz_type="practice_quiz", assignment_id=None)}
        with mock.patch.object(operations, "definition_file",
                               return_value={"quiz_id": 5, "question_id": 789,
                                             "correct_answer_ids": [1003]}), \
                mock.patch.object(operations, "guard_get", side_effect=reads):
            with self.assertRaises(operations.OperationError) as caught:
                operations.regrade_plan(self.args())
        self.assertIn("only a graded classic quiz", str(caught.exception))
        self.assertIn("New Quizzes", str(caught.exception))

    def test_the_definition_takes_ids_only_and_refuses_anything_else(self):
        for bad in ({"quiz_id": 5, "question_id": 789, "correct_answer_ids": ["C"]},
                    {"quiz_id": 5, "question_id": 789, "correct_answer_ids": []},
                    {"quiz_id": 5, "question_id": 789, "correct_answer_ids": [1003, 1003]},
                    {"quiz_id": 5, "question_id": 789, "correct_answer_ids": [1003],
                     "comment": "hi"}):
            with self.assertRaises(operations.OperationError):
                operations.regrade_definition(bad)

    def test_the_submission_list_envelope_is_paged_explicitly(self):
        pages = []

        def reads(path):
            pages.append(path)
            return self.reads(path)

        with mock.patch.object(operations, "guard_get", side_effect=reads):
            found = operations.quiz_submissions("12", "5")
        self.assertEqual([row["id"] for row in found], [55, 56, 57])
        self.assertEqual(pages, ["courses/12/quizzes/5/submissions?page=1&per_page=100",
                                 "courses/12/quizzes/5/submissions?page=2&per_page=100"])

    def test_more_attempts_than_the_cap_is_refused_before_any_write(self):
        many = {"quiz_submissions": [
            dict(SUBMISSIONS["quiz_submissions"][0], id=100 + n, user_id=100 + n)
            for n in range(operations.QUIZ_REGRADE_LIMIT + 1)]}
        history = {"attempt": 1, "score": 6.0, "submission_history": [
            {"attempt": 1, "score": 6.0, "submission_data": [
                {"question_id": 789, "answer_id": 1003, "points": 0.0}]}]}

        def reads(path):
            if path.startswith("courses/12/quizzes/5/submissions?page=1"):
                return {"object": many}
            if path.startswith("courses/12/assignments/77/submissions/"):
                return {"object": history}
            return self.reads(path)

        with mock.patch.object(operations, "definition_file",
                               return_value={"quiz_id": 5, "question_id": 789,
                                             "correct_answer_ids": [1003, 1004]}), \
                mock.patch.object(operations, "guard_get", side_effect=reads), \
                mock.patch.object(operations, "guard_write") as write:
            with self.assertRaises(operations.OperationError) as caught:
                operations.regrade_plan(self.args())
        self.assertIn("refuses more than 100 attempts", str(caught.exception))
        write.assert_not_called()
```

- [ ] **Step 2: Run it to verify it fails** — `python3 -m unittest test_canvas_api_operations.TestQuizRegradePlan -v`
  Expect `AttributeError: module 'canvas_api_operations' has no attribute 'regrade_plan'` (and the
  same for `regrade_answer_key`, `regrade_definition`, `quiz_submissions`, `QUIZ_REGRADE_LIMIT`).

- [ ] **Step 3: Implement** — add `import time` beside `import sys`, bump
  `USER_AGENT = "canvas-api-operations/0.14.0"`, and append this section after
  `bulk_grade_with_rubric`:

```python
QUIZ_REGRADE_LIMIT = 100       # attempts in one reviewed batch: one section, refused whole
QUIZ_PAGE_CAP = 10             # 100 per page; past this the batch cap has already refused
CLASSIC_QUESTION_TYPES = ("multiple_choice_question", "true_false_question")
# The update REPLACES the answer set, so every answer is sent back as Canvas returned it with
# only its weight changed. These are the fields canvas-cli round-trips (internal/api
# QuizAnswer); anything else Canvas returns is not sent back.
ANSWER_FIELDS = ("id", "text", "html", "comments", "comments_html")


def regrade_definition(value):
    """Answer IDs only: a Canvas answer's identity is its ID, its text is instructor HTML that
    is not unique and that this write has to round-trip untouched."""
    definition = exact_object(value, ("quiz_id", "question_id", "correct_answer_ids"), ())
    ids = definition["correct_answer_ids"]
    if not isinstance(ids, list) or not ids:
        raise OperationError("correct_answer_ids must be a non-empty array of Canvas answer IDs")
    answer_ids = [canvas_id(str(answer_id), "answer ID") for answer_id in ids]
    if len(set(answer_ids)) != len(answer_ids):
        raise OperationError("correct_answer_ids contains a duplicate answer ID")
    return (canvas_id(str(definition["quiz_id"]), "quiz ID"),
            canvas_id(str(definition["question_id"]), "question ID"), answer_ids)


def regrade_answer_key(question, answer_ids):
    """Canvas encodes correctness as weight: 100 correct, 0 wrong. Every answer not listed
    drops to 0, so a student who picked the old answer loses those points - the plan shows it."""
    if question.get("question_type") not in CLASSIC_QUESTION_TYPES:
        raise OperationError("regrade supports multiple_choice_question and true_false_question; "
                             "question %s is %s" % (question.get("id"),
                                                    question.get("question_type")))
    available = [str(answer.get("id")) for answer in question.get("answers") or []]
    missing = [answer_id for answer_id in answer_ids if answer_id not in available]
    if missing:
        raise OperationError("answer %s is not an answer of question %s (available: %s)"
                             % (", ".join(missing), question.get("id"), ", ".join(available)))
    answers = []
    for answer in question["answers"]:
        kept = dict((field, answer[field]) for field in ANSWER_FIELDS if field in answer)
        kept["weight"] = 100 if str(answer.get("id")) in answer_ids else 0
        answers.append(kept)
    return answers


def quiz_submissions(course_id, quiz_id):
    """Canvas answers this list in a {"quiz_submissions": [...]} envelope, not a JSON array, so
    API Only reports one object with no rel="next" and the pages are walked here. A short page
    is not the end - an admin can cap per_page below the request - but a page that adds no new
    submission is."""
    found, seen = [], set()
    for page in range(1, QUIZ_PAGE_CAP + 1):
        response = guard_get("courses/%s/quizzes/%s/submissions?page=%d&per_page=100"
                             % (course_id, quiz_id, page))
        rows = (response.get("object") or {}).get("quiz_submissions")
        if not isinstance(rows, list):
            raise OperationError("Canvas did not return a quiz_submissions list for quiz %s"
                                 % quiz_id)
        added = [row for row in rows if str(row.get("id")) not in seen]
        seen.update(str(row.get("id")) for row in added)
        found.extend(added)
        if not added:
            return found
    raise OperationError("quiz %s lists more submission pages than this operation reads" % quiz_id)


def attempt_row(course_id, assignment_id, submission, question, answer_ids):
    """One attempt's before/after, from the assignment submission's history - the per-question
    record a grader can see. Only answer_id and points are trusted: Canvas does not recompute
    submission_data's "correct" flag when an answer key changes (canvas-cli observed correct:
    true with points 0 after a regrade), so correctness is always answer_id against the key."""
    row = {"submission_id": submission.get("id"), "user_id": submission.get("user_id"),
           "attempt": submission.get("attempt"), "old_score": number(submission.get("score")),
           "selected_answer_id": None, "old_points": None, "new_points": None, "delta": 0}
    history = guard_get("courses/%s/assignments/%s/submissions/%s?include[]=submission_history"
                        % (course_id, assignment_id, submission.get("user_id"))).get("object") or {}
    entry = next((item for item in history.get("submission_history") or []
                  if item.get("attempt") == row["attempt"] and item.get("submission_data")), None)
    answered = next((item for item in (entry or {}).get("submission_data") or []
                     if str(item.get("question_id")) == str(question.get("id"))), None)
    if answered is None or answered.get("answer_id") in (None, ""):
        row["skipped"] = ("no graded answer record for attempt %s" % row["attempt"]
                          if entry is None else "the student did not answer this question")
        return row
    row["old_score"] = number(entry.get("score"))
    row["selected_answer_id"] = str(answered["answer_id"])
    row["old_points"] = number(answered.get("points"))
    row["new_points"] = (number(question.get("points_possible"))
                         if row["selected_answer_id"] in answer_ids else 0.0)
    row["delta"] = row["new_points"] - row["old_points"]
    row["expected_score"] = row["old_score"] + row["delta"]
    return row


def regrade_plan(args):
    """Read everything the regrade depends on and work out, per attempt, what would change.
    Nothing is written here, and the cap refuses the whole batch rather than part of a class."""
    quiz_id, question_id, answer_ids = regrade_definition(definition_file(args.definition))
    quiz = guard_get("courses/%s/quizzes/%s" % (args.course_id, quiz_id)).get("object") or {}
    if quiz.get("quiz_type") != "assignment" or not quiz.get("assignment_id"):
        raise OperationError("quiz %s is quiz_type %s with assignment_id %s; only a graded "
                             "classic quiz can be regraded, and a New Quizzes quiz is not in "
                             "this API at all" % (quiz_id, quiz.get("quiz_type"),
                                                  quiz.get("assignment_id")))
    question = guard_get("courses/%s/quizzes/%s/questions/%s"
                         % (args.course_id, quiz_id, question_id)).get("object") or {}
    regrade_answer_key(question, answer_ids)        # refuse an unsupported question first
    rows = [attempt_row(args.course_id, quiz["assignment_id"], submission, question, answer_ids)
            for submission in quiz_submissions(args.course_id, quiz_id)
            if submission.get("workflow_state") == "complete"]
    changed = [row for row in rows if abs(row["delta"]) > SCORE_TOLERANCE]
    if len(changed) > QUIZ_REGRADE_LIMIT:
        raise OperationError("regrade refuses more than %s attempts in one reviewed batch; %s "
                             "attempts would change" % (QUIZ_REGRADE_LIMIT, len(changed)))
    identities = student_identities(args.course_id, [row["user_id"] for row in rows])
    for row in rows:
        row.update(identities.get(str(row["user_id"]), {}))
    return quiz_id, question_id, answer_ids, question, rows, changed
```

- [ ] **Step 4: Run** — `python3 -m unittest test_canvas_api_operations -v 2>&1 | tail -3`
  Expect `OK`.

- [ ] **Step 5: Commit**

```
git status --porcelain --untracked-files=no    # only this task's files may be listed; stop otherwise
git add canvas_api_guard.py test_canvas_api_guard.py level2/canvas_api_operations.py test_canvas_api_operations.py level2/SKILL.md level2/README.md codex/canvas-api-guard.rules 2>/dev/null
git commit -m "feat: the read side of a quiz question regrade

Reads the quiz, the question and every attempt, and works out per attempt
what the new answer key does to that attempt's score. Answers are named by
ID; an answer not listed drops to weight 0, which the plan shows as a
negative delta.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

---

### Task 5: The writes, the per-attempt read-back and the uncertainty

**Files:** Modify `level2/canvas_api_operations.py` (same section; `OPERATIONS`; `parser()`).
Test `test_canvas_api_operations.py`.

**Interfaces:**
- Consumes: Task 3's structured `matches`/`combined_match` (without it the answer-key write reads back as uncertain); Task 4's `regrade_plan`; `guard_write`, `write_plan`, `operation_phase`,
  `GuardUncertain`, `SCORE_TOLERANCE`.
- Produces: `READ_BACK_READS = 3`, `READ_BACK_DELAY = 1.0`,
  `verify_answer_key(course_id, quiz_id, question_id, answer_ids)`,
  `write_attempt_score(args, quiz_id, question_id, row)`,
  `read_back_attempt(path, row)`, `regrade_quiz_question(args)`;
  `OPERATIONS["regrade-quiz-question"]`; the `regrade-quiz-question` subparser.

- [ ] **Step 1: Write the failing test** — append to `test_canvas_api_operations.py` after `TestQuizRegradePlan`

```python
class TestQuizRegradeWrites(QuizRegradeFixtures, unittest.TestCase):
    """Every write goes through API Only one at a time, and the attempt score is read back
    here: it is not a field API Only can prove on the submission object."""

    def run_regrade(self, dry_run=False, scores=(8.0, 6.0), key=(1003, 1004)):
        """Returns (guard_get mock, guard_write mock). scores are what each read-back reports."""
        after = dict(QUESTION, answers=[dict(a, weight=(100 if a["id"] in key else 0))
                                        for a in QUESTION["answers"]])
        read_backs = {"55": scores[0], "56": scores[1]}

        def reads(path):
            if "?attempt=" in path:
                submission_id = path.split("/submissions/")[1].split("?")[0]
                return {"object": {"quiz_submissions": [
                    {"id": int(submission_id), "attempt": int(path.split("attempt=")[1]),
                     "score": read_backs[submission_id]}]}}
            if path.startswith("courses/12/quizzes/5/questions/789") and questions_written:
                return {"object": after}
            return self.reads(path)

        questions_written = []

        def write(verb, path, body, phase, extra=None):
            if "/questions/" in path:
                questions_written.append(body)
            return {"verification": "passed"}

        names = [{"id": 34, "name": "Jordan Lee"}, {"id": 35, "name": "Casey Kim"}]
        with mock.patch.object(operations, "definition_file",
                               return_value={"quiz_id": 5, "question_id": 789,
                                             "correct_answer_ids": list(key)}), \
                mock.patch.object(operations, "guard_get", side_effect=reads) as get, \
                mock.patch.object(operations, "all_items", return_value=names), \
                mock.patch.object(operations, "time") as clock, \
                mock.patch.object(operations, "guard_write", side_effect=write) as written, \
                mock.patch("sys.stdout", io.StringIO()) as out:
            operations.regrade_quiz_question(self.args(dry_run=dry_run))
        self.clock, self.out = clock, out.getvalue()
        return get, written

    def test_the_answer_key_is_written_once_and_then_each_attempt_individually(self):
        _, written = self.run_regrade()
        paths = [call[0][1] for call in written.call_args_list]
        self.assertEqual(paths, ["courses/12/quizzes/5/questions/789",
                                 "courses/12/quizzes/5/submissions/55",
                                 "courses/12/quizzes/5/submissions/56"])
        self.assertEqual(written.call_args_list[0][0][2], {"question": {"answers": [
            {"id": 1001, "text": "A", "weight": 0}, {"id": 1002, "text": "B", "weight": 0},
            {"id": 1003, "text": "C", "weight": 100}, {"id": 1004, "text": "D", "weight": 100}]}})
        # no fudge_points and no comment: canvas-cli's regrade sends neither
        self.assertEqual(written.call_args_list[1][0][2],
                         {"quiz_submissions": [{"attempt": 1,
                                                "questions": {"789": {"score": 2.0}}}]})
        self.assertEqual(written.call_args_list[2][0][2],
                         {"quiz_submissions": [{"attempt": 2,
                                                "questions": {"789": {"score": 0.0}}}]})
        self.assertEqual([call[0][3] for call in written.call_args_list], ["yes"] * 3)

    def test_each_attempt_is_read_back_at_its_own_attempt_number(self):
        get, _ = self.run_regrade()
        read_backs = [call[0][0] for call in get.call_args_list if "?attempt=" in call[0][0]]
        self.assertEqual(read_backs, ["courses/12/quizzes/5/submissions/55?attempt=1",
                                      "courses/12/quizzes/5/submissions/56?attempt=2"])
        self.assertIn('"verified": true', self.out)

    def test_a_score_that_does_not_read_back_is_uncertain_and_stops_the_batch(self):
        with self.assertRaises(operations.GuardUncertain) as caught:
            self.run_regrade(scores=(6.0, 6.0))
        self.assertEqual(str(caught.exception),
                         "WRITE STATUS UNCERTAIN: submission 55 attempt 1 read back score 6.0, "
                         "expected 8.0")
        # Canvas can lag, so the read is retried a bounded number of times before that is said
        self.assertEqual(self.clock.sleep.call_count, operations.READ_BACK_READS - 1)

    def test_an_answer_key_that_does_not_read_back_stops_before_any_attempt_is_written(self):
        with self.assertRaises(operations.GuardUncertain) as caught:
            self.run_regrade(key=(1003,))       # the fixture reads back 1003 and 1004
        self.assertIn("WRITE STATUS UNCERTAIN", str(caught.exception))
        self.assertIn("question 789 reports correct answer(s) 1003, 1004, not 1003",
                      str(caught.exception))

    def test_a_dry_run_writes_nothing_and_reads_nothing_back(self):
        get, written = self.run_regrade(dry_run=True)
        self.assertEqual([call[0][3] for call in written.call_args_list], ["dry-run"] * 3)
        self.assertEqual([call[0][0] for call in get.call_args_list
                          if "?attempt=" in call[0][0]], [])
        self.assertIn('"phase": "dry-run"', self.out)
        self.assertIn('"attempts_written": 0', self.out)

    def test_a_refusal_after_the_first_written_attempt_becomes_uncertain(self):
        calls = []

        def write(verb, path, body, phase, extra=None):
            calls.append(path)
            if len(calls) == 3:
                raise operations.OperationError("Canvas rejected the attempt")
            return {"verification": "passed"}

        with mock.patch.object(operations, "regrade_plan", return_value=(
                "5", "789", ["1003"], QUESTION,
                [], [{"submission_id": 55, "attempt": 1, "new_points": 2.0, "expected_score": 8.0,
                      "user_id": 34, "delta": 2.0},
                     {"submission_id": 56, "attempt": 2, "new_points": 0.0, "expected_score": 6.0,
                      "user_id": 35, "delta": -2.0}])), \
                mock.patch.object(operations, "verify_answer_key"), \
                mock.patch.object(operations, "read_back_attempt"), \
                mock.patch.object(operations, "guard_write", side_effect=write), \
                mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(operations.GuardUncertain) as caught:
                operations.regrade_quiz_question(self.args(dry_run=False))
        self.assertIn("stopped after 1 of 2 attempts", str(caught.exception))
        self.assertIn("are not retried", str(caught.exception))

    def test_the_operation_is_registered_and_takes_only_the_reviewed_write_flags(self):
        self.assertIs(operations.OPERATIONS["regrade-quiz-question"],
                      operations.regrade_quiz_question)
        parsed = operations.parser().parse_args(
            ["regrade-quiz-question", "--course-id", "12", "--definition", "r.json", "--dry-run"])
        self.assertTrue(parsed.dry_run)
        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):        # a phase is required, as for every write
                operations.parser().parse_args(
                    ["regrade-quiz-question", "--course-id", "12", "--definition", "r.json"])
```

- [ ] **Step 2: Run it to verify it fails** — `python3 -m unittest test_canvas_api_operations.TestQuizRegradeWrites -v`
  Expect `AttributeError: module 'canvas_api_operations' has no attribute 'regrade_quiz_question'`
  and `KeyError: 'regrade-quiz-question'`.

- [ ] **Step 3: Implement** — append to the same section, then register the operation:

```python
READ_BACK_READS = 3            # Canvas applies a quiz score asynchronously (canvas-cli, live)
READ_BACK_DELAY = 1.0


def verify_answer_key(course_id, quiz_id, question_id, answer_ids):
    """API Only proves the weights it sent, answer by answer. This checks the resulting KEY -
    the set of answers Canvas now treats as correct - so neither the order Canvas returns
    answers in nor an answer this write did not name can hide a wrong outcome."""
    question = guard_get("courses/%s/quizzes/%s/questions/%s"
                         % (course_id, quiz_id, question_id)).get("object") or {}
    correct = sorted(str(answer.get("id")) for answer in question.get("answers") or []
                     if number(answer.get("weight")) == 100)
    if correct != sorted(answer_ids):
        raise GuardUncertain("WRITE STATUS UNCERTAIN: question %s reports correct answer(s) %s, "
                             "not %s" % (question_id, ", ".join(correct) or "none",
                                         ", ".join(answer_ids)))


def read_back_attempt(path, row):
    """The attempt's own score, at ?attempt=N: the assignment submission's history lags this
    write and must not be used. Canvas can still return the previous value on an immediate
    read, so the read is repeated a bounded number of times before it is a mismatch."""
    for read in range(READ_BACK_READS):
        if read:
            time.sleep(READ_BACK_DELAY)
        found = (((guard_get("%s?attempt=%s" % (path, row["attempt"])).get("object") or {})
                  .get("quiz_submissions") or [{}])[0])
        row["new_score"] = number(found.get("score"))
        if abs(row["new_score"] - row["expected_score"]) <= SCORE_TOLERANCE:
            row["verified"] = True
            return
    raise GuardUncertain("WRITE STATUS UNCERTAIN: submission %s attempt %s read back score %s, "
                         "expected %s" % (row["submission_id"], row["attempt"],
                                          row["new_score"], row["expected_score"]))


def write_attempt_score(args, quiz_id, question_id, row):
    """One attempt's per-question score. canvas-cli sends attempt and questions[qid][score] and
    nothing else - no fudge_points, no comment - so neither is sent here."""
    path = "courses/%s/quizzes/%s/submissions/%s" % (args.course_id, quiz_id,
                                                     row["submission_id"])
    body = {"quiz_submissions": [{"attempt": row["attempt"],
                                  "questions": {str(question_id): {"score": row["new_points"]}}}]}
    guard_write("put", path, body, operation_phase(args))
    if operation_phase(args) != "dry-run":
        read_back_attempt(path, row)


def regrade_quiz_question(args):
    """Rewrite one classic-quiz question's answer key and rescore every completed attempt of
    that question: the answer key first, so a failure there touches no score, then one audited
    write per attempt, each read back at its own attempt number."""
    quiz_id, question_id, answer_ids, question, rows, changed = regrade_plan(args)
    print(json.dumps({"operation": "regrade-quiz-question", "phase": operation_phase(args),
                      "course_id": args.course_id, "quiz_id": quiz_id,
                      "question_id": question_id, "question_type": question.get("question_type"),
                      "points_possible": number(question.get("points_possible")),
                      "correct_answer_ids": answer_ids, "attempts_considered": len(rows),
                      "attempts_changed": len(changed), "rows": rows,
                      "warning": "every answer not listed is now worth 0; a student who picked "
                                 "one of those loses the points, shown as a negative delta"},
                     indent=2, sort_keys=True))
    path = "courses/%s/quizzes/%s/questions/%s" % (args.course_id, quiz_id, question_id)
    body = {"question": {"answers": regrade_answer_key(question, answer_ids)}}
    write_plan("regrade-quiz-question", args, path, body)
    guard_write("put", path, body, operation_phase(args))
    written = []
    if operation_phase(args) != "dry-run":
        verify_answer_key(args.course_id, quiz_id, question_id, answer_ids)
    try:
        for row in changed:
            write_attempt_score(args, quiz_id, question_id, row)
            written.append(row["submission_id"])
    except GuardUncertain:
        raise
    except OperationError as err:
        if not written or operation_phase(args) == "dry-run":
            raise                 # nothing was written, so this is an ordinary refusal
        raise GuardUncertain("regrade stopped after %d of %d attempts; the scores already "
                             "written stand and are not retried: %s"
                             % (len(written), len(changed), err))
    print(json.dumps({"operation": "regrade-quiz-question", "phase": operation_phase(args),
                      "attempts_written": len(written), "attempts_changed": len(changed),
                      "rows": changed}, indent=2, sort_keys=True))
```

  Register it: add `"regrade-quiz-question": regrade_quiz_question,` to `OPERATIONS`, and in
  `parser()` extend the existing loop that builds the reviewed-write subparsers — the operation
  needs only `--course-id`, `--definition` and a phase, so one line does it:

```python
    subs.add_parser("regrade-quiz-question", parents=[write])
```

- [ ] **Step 4: Run** — `python3 -m unittest 2>&1 | tail -3`
  Expect `OK` with the previous count plus this task's new tests (Tasks 1, 2, 3 and 4 added 5, 2, 5 and 8). Then check the
  program directly: `python3 level2/canvas_api_operations.py --help` lists seven operations and
  `--version` prints `canvas-api-operations/0.14.0`.

- [ ] **Step 5: Commit**

```
git status --porcelain --untracked-files=no    # only this task's files may be listed; stop otherwise
git add canvas_api_guard.py test_canvas_api_guard.py level2/canvas_api_operations.py test_canvas_api_operations.py level2/SKILL.md level2/README.md codex/canvas-api-guard.rules 2>/dev/null
git commit -m "feat: regrade one quiz question's answer key across a class

The answer key is written first and its resulting correct-answer set is read
back, so a failure there never touches a score. Then one audited write per
attempt, each read back at ?attempt=N with a bounded retry for Canvas's
propagation lag. The first attempt that cannot be proved stops the batch and
exits 3; nothing is retried.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

---

### Task 6: Skill, README, rules entry and their coverage tests

**Files:** Modify `codex/canvas-api-guard.rules` (`OPERATION_PROMPTS`, its `match` list),
`level2/SKILL.md` (Writes section), `level2/README.md` (operation table and the count).
The coverage tests already derive from the parsers, so no new test is needed — they fail first.

**Interfaces:**
- Consumes: Task 5's subparser name.
- Produces: no code. `TestRulesCoverage`, `TestCodexRules` and `TestSkillDocuments` pass again.

- [ ] **Step 1: Run the existing tests to verify they fail** — `python3 -m unittest test_canvas_api_guard.TestRulesCoverage test_canvas_api_guard.TestSkillDocuments -v`
  Expect, from `test_every_level_2_operation_is_classified_exactly_once`, `AssertionError: Lists
  differ: [...] != [...]` with `'regrade-quiz-question'` missing from the rules; from
  `test_only_the_two_read_commands_are_allowed_without_a_prompt`, `AssertionError:
  'regrade-quiz-question' not found in [...]`; and from
  `test_the_level_2_skill_documents_every_operation_and_invents_none`, `an operation is
  undocumented`. (With Codex installed, `TestCodexRules.test_the_matrix` fails too.)

- [ ] **Step 2: Implement** — three edits.

  2a. `codex/canvas-api-guard.rules`:

```python
OPERATION_PROMPTS = ["prepare-submission-review", "download-assignment-submissions",
                     "create-rubric", "grade-with-rubric", "bulk-grade-with-rubric",
                     "regrade-quiz-question"]
```

  and add one line to that rule's `match` list:

```python
             "/usr/local/libexec/canvas_api_operations.py regrade-quiz-question --course-id 1 --definition regrade.json --yes",
```

  2b. `level2/SKILL.md` — one command line in the Writes block (it must parse against the real
  parser; `TestSkillDocuments` checks that):

```sh
/usr/local/libexec/canvas_api_operations.py regrade-quiz-question --course-id 123 --definition regrade.json --dry-run
```

  and one bullet after `bulk-grade-with-rubric`:

> - `regrade-quiz-question` rewrites one classic multiple-choice or true/false question's answer
>   key and rescores every completed attempt of that question. It refuses anything that is not a
>   graded classic quiz (a New Quizzes quiz is not in this API at all) and any other question
>   type. The definition is `{"quiz_id": N, "question_id": N, "correct_answer_ids": [N, ...]}`;
>   IDs only, because answer text is instructor HTML this write has to round-trip untouched.
>   **Every answer not listed becomes worth 0**, so a student who picked the previously correct
>   answer loses those points - the dry run shows each attempt's old points, new points and
>   delta, negative ones included, and the instructor approves that table. Up to 100 attempts,
>   refused whole above that; the answer key is written and read back first, then each attempt
>   is its own audited write, read back at its own attempt number.

  2c. `level2/README.md` — add the row and change "six" if the count is stated:

```
| `regrade-quiz-question` | rewrites a classic quiz question's answer key and rescores every completed attempt of that question: one write for the key, then one audited, individually read-back write per attempt, with the attempt's score read at ?attempt=N because the assignment submission's history lags it |
```

- [ ] **Step 3: Run** — `python3 -m unittest 2>&1 | tail -3` → `OK`, same count as after Task 5 (this task adds no tests of its own beyond the coverage tests already there; if the count moved, say why). With Codex
  installed also confirm the real matrix: `codex execpolicy check --rules codex/canvas-api-guard.rules -- /usr/local/libexec/canvas_api_operations.py regrade-quiz-question --course-id 1 --definition r.json --yes`
  prints `"decision": "prompt"`.

- [ ] **Step 4: Commit**

```
git status --porcelain --untracked-files=no    # only this task's files may be listed; stop otherwise
git add canvas_api_guard.py test_canvas_api_guard.py level2/canvas_api_operations.py test_canvas_api_operations.py level2/SKILL.md level2/README.md codex/canvas-api-guard.rules 2>/dev/null
git commit -m "docs: document regrade-quiz-question and make Codex prompt for it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

---

### Task 7: The guard contract for both regrade bodies

**Files:** Modify `test_canvas_api_operations.py` (`TestGuardWriteContract`). No source change.

**Interfaces:** Consumes Tasks 0-2. Produces `TestGuardWriteContract.test_the_real_guard_proves_both_regrade_writes`.

This is the one test that runs the **real** guard's `main()` and feeds its actual stdout to
`guard_write`. Mocked stdout shapes cannot prove the layers agree; this is also the test that
would have caught the Task 3 blocker before any of this was written.

- [ ] **Step 1: Write the failing test** — append to `class TestGuardWriteContract(GuardTestCase):`

```python
    def test_the_real_guard_proves_both_regrade_writes(self):
        """A regrade sends Canvas's resource[][field] shapes; the guard must prove them and
        guard_write must parse the evidence it prints for them."""
        answers = [{"id": 1001, "text": "A", "weight": 100}, {"id": 1002, "text": "B", "weight": 0},
                   {"id": 1003, "text": "C", "weight": 0}, {"id": 1004, "text": "D", "weight": 0}]
        regraded = [dict(a, weight=(100 if a["id"] in (1003, 1004) else 0)) for a in answers]
        question = {"id": 789, "quiz_id": 5, "question_type": "multiple_choice_question",
                    "points_possible": 2.0, "answers": answers}
        key_body = {"question": {"answers": regraded}}
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResponse(payload=question),
                FakeResponse(payload=dict(question, answers=regraded)),
                FakeResponse(payload=dict(question, answers=regraded))]):
            code, captured = self.run_main(["put", "courses/12/quizzes/5/questions/789", "--yes",
                                            "-o", "json", "-d", json.dumps(key_body)])
        self.assertEqual(code, 0)
        completed = mock.Mock(returncode=0, stdout=captured, stderr="")
        with mock.patch.object(operations.subprocess, "run", return_value=completed), \
                mock.patch("sys.stdout", io.StringIO()):
            evidence = operations.guard_write("put", "courses/12/quizzes/5/questions/789",
                                              key_body, "yes")
        self.assertEqual(evidence["verification"], "passed")

        before = {"quiz_submissions": [{"id": 55, "user_id": 34, "attempt": 1, "score": 6.0}]}
        after = {"quiz_submissions": [dict(before["quiz_submissions"][0], score=8.0)]}
        score_body = {"quiz_submissions": [{"attempt": 1,
                                            "questions": {"789": {"score": 2.0}}}]}
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResponse(payload=before), FakeResponse(payload=after),
                FakeResponse(payload=after)]):
            code, captured = self.run_main(["put", "courses/12/quizzes/5/submissions/55", "--yes",
                                            "-o", "json", "-d", json.dumps(score_body)])
        self.assertEqual(code, 0)
        completed = mock.Mock(returncode=0, stdout=captured, stderr="")
        with mock.patch.object(operations.subprocess, "run", return_value=completed), \
                mock.patch("sys.stdout", io.StringIO()):
            evidence = operations.guard_write("put", "courses/12/quizzes/5/submissions/55",
                                              score_body, "yes")
        self.assertEqual(evidence["verification"], "passed")
        self.assertEqual(evidence["url"],
                         "https://" + HOST + "/api/v1/courses/12/quizzes/5/submissions/55")
```

- [ ] **Step 2: Run it against the guard as it was before Task 3** — `git stash` the guard change if
  checking the red form: expect `AssertionError: 3 != 0` and, in the evidence,
  `"WRITE STATUS UNCERTAIN: read-back did not match requested field(s): answers"`. That failure is
  the reason Task 3 exists; restore the change before continuing.

- [ ] **Step 3: Run** — `python3 -m unittest test_canvas_api_operations -v 2>&1 | tail -3` → `OK`,
  then the whole suite: `python3 -m unittest 2>&1 | tail -3` → `OK`, previous count plus one. The suite
  must also stay quiet: `python3 -m unittest 2>&1 | grep -c "regrade-quiz-question"` prints `0`.

- [ ] **Step 4: Commit**

```
git status --porcelain --untracked-files=no    # only this task's files may be listed; stop otherwise
git add canvas_api_guard.py test_canvas_api_guard.py level2/canvas_api_operations.py test_canvas_api_operations.py level2/SKILL.md level2/README.md codex/canvas-api-guard.rules 2>/dev/null
git commit -m "test: pin the guard contract for both regrade write shapes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Sg4JytXUDBceJk8aRCqFp"
```

---

## PILOT CHECK — every assumption that offline work cannot settle

Run these on the owner's live pilot, in this order, before the operation is used on a real class.
The first four are the ones that can change the code.

1. **PILOT CHECK — more than one correct answer.** canvas-cli only ever set exactly *one* answer
   to weight 100. That Canvas accepts several weight-100 answers on a
   `multiple_choice_question` and awards `points_possible` for *any* of them is the central
   unverified claim of this operation. Prove it on a throwaway quiz with a single test student
   before any real use. If Canvas instead grades against the first weight-100 answer, the whole
   design falls back to one id and the owner's "C and D" case needs a different mechanism.
2. **PILOT CHECK — the answer round-trip.** That sending back only
   `id, text, html, comments, comments_html` + `weight` leaves each answer's text, HTML and
   comments unchanged, and that Canvas preserves the answer **ids** across the update (canvas-cli
   relies on this when it re-checks the key, but never checked text). Compare the question before
   and after on the pilot quiz, field by field. If any answer field is lost, add it to
   `ANSWER_FIELDS`.
3. **PILOT CHECK — the score body.** That Canvas accepts the JSON body
   `{"quiz_submissions": [{"attempt": N, "questions": {"<qid>": {"score": P}}}]}` on
   `PUT courses/:c/quizzes/:q/submissions/:id` when sent by the guard exactly as canvas-cli's
   `PutJSON` sends it, and that the response is the same `{"quiz_submissions": [...]}` envelope
   the read-back comparison depends on.
4. **PILOT CHECK — the history read.** That an instructor token sees, on
   `courses/:c/assignments/:a/submissions/:user_id?include[]=submission_history`, one entry per
   attempt with `submission_data[] = {question_id, answer_id, points}` for a classic quiz. Without
   `answer_id` there is no regrade: every row would be `skipped`, and the operation would report a
   plan that changes nothing.
5. **PILOT CHECK — pagination.** That `courses/:c/quizzes/:q/submissions` really returns the
   envelope with no usable `rel="next"` through the guard, and that `page=2` returns the next
   rows on a quiz with more than 100 submissions.
6. **PILOT CHECK — the read-back window.** That `?attempt=N` reports the updated score within
   3 reads 1s apart. If it does not, raise `READ_BACK_READS`, do **not** loosen the comparison.
7. **PILOT CHECK — `quiz_type` and New Quizzes.** That a graded classic quiz reports
   `quiz_type: "assignment"` with an `assignment_id`, and that a New Quizzes quiz is absent from
   `courses/:c/quizzes/:id` (canvas-cli's note that New Quizzes are external-tool assignments and
   never appear in the classic list). If a New Quizzes id instead returns an object, the refusal
   message must name what it saw.
8. **PILOT CHECK — the uncertain path.** Deliberately make one expected score wrong (edit the
   plan's `expected_score` in a scratch copy) and confirm the operation prints
   `WRITE STATUS UNCERTAIN`, exits 3, and stops without writing the remaining attempts.
9. **PILOT CHECK — the batch cap.** 100 is a judgement call, not a measured limit. Confirm with
   the owner that no section this is used on exceeds it, and that refusing the whole batch (rather
   than rescoring the first 100) is the behaviour they want.
10. **PILOT CHECK — Codex's prompt.** That Codex shows the `regrade-quiz-question --yes` command
    to the instructor before it runs, and that the dry-run plan the instructor approved is the
    same command line with `--dry-run` removed.
