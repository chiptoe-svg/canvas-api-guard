# Guard Pilot Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six guard gaps a pre-pilot review found, so an agent driving the guard cannot choose its own interpreter, silently destroy unpublished faculty work, exhaust memory on one response, write an ambiguous audit record, keep education-record values forever, or reach account administration.

**Architecture:** Every change is inside `canvas_api_guard.py`, and each one extends a rule the file already states rather than adding a new model. The interpreter check reuses `trusted_path`. The draft refusal is one more `reason` branch in `prove_draft`. The response cap bounds the single `read()` that already exists. The audit changes stay inside `log_event`. The path refusal goes in `canvas_url`, which the file already documents as the one place every URL is built.

**Tech Stack:** Python 3, standard library only. `unittest` (`python3 -m unittest -v`). No third-party dependencies anywhere in this repo.

**Spec:** `docs/superpowers/specs/2026-09-13-guard-pilot-safety-design.md`

## Global Constraints

- **Standard library only.** No new third-party dependency in either program or either test file.
- **Red-proof every test.** Before a test counts as evidence, run it with only its fix reverted and see it fail. A test never observed failing proves nothing.
- **The guard's exit codes are a contract:** 0 done and verified, 2 refused or failed (nothing was sent, or Canvas refused), 3 sent but unverified. A change must never turn a sent write into exit 2.
- **The token is never printed, logged, echoed, or placed in argv or the environment.**
- **Every guard subcommand must appear in exactly one list in `codex/canvas-api-guard.rules`.** `test_every_guard_subcommand_is_classified_exactly_once` fails otherwise. Only `get`, `draft` and `student-attention` may be allowed without a prompt.
- **Version:** bump `USER_AGENT` in `canvas_api_guard.py` from `canvas-api-guard/1.17.0` to `canvas-api-guard/1.18.0` in the final task, not before.
- Tests run from the repo root: `python3 -m unittest -v`.

---

## File Structure

| File | Responsibility | Tasks |
| --- | --- | --- |
| `canvas_api_guard.py` | all six behaviour changes | 1–6 |
| `test_canvas_api_guard.py` | one test class per change | 1–6 |
| `install.sh` | preflight that the pinned interpreter exists | 1 |
| `codex/canvas-api-guard.rules` | classify the new `audit` subcommand | 5 |
| `codex/skills/canvas-api-guard/SKILL.md` | document `audit prune` and the new refusals | 5, 7 |
| `README.md`, `docs/IT-REVIEW.md` | retention default, review surface | 7 |
| `LICENSE` | new, gated on the owner's choice | 8 |

---

### Task 1: Pin the interpreter

The guard proves its own file is root-owned before touching the keychain (`check_provenance`), then lets `#!/usr/bin/env python3` pick the interpreter out of the caller's `PATH`. An agent that puts a `python3` earlier in `PATH` runs the guard inside its own interpreter, and the keychain read happens there.

**Files:**
- Modify: `canvas_api_guard.py:1` (shebang), `canvas_api_guard.py:142-146` (`check_provenance`)
- Modify: `level2/canvas_api_operations.py:1` (shebang)
- Modify: `install.sh` (preflight near the top, before `DEST_DIR` is used)
- Test: `test_canvas_api_guard.py`

**Interfaces:**
- Produces: `guard.trusted_interpreter()` → the resolved interpreter path, or raises `GuardError`. Task 7 mentions it in the docs; no other task calls it.

- [ ] **Step 1: Write the failing tests**

Add to `test_canvas_api_guard.py`, after `class TestFixedProductionConfig`:

```python
class TestTrustedInterpreter(GuardTestCase):
    """The guard proves its own file is root-owned; the interpreter executing that file has to
    clear the same bar, or PATH still chooses the code that reads the keychain."""

    def test_a_user_owned_interpreter_is_refused(self):
        fake = os.path.join(self.state_dir, "python3")
        with open(fake, "w"):
            pass
        os.chmod(fake, 0o755)
        with mock.patch.object(guard.sys, "executable", fake):
            with self.assertRaises(guard.GuardError) as caught:
                guard.trusted_interpreter()
        self.assertIn("Python interpreter", str(caught.exception))

    def test_a_root_owned_interpreter_is_accepted(self):
        with mock.patch.object(guard.sys, "executable", "/bin/sh"):
            self.assertEqual(guard.trusted_interpreter(), os.path.realpath("/bin/sh"))

    def test_an_unset_interpreter_is_refused(self):
        with mock.patch.object(guard.sys, "executable", ""):
            with self.assertRaises(guard.GuardError) as caught:
                guard.trusted_interpreter()
        self.assertIn("sys.executable", str(caught.exception))

    def test_provenance_checks_the_interpreter_when_the_config_is_the_installed_one(self):
        """check_provenance runs before read_token and before the network; the interpreter
        check has to sit inside it, not beside it."""
        fake = os.path.join(self.state_dir, "python3")
        with open(fake, "w"):
            pass
        os.chmod(fake, 0o755)
        with mock.patch.object(guard, "INSTALLED_CONFIG_PATH", guard.CONFIG_PATH), \
                mock.patch.object(guard, "installed_guard_file", lambda: "/bin/sh"), \
                mock.patch.object(guard.sys, "executable", fake):
            with self.assertRaises(guard.GuardError) as caught:
                guard.check_provenance()
        self.assertIn("Python interpreter", str(caught.exception))

    def test_both_programs_name_an_absolute_interpreter(self):
        root = os.path.dirname(os.path.abspath(__file__))
        for name in ("canvas_api_guard.py", os.path.join("level2", "canvas_api_operations.py")):
            with open(os.path.join(root, name)) as handle:
                first = handle.readline().strip()
            self.assertEqual(first, "#!/usr/bin/python3", name)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m unittest test_canvas_api_guard.TestTrustedInterpreter -v`
Expected: FAIL — `AttributeError: module 'canvas_api_guard' has no attribute 'trusted_interpreter'`, and the shebang test fails with `'#!/usr/bin/env python3' != '#!/usr/bin/python3'`.

- [ ] **Step 3: Add the function and call it**

In `canvas_api_guard.py`, immediately after `installed_guard_file()`:

```python
def trusted_interpreter():
    """The interpreter executing this file must clear the same bar as the file itself. The
    shebang names an absolute path, but `python3 canvas_api_guard.py` still runs whatever
    python the caller's PATH supplies, and that process is the one that reads the keychain."""
    running = sys.executable
    if not running:
        raise GuardError("the guard cannot prove its interpreter: sys.executable is not set")
    return trusted_path(running, "the Python interpreter")
```

Replace `check_provenance` with:

```python
def check_provenance():
    """Prove the running guard is the installed, root-owned one, and that an equally trusted
    interpreter is executing it, before any credential use."""
    if CONFIG_PATH != INSTALLED_CONFIG_PATH:
        return                       # test seam: a throwaway config is never an installation
    trusted_path(installed_guard_file(), "the guard executable")
    trusted_interpreter()
```

- [ ] **Step 4: Change both shebangs**

Line 1 of `canvas_api_guard.py` and line 1 of `level2/canvas_api_operations.py`:

```python
#!/usr/bin/python3
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m unittest test_canvas_api_guard.TestTrustedInterpreter -v`
Expected: 5 tests PASS.

Run: `python3 -m unittest -v`
Expected: the whole suite passes. The test seam means no existing test hits the interpreter check.

- [ ] **Step 6: Add the installer preflight**

In `install.sh`, before the install steps (near the `DEST_DIR=/usr/local/libexec` line), add:

```sh
# The installed programs name /usr/bin/python3 absolutely, so PATH cannot choose the
# interpreter that reads the credential store. Refuse to install if it is not there.
PINNED_PYTHON=/usr/bin/python3
if [ ! -x "$PINNED_PYTHON" ]; then
    echo "error: $PINNED_PYTHON is missing. On macOS install the Command Line Tools" >&2
    echo "       (xcode-select --install), then run this again." >&2
    exit 1
fi
if [ "$(stat -f %u "$PINNED_PYTHON" 2>/dev/null || stat -c %u "$PINNED_PYTHON")" != "0" ]; then
    echo "error: $PINNED_PYTHON is not owned by root; refusing to install" >&2
    exit 1
fi
```

- [ ] **Step 7: Verify the installer preflight runs**

Run: `sh -n install.sh`
Expected: no output (syntax is valid).

Run: `/usr/bin/python3 --version`
Expected: a version string. If this fails on the development machine, stop and report it — the pinned path must exist before this change can ship.

- [ ] **Step 8: Red-proof**

Revert only the `trusted_interpreter()` call inside `check_provenance`, run `python3 -m unittest test_canvas_api_guard.TestTrustedInterpreter -v`, and confirm `test_provenance_checks_the_interpreter_when_the_config_is_the_installed_one` fails. Restore it.

- [ ] **Step 9: Commit**

```bash
git add canvas_api_guard.py level2/canvas_api_operations.py install.sh test_canvas_api_guard.py
git commit -m "feat(guard): pin the interpreter, not just the guard file

check_provenance proved the guard executable was the installed root-owned
file, then let the shebang pick python3 out of the caller's PATH. The
process that reads the keychain is the interpreter, so it has to clear the
same bar. Both shebangs are absolute and install.sh refuses to install
without a root-owned /usr/bin/python3."
```

---

### Task 2: `draft` never deletes a top-level object

`do_draft` dispatches to `VERBS[method]`, and the draft parser accepts `delete`. `prove_draft` establishes only that the target is unpublished. Draft mode's premise — no student can see it, so no approval is needed — quietly assumes the change is recoverable. Deleting an unpublished quiz destroys faculty work no student ever needed to see.

**Files:**
- Modify: `canvas_api_guard.py:541-586` (`prove_draft`)
- Test: `test_canvas_api_guard.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: no new symbols. `prove_draft(cfg, method, path, body)` keeps its signature.

- [ ] **Step 1: Write the failing tests**

```python
class TestDraftNeverDeletesTopLevel(GuardTestCase):
    """Unpublished is not the same as recoverable. Draft may remove a question from a quiz it
    is building; it may not remove the quiz."""

    def test_deleting_an_unpublished_quiz_is_refused(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["draft", "delete", "courses/1/quizzes/5"])
        self.assertEqual(code, 2)
        self.assertIn("never deletes", self.last_stderr)
        urlopen.assert_not_called()
        self.assertEqual([line["confirmation"] for line in self.log_lines()
                          if line.get("event") == "refusal"], ["refused-not-draft"])

    def test_deleting_a_collection_is_refused(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["draft", "delete", "courses/1/assignments"])
        self.assertEqual(code, 2)
        self.assertIn("never deletes", self.last_stderr)
        urlopen.assert_not_called()

    def test_deleting_a_question_of_an_unpublished_quiz_is_allowed(self):
        responses = [FakeResponse(payload={"id": 5, "published": False}),   # parent proof
                     FakeResponse(payload={"id": 9}),                        # the pre-read
                     FakeResponse(payload={"id": 9}),                        # the DELETE
                     FakeResponse(status=404, payload={})]                   # gone on read-back
        with mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            code, _ = self.run_main(["draft", "delete", "courses/1/quizzes/5/questions/9"])
        self.assertEqual(code, 0)
        self.assertTrue(urlopen.called)

    def test_an_ordinary_delete_with_approval_is_unaffected(self):
        responses = [FakeResponse(payload={"id": 5, "published": True}),
                     FakeResponse(payload={"id": 5}),
                     FakeResponse(status=404, payload={})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["delete", "courses/1/quizzes/5", "--yes"])
        self.assertEqual(code, 0)
```

The response sequences match the real call order. `do_delete` (`canvas_api_guard.py:1125`) reads the object, writes, then reads back, treating a 404 on that read-back as proof it is gone (`:1143`) — three calls. A *draft* delete adds `prove_draft`'s parent read in front, making four. If a sequence still runs short, follow the failure; never change `do_delete` to fit a test.

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m unittest test_canvas_api_guard.TestDraftNeverDeletesTopLevel -v`
Expected: the two refusal tests FAIL — the delete is attempted instead of refused.

- [ ] **Step 3: Add the branch**

In `prove_draft`, insert immediately after the `if not match:` branch and before `elif unsafe:`:

```python
    elif method.lower() == "delete" and not match.group(4):
        reason = ("draft never deletes courses/%s/%s: unpublished work is still faculty work "
                  "and deleting it is not reversible. Use delete with --dry-run, then --yes. "
                  "Draft may still delete the questions, groups or overrides under an "
                  "unpublished item." % (match.group(1), match.group(2)))
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest test_canvas_api_guard.TestDraftNeverDeletesTopLevel -v`
Expected: 4 tests PASS.

Run: `python3 -m unittest -v`
Expected: the whole suite passes.

- [ ] **Step 5: Red-proof**

Comment out the new `elif` branch, rerun the class, confirm both refusal tests fail. Restore it.

- [ ] **Step 6: Commit**

```bash
git add canvas_api_guard.py test_canvas_api_guard.py
git commit -m "feat(guard): draft never deletes a top-level object

prove_draft established that a target was unpublished, which is not the same
as recoverable. Draft mode writes without asking anyone, so it may remove a
question from the quiz it is building, but not the quiz."
```

---

### Task 3: Bound one response body

`PAGE_CAP = 200` already bounds `--all-pages`. One response body is read with an unbounded `raw.read()`. The refusal must not turn a sent write into exit 2, so it raises `RequestFailure` carrying the status: `send_write` then treats a non-4xx as uncertain, which is the truth — the write was sent and its result could not be read.

**Files:**
- Modify: `canvas_api_guard.py:78` (constant, beside `PAGE_CAP`), `canvas_api_guard.py:484-494` (`send_request`)
- Modify: `test_canvas_api_guard.py:56-58` (`FakeResponse.read` must accept a size argument)
- Test: `test_canvas_api_guard.py`

**Interfaces:**
- Produces: `guard.MAX_RESPONSE_BYTES` (int). Tests patch it rather than building large payloads.

- [ ] **Step 1: Teach the test double to take a size**

`FakeResponse.read` currently takes no argument, so a bounded read would raise `TypeError`. Replace it:

```python
    def read(self, amt=None):
        return self._payload if amt is None else self._payload[:amt]
```

- [ ] **Step 2: Write the failing tests**

```python
class TestResponseSizeCap(GuardTestCase):
    """--all-pages is bounded by PAGE_CAP; one response body was not bounded at all."""

    def test_an_oversized_read_is_refused(self):
        big = {"blob": "x" * 500}
        with mock.patch.object(guard, "MAX_RESPONSE_BYTES", 64), \
                mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=big)
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 2)
        self.assertIn("64-byte limit", self.last_stderr)
        self.assertTrue(any(line.get("error") == "ResponseTooLarge" for line in self.log_lines()))

    def test_a_response_at_the_limit_is_accepted(self):
        with mock.patch.object(guard, "MAX_RESPONSE_BYTES", 4096), \
                mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)

    def test_an_oversized_read_back_after_a_write_is_uncertain_not_refused(self):
        """The write was sent. Exit 2 would claim nothing happened."""
        responses = [FakeResponse(payload={"id": 1, "name": "before"}),
                     FakeResponse(payload={"id": 1, "name": "after"}),
                     FakeResponse(payload={"id": 1, "name": "x" * 500})]
        with mock.patch.object(guard, "MAX_RESPONSE_BYTES", 64), \
                mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["put", "courses/1", "-d", '{"course": {"name": "after"}}',
                                     "--yes"])
        self.assertEqual(code, 3)
```

The two small payloads serialise to well under 64 bytes, so only the third trips the cap. The assertion that matters is exit 3, never exit 2: the write was sent, and only its read-back was unreadable.

- [ ] **Step 3: Run them and watch them fail**

Run: `python3 -m unittest test_canvas_api_guard.TestResponseSizeCap -v`
Expected: FAIL — `AttributeError: module 'canvas_api_guard' has no attribute 'MAX_RESPONSE_BYTES'`.

- [ ] **Step 4: Add the constant**

Beside `PAGE_CAP` at `canvas_api_guard.py:78`:

```python
MAX_RESPONSE_BYTES = 8 * 1024 * 1024   # one response body. --all-pages is bounded separately by
                                       # PAGE_CAP; this bounds the single read underneath it.
```

- [ ] **Step 5: Bound the read**

In `send_request`, replace the response block. Before:

```python
        raw = open_request(request)
        status, head, text = raw.status, dict(raw.headers), raw.read()
        raw.close()
```

After — read one byte past the cap so the overflow is detectable, and check outside the `except Exception` so the refusal is not rewritten as a transport failure:

```python
        raw = open_request(request)
        status, head, text = raw.status, dict(raw.headers), raw.read(MAX_RESPONSE_BYTES + 1)
        raw.close()
```

Then immediately after that `try/except` block, before the success `log_event`:

```python
    if len(text) > MAX_RESPONSE_BYTES:
        log_event(cfg.log_path, {"event": event, "verb": method, "path": npath, "ok": False,
                                 "status": status, "error": "ResponseTooLarge"})
        # RequestFailure, not GuardError: on a write this reaches send_write, which treats a
        # non-4xx as uncertain. The write was sent; only its result is unreadable.
        raise RequestFailure("%s %s returned more than the %d-byte limit; narrow the request "
                             "with --fields, a smaller per_page, or a more specific path"
                             % (method, npath, MAX_RESPONSE_BYTES), status=status)
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m unittest test_canvas_api_guard.TestResponseSizeCap -v`
Expected: 3 tests PASS.

Run: `python3 -m unittest -v`
Expected: the whole suite passes.

- [ ] **Step 7: Red-proof**

Change the read back to `raw.read()` and drop the length check; rerun the class and confirm the first and third tests fail. Restore.

- [ ] **Step 8: Commit**

```bash
git add canvas_api_guard.py test_canvas_api_guard.py
git commit -m "feat(guard): bound one response body

PAGE_CAP bounded --all-pages; the single read underneath it was unbounded.
The refusal is a RequestFailure carrying the status, so an oversized
read-back after a write stays uncertain rather than claiming nothing was
sent."
```

---

### Task 4: One correlation ID per run, and one write per record

`log_event` appends through a buffered file object. Append is atomic only up to `PIPE_BUF`; a `changes` array carrying long text exceeds 4 KiB and two concurrent guards can interleave. Nothing ties a request, its evidence and its refusal to the same run except a PID, which is reused.

**Files:**
- Modify: `canvas_api_guard.py:292-301` (`log_event`), plus a module-level `_RUN_ID`
- Modify: `test_canvas_api_guard.py:77` (`setUp` must reset `_RUN_ID`, as it already resets `_SOURCE`)
- Test: `test_canvas_api_guard.py`

**Interfaces:**
- Produces: `guard.run_id()` → a stable string for the life of the process. Every log record gains a `"run"` key.

- [ ] **Step 1: Write the failing tests**

```python
class TestAuditCorrelation(GuardTestCase):
    def test_every_record_of_one_run_shares_a_correlation_id(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)
        runs = set(line["run"] for line in self.log_lines())
        self.assertEqual(len(runs), 1)
        self.assertTrue(all(line["run"] for line in self.log_lines()))

    def test_the_token_is_not_in_the_correlation_id(self):
        self.assertNotIn(TOKEN, guard.run_id())

    def test_concurrent_writers_produce_intact_lines(self):
        """A record larger than PIPE_BUF must not interleave with another writer's."""
        import threading
        payload = {"event": "test", "blob": "y" * 9000}

        def writer():
            for _ in range(20):
                guard.log_event(self.log_path, dict(payload))

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        with open(self.log_path) as handle:
            lines = [line for line in handle if line.strip()]
        self.assertEqual(len(lines), 80)
        for line in lines:
            json.loads(line)          # raises if two writers interleaved
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m unittest test_canvas_api_guard.TestAuditCorrelation -v`
Expected: FAIL — `KeyError: 'run'`, and `AttributeError: ... has no attribute 'run_id'`.

- [ ] **Step 3: Add the run ID and the single write**

Above `log_event` in `canvas_api_guard.py`:

```python
_RUN_ID = None

def run_id():
    """One id for every record this process writes. A PID is reused; this is not, so a request,
    its evidence and its refusal cannot be read as belonging to a different run."""
    global _RUN_ID
    if _RUN_ID is None:
        _RUN_ID = os.urandom(6).hex()
    return _RUN_ID
```

Replace the body of `log_event`:

```python
def log_event(log_path, fields):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"timestamp": stamp, "pid": os.getpid(), "run": run_id(),
              "source": invocation_source()}
    record.update(fields)
    line = (json.dumps(record, sort_keys=True, default=str) + "\n").encode("utf-8")
    fd = secure_log_fd(log_path)
    try:
        # One write on an O_APPEND descriptor, so a record longer than a pipe buffer cannot be
        # split across another writer's. This is not a lock: it removes interleaving, it does
        # not order two runs.
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return record
```

- [ ] **Step 4: Reset the run ID between tests**

In `GuardTestCase.setUp`, beside `guard._SOURCE = None`:

```python
        guard._RUN_ID = None
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m unittest test_canvas_api_guard.TestAuditCorrelation -v`
Expected: 3 tests PASS.

Run: `python3 -m unittest -v`
Expected: the whole suite passes. If a test asserts an exact set of log-record keys, update it to expect `run` — that is a real interface change, not a test to weaken.

- [ ] **Step 6: Red-proof**

Restore the old buffered `with os.fdopen(fd, "a")` body and rerun the class; confirm `test_concurrent_writers_produce_intact_lines` fails or becomes flaky, and the correlation test fails on `KeyError`. Restore.

If the concurrency test passes even with the old implementation on this platform, say so in the commit message rather than deleting the test — it still pins the behaviour, and it will fail on a platform with a smaller atomic write.

- [ ] **Step 7: Commit**

```bash
git add canvas_api_guard.py test_canvas_api_guard.py
git commit -m "feat(guard): one correlation id per run, one write per record

A record longer than a pipe buffer could interleave with a concurrent
guard's, and nothing but a reusable PID tied a request to its evidence."
```

---

### Task 5: `audit prune`, and a documented retention default

The log already records the right things and omits the wrong ones. What is missing is the end of the lifecycle: nothing removes old education-record values.

**Files:**
- Modify: `canvas_api_guard.py` (new `do_audit_prune`, new subparser, `main` dispatch)
- Modify: `codex/canvas-api-guard.rules` (classify `audit`)
- Modify: `test_canvas_api_guard.py:1809-1812` and `:1829-1831` (the rules-coverage assertions)
- Modify: `codex/skills/canvas-api-guard/SKILL.md` (document the command)
- Test: `test_canvas_api_guard.py`

**Interfaces:**
- Consumes: `run_id()` from Task 4 — the prune logs its own record.
- Produces: `guard.do_audit_prune(cfg, days)`; CLI `canvas_api_guard.py audit prune --older-than DAYS`; `guard.RETENTION_DAYS` (int, documentation default, not enforced automatically).

- [ ] **Step 1: Write the failing tests**

```python
class TestAuditPrune(GuardTestCase):
    def seed(self, ages_in_days):
        """Write one record per age, oldest first, bypassing log_event's own timestamp."""
        lines = []
        now = guard.datetime.datetime.now(guard.datetime.timezone.utc)
        for age in ages_in_days:
            stamp = (now - guard.datetime.timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
            lines.append(json.dumps({"timestamp": stamp, "event": "read", "age": age}))
        with open(self.log_path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(self.log_path, 0o600)

    def test_records_older_than_the_cutoff_are_dropped_and_newer_ones_kept(self):
        self.seed([400, 200, 10, 1])
        code, _ = self.run_main(["audit", "prune", "--older-than", "180"])
        self.assertEqual(code, 0)
        ages = [line.get("age") for line in self.log_lines() if "age" in line]
        self.assertEqual(ages, [10, 1])

    def test_the_prune_logs_itself(self):
        self.seed([400, 1])
        self.run_main(["audit", "prune", "--older-than", "180"])
        pruned = [line for line in self.log_lines() if line.get("event") == "audit-prune"]
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0]["records_dropped"], 1)
        self.assertEqual(pruned[0]["records_kept"], 1)

    def test_an_unparseable_line_is_kept_never_silently_discarded(self):
        self.seed([400])
        with open(self.log_path, "a") as handle:
            handle.write("this is not json\n")
        self.run_main(["audit", "prune", "--older-than", "180"])
        with open(self.log_path) as handle:
            self.assertIn("this is not json", handle.read())

    def test_the_pruned_log_keeps_its_private_mode(self):
        self.seed([400, 1])
        self.run_main(["audit", "prune", "--older-than", "180"])
        self.assertEqual(os.stat(self.log_path).st_mode & 0o777, 0o600)

    def test_a_zero_day_retention_is_refused(self):
        self.seed([1])
        code, _ = self.run_main(["audit", "prune", "--older-than", "0"])
        self.assertEqual(code, 2)
        self.assertIn("at least 1 day", self.last_stderr)

    def test_the_prune_reaches_no_network(self):
        self.seed([400])
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.run_main(["audit", "prune", "--older-than", "180"])
        urlopen.assert_not_called()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m unittest test_canvas_api_guard.TestAuditPrune -v`
Expected: FAIL — argparse rejects `audit` as an invalid choice.

- [ ] **Step 3: Implement the prune**

Add near the other `do_*` functions, after `do_delete`:

```python
RETENTION_DAYS = 180           # the pilot default, documented in SKILL.md; never automatic

def do_audit_prune(cfg, days):
    """Rewrite the audit log keeping only records newer than the cutoff. The same ownership and
    mode gate applies on the way in, the replacement is written privately and moved into place,
    and the file is never deleted. A line whose timestamp cannot be read is always kept."""
    if days < 1:
        raise GuardError("--older-than must be at least 1 day")
    os.close(secure_log_fd(cfg.log_path))       # the ownership and mode gate, before reading
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=days))
    kept, dropped = [], 0
    with open(cfg.log_path) as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                stamp = json.loads(line)["timestamp"]
                when = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc)
            except (ValueError, TypeError, KeyError):
                kept.append(line)               # unreadable: kept, never silently discarded
                continue
            if when >= cutoff:
                kept.append(line)
            else:
                dropped += 1
    temporary = cfg.log_path + ".prune"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        os.write(fd, "".join(kept).encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, cfg.log_path)
    log_event(cfg.log_path, {"event": "audit-prune", "older_than_days": days,
                             "records_kept": len(kept), "records_dropped": dropped})
    emit(cfg, {"verb": "AUDIT", "path": cfg.log_path,
               "note": "audit records older than %d days removed" % days,
               "object": {"records_kept": len(kept), "records_dropped": dropped}})
```

`READ_VERBS` is `("GET", "DOWNLOAD")` (`canvas_api_guard.py:76`) and `emit` logs anything whose verb is not in it (`:792`), so the call above would write a **second** record for one prune. Add `"AUDIT"` to `READ_VERBS` — the tuple's own comment says it holds "evidence verbs already logged as their own single line", which is exactly what the explicit `log_event` above makes this one:

```python
READ_VERBS = ("GET", "DOWNLOAD", "AUDIT")   # evidence verbs already logged as their own single line
```

`test_the_prune_logs_itself` asserts exactly one `audit-prune` record and fails if this is missed.

- [ ] **Step 4: Add the subcommand**

In `build_parser`, after the `download` subparser:

```python
    audit = subs.add_parser("audit", help="maintain the local audit log; reaches no network")
    audit_subs = audit.add_subparsers(dest="audit_action", required=True)
    prune = audit_subs.add_parser("prune", help="remove audit records older than --older-than days")
    prune.add_argument("--older-than", type=int, required=True, metavar="DAYS",
                       help="keep records newer than this many days (pilot default: %d)"
                            % RETENTION_DAYS)
    prune.add_argument("-o", "--output", choices=("text", "json"), default=None)
```

In `main`, beside the `download-submission-file` branch and before the body/config lines:

```python
        if args.verb == "audit":
            cfg = make_config(argparse.Namespace(output=args.output, dry_run=False,
                                                  yes=False, all_pages=False, fields=None))
            do_audit_prune(cfg, args.older_than)
            return 0
```

- [ ] **Step 5: Classify the new subcommand**

In `codex/canvas-api-guard.rules`, beside the other lists:

```python
MAINTENANCE = ["audit"]
```

and a rule matching the shape of the existing ones:

```python
prefix_rule(
    pattern = [GUARD, MAINTENANCE],
    decision = "prompt",
    justification = "removes local audit records: a person sees the retention window first",
    match = ["/usr/local/libexec/canvas_api_guard.py audit prune --older-than 180"],
    not_match = ["/usr/local/libexec/canvas_api_guard.py get courses"],
)
```

Then update the two coverage assertions in `test_canvas_api_guard.py`:

```python
        classified = (lists["READS"] + lists["DRAFTS"] + lists["WRITES"]
                      + lists["DOWNLOADS"] + lists["MAINTENANCE"])
```

and, in `test_only_the_three_unprompted_commands_are_allowed_without_a_prompt`:

```python
                self.assertIn(name, lists["WRITES"] + lists["DOWNLOADS"] + lists["MAINTENANCE"],
                              name)
```

- [ ] **Step 6: Document it in the guard skill**

`codex/skills/canvas-api-guard/SKILL.md` is checked by `TestSkillDocuments`, which fails if a skill shows a command the program does not have — and the reverse test fails if a command is undocumented. Add, in the same voice as the surrounding entries:

```sh
/usr/local/libexec/canvas_api_guard.py audit prune --older-than 180
```

with one sentence: the audit log holds identifiers, changed field values and verification results; `prune` removes records older than the window and keeps anything whose timestamp it cannot read. The pilot default is 180 days. It reaches no network.

- [ ] **Step 7: Run the tests**

Run: `python3 -m unittest test_canvas_api_guard.TestAuditPrune -v`
Expected: 7 tests PASS.

Run: `python3 -m unittest -v`
Expected: the whole suite passes, including the rules-coverage and skill-document tests.

- [ ] **Step 8: Red-proof**

Change the unparseable-line branch to `dropped += 1` instead of keeping the line; confirm `test_an_unparseable_line_is_kept_never_silently_discarded` fails. Restore.

- [ ] **Step 9: Commit**

```bash
git add canvas_api_guard.py codex/canvas-api-guard.rules codex/skills/canvas-api-guard/SKILL.md test_canvas_api_guard.py
git commit -m "feat(guard): audit prune, with a documented retention default

The log already recorded the right things and omitted the wrong ones; what
was missing was the end of the lifecycle. Pruning is itself logged, the file
is never deleted, and a line whose timestamp cannot be read is kept."
```

---

### Task 6: Refuse account-level and developer-key paths

`profile` validates only `level-1`/`level-2` and selects whether Specialized Functions are installed; there is no endpoint policy. This is the narrow version: two path prefixes no faculty pilot has any use for, refused for every verb including reads, so the rule needs no judgement about which operations are dangerous.

**Files:**
- Modify: `canvas_api_guard.py` (new constant and function near `normalise_path`, called from `canvas_url`)
- Modify: `codex/skills/canvas-api-guard/SKILL.md` (state the boundary)
- Test: `test_canvas_api_guard.py`

**Interfaces:**
- Produces: `guard.refuse_out_of_scope(npath)` → None or raises `GuardError`.

- [ ] **Step 1: Write the failing tests**

```python
class TestOutOfScopePaths(GuardTestCase):
    """Account administration and developer keys are outside a faculty pilot. Refused for every
    verb, reads included, because that needs no judgement about which are dangerous."""

    def test_an_account_path_is_refused_on_read(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["get", "accounts/1/users"])
        self.assertEqual(code, 2)
        self.assertIn("outside its scope", self.last_stderr)
        urlopen.assert_not_called()

    def test_an_account_path_is_refused_on_write(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["post", "accounts/1/courses", "-d", "{}", "--yes"])
        self.assertEqual(code, 2)
        urlopen.assert_not_called()

    def test_a_developer_key_path_is_refused(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["get", "developer_keys"])
        self.assertEqual(code, 2)
        urlopen.assert_not_called()

    def test_a_course_path_naming_accounts_further_down_is_allowed(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_main(["get", "courses/1/accounts"])
        self.assertEqual(code, 0)

    def test_the_refusal_happens_before_any_network_or_log_line(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["get", "accounts/1"])
        self.assertEqual(code, 2)
        urlopen.assert_not_called()
        self.assertEqual([line for line in self.log_lines() if line.get("event") == "read"], [])
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m unittest test_canvas_api_guard.TestOutOfScopePaths -v`
Expected: FAIL — the requests are attempted.

- [ ] **Step 3: Add the refusal**

Beside `normalise_path` in the host-pinning section:

```python
# Two path prefixes a faculty pilot never needs, refused for every verb including reads. This is
# deliberately not a list of "dangerous" operations: such a list invites the belief that what is
# missing from it is safe. Every other write is gated the way it always was, by a person seeing
# the URL and the changed fields and confirming.
OUT_OF_SCOPE = re.compile(r"^/api/v1/(accounts|developer_keys)(/|$)")

def refuse_out_of_scope(npath):
    if OUT_OF_SCOPE.match(npath):
        raise GuardError("this tool does not reach %s: account administration and developer "
                         "keys are outside its scope" % npath.split("?")[0])
```

`canvas_url` (`canvas_api_guard.py:328`) normalises inline while building the URL, so lift it into a variable. Before:

```python
    url = "https://" + host + normalise_path(path)
```

After:

```python
    npath = normalise_path(path)
    refuse_out_of_scope(npath)
    url = "https://" + host + npath
```

`main` already calls `canvas_url(cfg.host, args.path)` before anything else happens, so the refusal lands before the keychain, the network and any log line — which `test_the_refusal_happens_before_any_network_or_log_line` pins.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest test_canvas_api_guard.TestOutOfScopePaths -v`
Expected: 5 tests PASS.

Run: `python3 -m unittest -v`
Expected: the whole suite passes. If an existing test uses an `accounts/` path incidentally, change that test's path — do not weaken the refusal.

- [ ] **Step 5: Document the boundary**

In `codex/skills/canvas-api-guard/SKILL.md`, one line in the same voice as the rest: the guard reaches course-scoped Canvas endpoints; `accounts/...` and developer keys are refused for every verb, and that refusal is in the program, not in instructions.

- [ ] **Step 6: Red-proof**

Comment out the `refuse_out_of_scope` call in `canvas_url`; confirm four of the five tests fail. Restore.

- [ ] **Step 7: Commit**

```bash
git add canvas_api_guard.py codex/skills/canvas-api-guard/SKILL.md test_canvas_api_guard.py
git commit -m "feat(guard): refuse account-level and developer-key paths

The narrow version of an endpoint policy: two prefixes a faculty pilot never
needs, refused for every verb including reads, so the rule needs no judgement
about which operations are dangerous."
```

---

### Task 7: Version, README and IT review

**Files:**
- Modify: `canvas_api_guard.py:63` (`USER_AGENT`)
- Modify: `README.md`, `docs/IT-REVIEW.md`

- [ ] **Step 1: Bump the version**

```python
USER_AGENT = "canvas-api-guard/1.18.0"
```

- [ ] **Step 2: Check for a version assertion**

Run: `grep -rn "1\.17\.0" . --include="*.py" --include="*.md" --include="*.sh" --include="*.rules"`
Update every occurrence that names the guard's version. If a test asserts the version string, that is the intended coupling — update it.

- [ ] **Step 3: Update the review surface**

In `docs/IT-REVIEW.md`, add to the reviewed behaviour: the interpreter is pinned and verified root-owned before any credential use; draft mode cannot delete a top-level object; one response body is bounded; every audit record carries a per-run correlation id; `audit prune` implements a 180-day pilot retention default; `accounts/` and developer-key paths are refused for every verb.

In `README.md`, state the retention default and the two refused prefixes.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest -v`
Expected: every test passes. Record the count in the commit message.

- [ ] **Step 5: Commit**

```bash
git add canvas_api_guard.py README.md docs/IT-REVIEW.md
git commit -m "chore: guard 1.18.0, and the pilot-safety review surface"
```

---

### Task 8: LICENSE

**Gated on the owner's choice — do not guess a licence.** Ask which, then:

- [ ] **Step 1: Fetch the exact text**

```bash
gh api /licenses/<key> --jq .body > LICENSE
```

where `<key>` is the owner's choice (`mit`, `apache-2.0`, `agpl-3.0`, …). Fill in the copyright line if the text carries a placeholder.

- [ ] **Step 2: Name it in the README**

One line under a `## License` heading.

- [ ] **Step 3: Commit**

```bash
git add LICENSE README.md
git commit -m "docs: add LICENSE"
```

---

## Not in this plan

`accessibility-scan` is the other half of the spec and gets its own plan: it touches a different program (`level2/canvas_api_operations.py`), shares no code with any task here, and the spec says it can go whenever. Writing it separately keeps both plans independently executable.

Deferred with reasons recorded in the spec, and deliberately absent here: a general endpoint denylist, restricting draft edits to plan-created objects, read-only retry with backoff, and per-endpoint verification adapters.
