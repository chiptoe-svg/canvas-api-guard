#!/usr/bin/env python3
"""Tests for canvas_api_guard. Stdlib unittest only: python3 -m unittest -v

Every test that touches the request path replaces urllib.request.urlopen, so the suite
never reaches the network. Two tests prove that directly.
"""

import io
import json
import os
import tempfile
import unittest
from unittest import mock

import canvas_api_guard as guard

TOKEN = "SECRET-TOKEN-DO-NOT-LEAK-9d41"
HOST = "canvas.example.edu"


class FakeResponse(object):
    """The parts of an http.client.HTTPResponse that send_request uses."""

    def __init__(self, status=200, headers=None, payload=None):
        self.status = status
        self.headers = headers or {}
        self._payload = json.dumps(payload if payload is not None else {}).encode("utf-8")

    def read(self):
        return self._payload

    def close(self):
        pass


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.log_path = tempfile.mkstemp(prefix="cag-test-", suffix=".jsonl")
        os.close(handle)
        self.addCleanup(os.unlink, self.log_path)
        # a token that must never appear in the log or on stdout
        self.token_patcher = mock.patch.object(guard, "read_token", lambda: TOKEN)
        self.token_patcher.start()
        self.addCleanup(self.token_patcher.stop)

    def run_main(self, argv, stdin_is_tty=False):
        """Run main() with the log redirected, stdin non-TTY by default, stdout captured."""
        argv = list(argv) + ["--host", HOST, "--log-path", self.log_path]
        out, err = io.StringIO(), io.StringIO()
        stdin = io.StringIO()          # StringIO.isatty() is False
        if stdin_is_tty:
            stdin = mock.Mock()
            stdin.isatty.return_value = True
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err), \
                mock.patch("sys.stdin", stdin):
            code = guard.main(argv)
        self.last_stderr = err.getvalue()
        return code, out.getvalue()

    def log_lines(self):
        with open(self.log_path) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def log_text(self):
        with open(self.log_path) as handle:
            return handle.read()


class TestHostPinning(GuardTestCase):
    def test_rejects_a_path_with_a_scheme_or_netloc(self):
        for bad in ("https://evil.example.com/api/v1/courses/1",
                    "//evil.example.com/api/v1/courses/1",
                    "http://evil.example.com"):
            with self.assertRaises(guard.GuardError):
                guard.canvas_url(HOST, bad)

    def test_rejects_traversal(self):
        for bad in ("api/v1/../../etc/passwd", "courses/../../..", "/api/v1/courses/../1"):
            with self.assertRaises(guard.GuardError):
                guard.canvas_url(HOST, bad)

    def test_rejects_a_host_that_is_not_a_bare_hostname(self):
        for bad in ("https://canvas.example.edu", "canvas.example.edu/x", "a@b.example.edu"):
            with self.assertRaises(guard.GuardError):
                guard.canvas_url(bad, "courses/1")

    def test_every_url_stays_on_the_configured_host(self):
        url = guard.canvas_url(HOST, "courses/1")
        self.assertTrue(url.startswith("https://" + HOST + "/"))

    def test_the_verb_refuses_before_any_log_line_is_written(self):
        code, _ = self.run_main(["get", "https://evil.example.com/api/v1/courses/1"])
        self.assertEqual(code, 2)
        self.assertEqual(self.log_lines(), [])


class TestPathNormalisation(GuardTestCase):
    def test_all_three_forms_normalise_to_one(self):
        for given in ("/api/v1/courses/123", "api/v1/courses/123", "courses/123",
                      "/courses/123", "courses/123/"):
            self.assertEqual(guard.normalise_path(given), "/api/v1/courses/123")

    def test_query_strings_are_preserved(self):
        self.assertEqual(guard.normalise_path("courses/1/students?per_page=100"),
                         "/api/v1/courses/1/students?per_page=100")

    def test_empty_and_whitespace_paths_are_refused(self):
        for bad in ("", "   ", "courses/1 2", "courses\\1"):
            with self.assertRaises(guard.GuardError):
                guard.normalise_path(bad)


class TestConfirmation(GuardTestCase):
    def test_a_write_without_a_tty_and_without_yes_is_refused(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 7, "posted_grade": 88})
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 2)
        self.assertNotIn("confirmation:  yes-flag", output)
        self.assertIn("stdin is not a terminal", self.last_stderr)
        self.assertIn("pass --yes", self.last_stderr)
        requests = [line for line in self.log_lines() if line["event"] == "request"]
        self.assertEqual(requests, [])          # not even the pre-read was sent

    def test_the_refusal_precedes_the_keychain_and_every_network_call(self):
        """The property this tool exists for, demonstrable with no token and no account."""
        def no_keychain():
            raise AssertionError("the keychain was touched before the refusal")

        def no_network(*args, **kwargs):
            raise AssertionError("a request was made before the refusal")

        with mock.patch.object(guard, "read_token", no_keychain), \
                mock.patch("urllib.request.urlopen", side_effect=no_network):
            for verb, extra in (("post", ["-d", "{}"]), ("put", ["-d", "{}"]),
                                ("patch", ["-d", "{}"]), ("delete", [])):
                code, _ = self.run_main([verb, "courses/1/assignments/2"] + extra)
                self.assertEqual(code, 2, verb)
        events = [(line["event"], line["confirmation"]) for line in self.log_lines()]
        self.assertEqual(events, [("refusal", "refused-no-tty")] * 4)

    def test_the_yes_flag_is_recorded_as_the_confirmation_mode(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 3, "posted_grade": 95})
            code, _ = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        writes = [line for line in self.log_lines()
                  if line["event"] == "request" and line["kind"] == "write"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["confirmation"], "yes-flag")

    def test_a_human_at_a_tty_is_recorded_as_human_tty(self):
        with mock.patch("urllib.request.urlopen") as urlopen, \
                mock.patch.object(guard, "input", create=True, return_value="yes"):
            urlopen.return_value = FakeResponse(payload={"id": 3, "posted_grade": 95})
            code, _ = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3",
                 "-d", '{"submission": {"posted_grade": 95}}'], stdin_is_tty=True)
        self.assertEqual(code, 0)
        writes = [line for line in self.log_lines()
                  if line["event"] == "request" and line["kind"] == "write"]
        self.assertEqual(writes[0]["confirmation"], "human-tty")

    def test_a_read_needs_no_confirmation(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)


class TestLogBeforeRequest(GuardTestCase):
    def test_the_request_line_is_on_disk_before_urlopen_is_called(self):
        seen = {}

        def inspect_the_log(request, timeout=None):
            # runs INSIDE urlopen: whatever is in the log now was written beforehand
            seen["lines"] = self.log_lines()
            raise OSError("no network in tests")

        with mock.patch("urllib.request.urlopen", side_effect=inspect_the_log):
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 2)
        self.assertEqual(len(seen["lines"]), 1)
        self.assertEqual(seen["lines"][0]["event"], "request")
        self.assertEqual(seen["lines"][0]["verb"], "GET")
        self.assertEqual(seen["lines"][0]["path"], "/api/v1/courses/1")

    def test_a_failed_write_still_leaves_its_request_line(self):
        def boom(request, timeout=None):
            raise OSError("no network in tests")

        with mock.patch("urllib.request.urlopen", side_effect=boom):
            code, _ = self.run_main(["delete", "courses/1/assignments/2", "--yes"])
        self.assertEqual(code, 2)
        events = [(line["event"], line.get("verb")) for line in self.log_lines()]
        self.assertIn(("request", "GET"), events)
        self.assertEqual(events[0][0], "request")

    def test_the_log_file_is_not_world_readable(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            self.run_main(["get", "courses/1"])
        self.assertEqual(os.stat(self.log_path).st_mode & 0o077, 0)


class TestTokenIsNeverExposed(GuardTestCase):
    def test_the_token_is_absent_from_the_log_and_from_stdout(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 3, "posted_grade": 95})
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertNotIn(TOKEN, self.log_text())
        self.assertNotIn(TOKEN, output)
        # the token did reach the header of the request that was actually sent
        sent = urlopen.call_args[0][0]
        self.assertEqual(sent.get_header("Authorization"), "Bearer " + TOKEN)

    def test_dry_run_redacts_the_header_and_never_reads_the_token(self):
        def explode():
            raise AssertionError("--dry-run must not read the token")

        with mock.patch.object(guard, "read_token", explode):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--dry-run",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertIn("Authorization: Bearer <redacted>", output)
        self.assertNotIn(TOKEN, output)
        self.assertNotIn(TOKEN, self.log_text())


class TestDryRunSendsNothing(GuardTestCase):
    def test_every_verb_runs_under_dry_run_without_touching_the_network(self):
        def never(*args, **kwargs):
            raise AssertionError("--dry-run made a network call")

        cases = [["get", "courses/1"],
                 ["post", "courses/1/assignments", "-d", '{"assignment": {"name": "Lab"}}'],
                 ["put", "courses/1/assignments/2", "-d", '{"assignment": {"name": "Lab"}}'],
                 ["patch", "courses/1/assignments/2", "-d", '{"assignment": {"name": "L"}}'],
                 ["delete", "courses/1/assignments/2"]]
        with mock.patch("urllib.request.urlopen", side_effect=never):
            for case in cases:
                code, output = self.run_main(case + ["--dry-run"])
                self.assertEqual(code, 0, case)
                self.assertIn("DRY RUN", output)
                self.assertIn("https://" + HOST + "/api/v1/", output)
        for line in self.log_lines():
            if line["event"] == "request":
                self.assertTrue(line["dry_run"])


class TestEvidence(GuardTestCase):
    def test_put_reports_before_and_after_and_whether_they_match(self):
        responses = [FakeResponse(payload={"id": 3, "posted_grade": 60}),   # before
                     FakeResponse(payload={"id": 3, "posted_grade": 95}),   # the write
                     FakeResponse(payload={"id": 3, "posted_grade": 95})]   # read-back
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertIn("posted_grade", output)
        self.assertIn("60 -> 95", output)
        self.assertIn("match: True", output)

    def test_post_without_an_id_or_location_says_so_instead_of_inventing_evidence(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(status=201, headers={}, payload={"ok": True})
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 0)
        self.assertIn("neither an id nor a usable Location header", output)

    def test_post_reads_back_the_created_object_by_id(self):
        responses = [FakeResponse(status=201, payload={"id": 42, "name": "Lab 4"}),
                     FakeResponse(payload={"id": 42, "name": "Lab 4"})]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 0)
        self.assertIn("Lab 4", output)
        self.assertEqual(urlopen.call_args[0][0].full_url,
                         "https://" + HOST + "/api/v1/courses/1/assignments/42")

    def test_delete_reports_that_the_object_is_gone(self):
        responses = [FakeResponse(payload={"id": 2, "name": "Lab 4"}),  # before
                     FakeResponse(status=200, payload={"id": 2}),       # the delete
                     OSError("404")]                                    # read-back fails
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(["delete", "courses/1/assignments/2", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("read-back after delete: gone", output)


class FakeProc(object):
    def __init__(self, returncode=0, stdout=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, b""


class TestCredentialStore(unittest.TestCase):
    """The token lives in the macOS keychain or the Linux secret service. Nothing else.
    Not a GuardTestCase: that fixture patches read_token away, and these test the real one."""

    def setUp(self):
        self.calls = []

        def fake_run(argv, **kwargs):
            self.calls.append((argv, kwargs.get("input")))
            return FakeProc(stdout=(TOKEN + "\n").encode("utf-8"))
        self.run_patch = mock.patch.object(guard.subprocess, "run", side_effect=fake_run)
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

    def test_macos_reads_from_the_keychain(self):
        with mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True):
            self.assertEqual(guard.read_token(), TOKEN)
        argv, _ = self.calls[0]
        self.assertEqual(argv[:2], [guard.SECURITY_BIN, "find-generic-password"])
        self.assertEqual(argv[-1], "-w")

    def test_linux_reads_from_the_secret_service(self):
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard.shutil, "which", return_value="/usr/bin/secret-tool"):
            self.assertEqual(guard.read_token(), TOKEN)
        argv, _ = self.calls[0]
        self.assertEqual(argv[:2], ["/usr/bin/secret-tool", "lookup"])
        self.assertIn(guard.KEYCHAIN_SERVICE, argv)

    def test_linux_without_secret_tool_refuses_and_names_the_package(self):
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard.shutil, "which", return_value=None):
            with self.assertRaises(guard.GuardError) as caught:
                guard.read_token()
        self.assertIn("secret-tool", str(caught.exception))
        self.assertIn("libsecret", str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_an_unsupported_platform_refuses_before_any_subprocess(self):
        with mock.patch.object(guard.sys, "platform", "win32"):
            with self.assertRaises(guard.GuardError) as caught:
                guard.read_token()
        self.assertIn("macOS", str(caught.exception))
        self.assertIn("Linux", str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_an_empty_token_is_refused(self):
        self.run_patch.stop()
        self.addCleanup(self.run_patch.start)          # so the registered stop still works
        with mock.patch.object(guard.subprocess, "run", return_value=FakeProc(stdout=b"\n")), \
                mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True):
            with self.assertRaises(guard.GuardError) as caught:
                guard.read_token()
        self.assertIn("empty", str(caught.exception))

    def test_set_token_on_macos_sends_the_secret_twice_and_reads_it_back(self):
        """security asks for the password and a retype on stdin. Sending it once stored an
        EMPTY token (observed 2026-09-07). The read-back makes that impossible to miss."""
        with mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True), \
                mock.patch.object(guard.getpass, "getpass", return_value=TOKEN), \
                mock.patch("sys.stdout", io.StringIO()):
            guard.set_token()
        store_argv, store_input = self.calls[0]
        self.assertEqual(store_argv[:2], [guard.SECURITY_BIN, "add-generic-password"])
        self.assertNotIn(TOKEN, store_argv)                      # never in argv
        self.assertEqual(store_input, (TOKEN + "\n" + TOKEN + "\n").encode("utf-8"))
        self.assertEqual(self.calls[1][0][:2], [guard.SECURITY_BIN, "find-generic-password"])

    def test_set_token_on_linux_sends_the_secret_once(self):
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard.shutil, "which", return_value="/usr/bin/secret-tool"), \
                mock.patch.object(guard.getpass, "getpass", return_value=TOKEN), \
                mock.patch("sys.stdout", io.StringIO()):
            guard.set_token()
        store_argv, store_input = self.calls[0]
        self.assertEqual(store_argv[:2], ["/usr/bin/secret-tool", "store"])
        self.assertEqual(store_input, (TOKEN + "\n").encode("utf-8"))

    def test_set_token_refuses_when_the_read_back_differs(self):
        self.run_patch.stop()
        self.addCleanup(self.run_patch.start)
        responses = [FakeProc(), FakeProc(stdout=b"a-different-token\n")]  # store ok, read-back differs
        with mock.patch.object(guard.subprocess, "run", side_effect=responses), \
                mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True), \
                mock.patch.object(guard.getpass, "getpass", return_value=TOKEN):
            with self.assertRaises(guard.GuardError) as caught:
                guard.set_token()
        self.assertIn("read back", str(caught.exception))


class TestLinuxTokenNeverExposed(GuardTestCase):
    def test_the_token_reaches_the_header_and_nothing_else_on_linux(self):
        self.token_patcher.stop()                      # use the real read_token
        self.addCleanup(self.token_patcher.start)
        fake_proc = mock.Mock(returncode=0, stdout=(TOKEN + "\n").encode("utf-8"), stderr=b"")
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard.shutil, "which", return_value="/usr/bin/secret-tool"), \
                mock.patch.object(guard.subprocess, "run", return_value=fake_proc), \
                mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, output = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)
        self.assertNotIn(TOKEN, self.log_text())
        self.assertNotIn(TOKEN, output)
        self.assertEqual(urlopen.call_args[0][0].get_header("Authorization"), "Bearer " + TOKEN)


if __name__ == "__main__":
    unittest.main()
