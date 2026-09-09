#!/usr/bin/env python3
"""Tests for canvas_api_guard. Stdlib unittest only: python3 -m unittest -v

Every test that touches the request path replaces urllib.request.urlopen, so the suite
never reaches the network. Two tests prove that directly.
"""

import argparse
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

import canvas_api_guard as guard

TOKEN = "SECRET-TOKEN-DO-NOT-LEAK-9d41"
HOST = "canvas.example.edu"

OPERATIONS_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "level2",
                                 "canvas_api_operations.py")


def load_operations():
    """Load the Level 2 program from the source tree, the way its own tests do."""
    spec = importlib.util.spec_from_file_location("canvas_api_operations", OPERATIONS_SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subcommand_names(parser):
    """Every subcommand an argparse parser accepts. The rules matrix is driven from this, so a
    command nobody classified cannot slip through."""
    names = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.extend(action.choices)
    return sorted(set(names))


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


class FakeStdout(io.StringIO):
    """Captured stdout that can claim to be a terminal, so the guard's -o default applies."""

    def __init__(self, is_tty):
        io.StringIO.__init__(self)
        self.is_tty = is_tty

    def isatty(self):
        return self.is_tty


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        guard._SOURCE = None
        self.state_dir = tempfile.mkdtemp(prefix="cag-test-state-")
        os.chmod(self.state_dir, 0o700)
        self.addCleanup(shutil.rmtree, self.state_dir, True)
        self.log_path = os.path.join(self.state_dir, "audit.jsonl")
        with open(self.log_path, "w"):
            pass
        os.chmod(self.log_path, 0o600)
        self.log_patch = mock.patch.object(guard, "DEFAULT_LOG", self.log_path)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.config_path = self.temp_config(HOST)
        self.pin_config(self.config_path)
        # a token that must never appear in the log or on stdout
        self.token_patcher = mock.patch.object(guard, "read_token", lambda: TOKEN)
        self.token_patcher.start()
        self.addCleanup(self.token_patcher.stop)

    def temp_config(self, host=None, profile="level-1"):
        """A private throwaway system config; never the real installed config."""
        path = os.path.join(self.state_dir, "config-%d.json" % len(os.listdir(self.state_dir)))
        if host is not None:
            with open(path, "w") as handle:
                json.dump({"host": host, "profile": profile}, handle)
            os.chmod(path, 0o600)
        return path

    def pin_config(self, path):
        patcher = mock.patch.object(guard, "CONFIG_PATH", path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, argv, stdin_is_tty=False, stdout_is_tty=True):
        """Run main() with private fixed config/log paths and captured output."""
        return self.run_argv(list(argv), stdin_is_tty, stdout_is_tty)

    def run_argv(self, argv, stdin_is_tty=False, stdout_is_tty=True):
        """Run main() on exactly this argv, with the same patches run_main uses."""
        out, err = FakeStdout(stdout_is_tty), io.StringIO()
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


class TestFixedProductionConfig(GuardTestCase):
    """The host and audit destination are fixed outside the agent-controlled arguments."""

    def no_keychain(self):
        def explode():
            raise AssertionError("the credential store was touched before the refusal")
        return mock.patch.object(guard, "read_token", explode)

    def no_network(self):
        def explode(*args, **kwargs):
            raise AssertionError("a request was made before the refusal")
        return mock.patch("urllib.request.urlopen", side_effect=explode)

    def test_no_configured_host_refuses_a_real_request(self):
        self.pin_config(self.temp_config())                  # path does not exist
        with self.no_keychain(), self.no_network():
            code, _ = self.run_argv(["get", "courses"])
        self.assertEqual(code, 2)
        self.assertIn("no Canvas configuration", self.last_stderr)
        self.assertEqual([line for line in self.log_lines() if line["event"] == "request"], [])

    def test_the_fixed_host_and_log_are_used(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_argv(["get", "courses/1"])
        self.assertEqual(code, 0)
        self.assertTrue(urlopen.call_args[0][0].full_url.startswith("https://" + HOST + "/"),
                        urlopen.call_args[0][0].full_url)
        self.assertTrue(self.log_lines())

    def test_a_group_writable_config_is_refused(self):
        os.chmod(self.config_path, 0o620)
        with self.no_keychain(), self.no_network():
            code, _ = self.run_argv(["get", "courses"])
        self.assertEqual(code, 2)
        self.assertIn("not writable by group or others", self.last_stderr)

    def test_a_symlinked_config_is_refused(self):
        link = os.path.join(self.state_dir, "config-link.json")
        os.symlink(self.config_path, link)
        self.pin_config(link)
        with self.no_keychain(), self.no_network():
            code, _ = self.run_argv(["get", "courses"])
        self.assertEqual(code, 2)
        self.assertIn("regular file, not a link", self.last_stderr)

    def test_a_group_writable_config_directory_is_refused(self):
        os.chmod(self.state_dir, 0o770)
        with self.no_keychain(), self.no_network():
            code, _ = self.run_argv(["get", "courses"])
        self.assertEqual(code, 2)
        self.assertIn("configuration directory", self.last_stderr)
        self.assertIn("not writable by group or others", self.last_stderr)

    def test_an_unknown_profile_is_refused(self):
        self.pin_config(self.temp_config(HOST, profile="not-a-profile"))
        with self.no_keychain(), self.no_network():
            code, _ = self.run_argv(["get", "courses"])
        self.assertEqual(code, 2)
        self.assertIn("unsupported policy profile", self.last_stderr)

    def test_the_level_2_profile_keeps_level_1_available(self):
        self.pin_config(self.temp_config(HOST, profile="level-2"))
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_argv(["get", "courses/1"])
        self.assertEqual(code, 0)


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
            urlopen.return_value = FakeResponse(payload={"id": 7, "grade": "88",
                                                          "entered_grade": "88",
                                                          "score": 88.0, "entered_score": 88.0})
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
            urlopen.return_value = FakeResponse(payload={"id": 3, "grade": "95",
                                                          "entered_grade": "95",
                                                          "score": 95.0, "entered_score": 95.0})
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
            urlopen.return_value = FakeResponse(payload={"id": 3, "grade": "95",
                                                          "entered_grade": "95",
                                                          "score": 95.0, "entered_score": 95.0})
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

    def test_json_output_keeps_the_confirmation_preamble_off_stdout(self):
        """Under -o json stdout is machine-read: the preamble a person needs goes to stderr."""
        graded = {"id": 3, "grade": "95", "entered_grade": "95", "score": 95.0,
                  "entered_score": 95.0}
        responses = [FakeResponse(payload=dict(graded, grade="60", entered_grade="60",
                                               score=60.0, entered_score=60.0)),
                     FakeResponse(payload=graded), FakeResponse(payload=graded)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes", "-o", "json",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["verification"], "passed")
        self.assertIn("about to PUT", self.last_stderr)
        self.assertIn("requested changes", self.last_stderr)
        self.assertIn("confirmation: --yes was passed explicitly", self.last_stderr)

    def test_text_output_still_shows_the_preamble_on_stdout(self):
        graded = {"id": 3, "grade": "95", "entered_grade": "95", "score": 95.0,
                  "entered_score": 95.0}
        with mock.patch("urllib.request.urlopen",
                        side_effect=[FakeResponse(payload=graded)] * 3):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes", "-o", "text",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertIn("about to PUT", output)
        self.assertIn("confirmation: --yes was passed explicitly", output)


class TestLogBeforeRequest(GuardTestCase):
    def test_the_write_request_line_is_on_disk_before_urlopen_is_called(self):
        seen = {}

        def inspect_the_log(request, timeout=None):
            if request.get_method() != "PUT":
                return FakeResponse(payload={"id": 3, "grade": "60", "score": 60.0})
            # runs INSIDE urlopen: whatever is in the log now was written beforehand
            seen["lines"] = self.log_lines()
            raise OSError("no network in tests")

        with mock.patch("urllib.request.urlopen", side_effect=inspect_the_log):
            code, _ = self.run_main(["put", "courses/1/assignments/2/submissions/3", "--yes",
                                     "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 3)          # a transport failure on a write may have applied it
        self.assertEqual([line["event"] for line in seen["lines"]], ["read", "request"])
        self.assertEqual(seen["lines"][-1]["verb"], "PUT")
        self.assertEqual(seen["lines"][-1]["path"], "/api/v1/courses/1/assignments/2/submissions/3")
        self.assertEqual(seen["lines"][-1]["request_body"], {"submission": {"posted_grade": 95}})

    def test_a_failed_write_still_leaves_its_request_line(self):
        responses = [FakeResponse(payload={"id": 3, "grade": "60", "score": 60.0}),
                     OSError("no network in tests")]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["put", "courses/1/assignments/2/submissions/3", "--yes",
                                     "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 3)
        events = [(line["event"], line.get("verb")) for line in self.log_lines()]
        self.assertEqual(events, [("read", "GET"), ("request", "PUT"), ("response", "PUT"),
                                  ("evidence", "PUT")])
        self.assertFalse(self.log_lines()[2]["ok"])
        self.assertEqual(self.log_lines()[2]["error"], "OSError")

    def test_a_read_is_one_line_written_after_the_response(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)
        lines = self.log_lines()
        self.assertEqual([line["event"] for line in lines], ["read"])
        self.assertEqual(lines[0]["verb"], "GET")
        self.assertEqual(lines[0]["path"], "/api/v1/courses/1")
        self.assertEqual(lines[0]["status"], 200)
        self.assertTrue(lines[0]["ok"])
        self.assertEqual(lines[0]["bytes"], len(json.dumps({"id": 1})))
        self.assertNotIn("timing_ms", self.log_text())

    def test_a_write_keeps_its_three_lines_and_its_read_backs_keep_one_each(self):
        graded = {"id": 3, "user_id": 3, "grade": "95", "entered_grade": "95",
                  "score": 95.0, "entered_score": 95.0}
        responses = [FakeResponse(payload=dict(graded, grade="60", entered_grade="60",
                                               score=60.0, entered_score=60.0)),
                     FakeResponse(payload=graded), FakeResponse(payload=graded)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["put", "courses/1/assignments/2/submissions/3", "--yes",
                                     "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertEqual([(line["event"], line["verb"]) for line in self.log_lines()],
                         [("read", "GET"), ("request", "PUT"), ("response", "PUT"),
                          ("read", "GET"), ("evidence", "PUT")])

    def test_the_log_file_and_its_directory_are_created_private(self):
        """The fixed audit path is created with private directory and file modes."""
        parent = tempfile.mkdtemp(prefix="cag-test-logdir-")
        self.addCleanup(shutil.rmtree, parent, True)
        directory = os.path.join(parent, "sub")
        log_path = os.path.join(directory, "audit.jsonl")
        with mock.patch.object(guard, "DEFAULT_LOG", log_path), \
                mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_argv(["get", "courses/1"])
        self.assertEqual(code, 0)
        self.assertEqual(os.stat(log_path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)

    def test_an_insecure_existing_log_is_refused(self):
        os.chmod(self.log_path, 0o644)
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 2)
        self.assertIn("mode 0600", self.last_stderr)
        urlopen.assert_not_called()

    def test_a_symlinked_audit_directory_is_refused(self):
        parent = tempfile.mkdtemp(prefix="cag-test-loglink-")
        self.addCleanup(shutil.rmtree, parent, True)
        real_dir = os.path.join(parent, "real")
        link_dir = os.path.join(parent, "link")
        os.mkdir(real_dir, 0o700)
        os.symlink(real_dir, link_dir)
        with mock.patch.object(guard, "DEFAULT_LOG", os.path.join(link_dir, "audit.jsonl")), \
                mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_argv(["get", "courses/1"])
        self.assertEqual(code, 2)
        self.assertIn("real directory", self.last_stderr)
        urlopen.assert_not_called()


class TestTokenIsNeverExposed(GuardTestCase):
    def test_the_token_is_absent_from_the_log_and_from_stdout(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 3, "grade": "95",
                                                          "entered_grade": "95",
                                                          "score": 95.0, "entered_score": 95.0})
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


class TestDryRunOutput(GuardTestCase):
    """Under -o json stdout is machine-read, so a dry run is one JSON object there too - not
    four lines of prose in front of one. Text output is for a person and does not change."""

    def test_a_json_dry_run_is_one_object_and_never_reads_the_token(self):
        def explode():
            raise AssertionError("--dry-run must not read the token")

        with mock.patch.object(guard, "read_token", explode), \
                mock.patch("urllib.request.urlopen") as urlopen:
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--dry-run", "-o", "json",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        shown = json.loads(output)                       # the whole of stdout, once
        self.assertIs(shown["dry_run"], True)
        self.assertEqual(shown["method"], "PUT")
        self.assertEqual(shown["url"],
                         "https://" + HOST + "/api/v1/courses/1/assignments/2/submissions/3")
        self.assertEqual(shown["headers"]["Authorization"], guard.REDACTED)
        self.assertEqual(shown["body"], {"submission": {"posted_grade": 95}})
        self.assertNotIn(TOKEN, output)
        self.assertNotIn(TOKEN, self.log_text())

    def test_a_json_dry_run_read_is_one_object_too(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, output = self.run_main(["get", "courses/1", "--dry-run", "-o", "json"])
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        self.assertEqual(json.loads(output)["method"], "GET")

    def test_the_text_dry_run_is_unchanged(self):
        with mock.patch("urllib.request.urlopen"):
            code, output = self.run_main(["get", "courses/1", "--dry-run", "-o", "text"])
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN - nothing is sent and no token is read", output)
        self.assertIn("  header   Authorization: Bearer <redacted>", output)
        self.assertIn("  body     (none)", output)


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
        student = {"id": 3, "name": "Student Example"}
        graded = {"id": 3, "user_id": 3, "user": student, "grade": "95",
                  "entered_grade": "95", "score": 95.0, "entered_score": 95.0,
                  "excused": False, "workflow_state": "graded"}
        ungraded = dict(graded, grade="60", entered_grade="60", score=60.0,
                        entered_score=60.0)
        responses = [FakeResponse(payload=ungraded),                       # before
                     FakeResponse(payload=dict(graded, user=None)),        # the write
                     FakeResponse(payload=graded)]                         # read-back
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertIn("posted_grade (read entered_score)", output)
        self.assertIn("60.0 -> 95.0", output)
        self.assertIn("match: True", output)
        self.assertIn("Student Example", output)
        evidence = [line for line in self.log_lines() if line["event"] == "evidence"][-1]
        self.assertEqual(evidence["target"], {"student_name": "Student Example", "user_id": 3})
        self.assertEqual(evidence["verification"], "passed")

    def test_pass_fail_grades_match_canvas_complete_incomplete(self):
        """Canvas records posted_grade "pass"/"fail" as entered_grade "complete"/"incomplete"."""
        self.assertTrue(guard.compare_fields({"submission": {"posted_grade": "pass"}}, {},
                                             {"entered_grade": "complete"})[0]["match"])
        self.assertTrue(guard.compare_fields({"submission": {"posted_grade": "fail"}}, {},
                                             {"entered_grade": "incomplete"})[0]["match"])
        self.assertFalse(guard.compare_fields({"submission": {"posted_grade": "pass"}}, {},
                                              {"entered_grade": "incomplete"})[0]["match"])

    def test_before_and_after_are_read_from_the_same_field(self):
        """The before object may lack the field the after object proved the grade with;
        honestly report no before value rather than one read from a different field."""
        rows = guard.compare_fields({"submission": {"posted_grade": 95}},
                                    {"score": 60.0},
                                    {"entered_score": 95.0, "score": 95.0})
        self.assertEqual(rows[0]["read_field"], "entered_score")
        self.assertIsNone(rows[0]["before"])

    def test_a_numeric_posted_grade_is_proved_by_the_score_canvas_recorded(self):
        """Canvas rounds a score to two decimals; canvas-cli's verifyGradeReadBack allows it."""
        rows = guard.compare_fields({"submission": {"posted_grade": 95}},
                                    {"grade": "60", "score": 60.0, "entered_score": 60.0},
                                    {"grade": "95", "score": 94.999, "entered_score": 94.999})
        self.assertEqual(rows, [{"field": "posted_grade", "read_field": "entered_score",
                                 "requested": 95, "before": 60.0, "after": 94.999,
                                 "match": True}])

    def test_a_letter_posted_grade_is_proved_by_the_grade_canvas_recorded(self):
        rows = guard.compare_fields({"submission": {"posted_grade": "A-"}}, {},
                                    {"entered_grade": "a-", "grade": "a-", "score": 91.0})
        self.assertEqual(rows[0]["read_field"], "entered_grade")
        self.assertTrue(rows[0]["match"])

    def test_a_grade_canvas_did_not_record_is_still_a_mismatch(self):
        rows = guard.compare_fields({"submission": {"posted_grade": 95}}, {},
                                    {"grade": "60", "score": 60.0})
        self.assertFalse(rows[0]["match"])

    def test_submission_excuse_verifies_canvas_excused_response_field(self):
        responses = [FakeResponse(payload={"id": 3, "user_id": 3, "excused": False}),
                     FakeResponse(payload={"id": 3, "user_id": 3, "excused": True}),
                     FakeResponse(payload={"id": 3, "user_id": 3, "excused": True})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"excuse": true}}'])
        self.assertEqual(code, 0)
        self.assertIn("false -> true", output.lower())

    def test_post_without_an_id_or_location_is_uncertain_and_nonzero(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(status=201, headers={}, payload={"ok": True})
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 3)
        self.assertIn("neither an id nor a usable Location header", output)
        self.assertIn("WRITE STATUS UNCERTAIN", output)

    def test_a_post_to_an_off_host_location_is_refused_and_uncertain(self):
        """The create was sent, so a Location pointing elsewhere is uncertain, not a refusal -
        and the guard reads back nothing at all rather than following it."""
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(
                status=201, headers={"Location": "https://evil.example.com/api/v1/x"},
                payload={"ok": True})
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertIn("evil.example.com", self.last_stderr)
        self.assertEqual(urlopen.call_count, 1)          # the POST, and nothing after it

    def rubric_create(self, read_back):
        """One create-rubric POST, with the exact body Level 2's rubric_body() builds."""
        operations = load_operations()
        body = operations.rubric_body({"title": "Lab rubric", "criteria": [
            {"description": "Craft", "points": 10,
             "ratings": [{"description": "Complete", "points": 10},
                         {"description": "Incomplete", "points": 0}]}]})
        body["rubric_association"] = {"association_type": "Assignment", "association_id": 1,
                                      "purpose": "grading", "use_for_grading": True}
        responses = [FakeResponse(status=201, payload={"rubric": {"id": 42}}),
                     FakeResponse(payload=read_back)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            return self.run_main(["post", "courses/1/rubrics", "--yes", "-o", "json",
                                  "--created-id", "rubric.id", "-d", json.dumps(body)])

    CANVAS_RUBRIC = {"id": 42, "title": "Lab rubric", "free_form_criterion_comments": False,
                     "points_possible": 10,
                     "data": [{"id": "_1234", "description": "Craft", "points": 10,
                               "ratings": [{"description": "Complete", "points": 10},
                                           {"description": "Incomplete", "points": 0}]}]}

    def test_a_whole_create_rubric_body_verifies_on_the_leaves_canvas_exposes(self):
        code, output = self.rubric_create(self.CANVAS_RUBRIC)
        self.assertEqual(code, 0)
        rows = {row["field"]: row["match"] for row in json.loads(output)["changes"]}
        # ratings is an index-keyed hash now, so the guard descends into it: its leaves are
        # the same names as the criterion's, description and points
        self.assertEqual(rows, {"title": True, "description": None, "points": None,
                                "association_type": None, "purpose": None,
                                "association_id": None, "use_for_grading": None})

    def test_a_nested_leaf_the_created_object_happens_to_expose_still_fails_closed(self):
        """A criterion's "description" and a rubric's own top-level "description" are the same
        NAME. The rule is by name, so the collision is checked, and a contradiction fails."""
        code, output = self.rubric_create(dict(self.CANVAS_RUBRIC, description=None))
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN: created object did not match requested "
                      "field(s): description", output)

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

    def test_post_can_read_back_a_documented_nested_create_response(self):
        responses = [FakeResponse(status=201, payload={"rubric": {"id": 42, "title": "Lab"}}),
                     FakeResponse(payload={"id": 42, "title": "Lab", "data": []})]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            code, output = self.run_main(
                ["post", "courses/1/rubrics", "--yes", "--created-id", "rubric.id",
                 "-d", '{"rubric": {"title": "Lab"}}'])
        self.assertEqual(code, 0)
        self.assertIn("verification:  passed", output)
        self.assertEqual(urlopen.call_args[0][0].full_url,
                         "https://" + HOST + "/api/v1/courses/1/rubrics/42")

    def test_a_created_object_that_contradicts_the_body_is_uncertain(self):
        responses = [FakeResponse(status=201, payload={"id": 42, "name": "Lab 4"}),
                     FakeResponse(payload={"id": 42, "name": "Different name"})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertIn("created object did not match requested field", output)

    def test_a_created_id_the_response_does_not_carry_is_uncertain_not_a_refusal(self):
        """The POST was already sent by then, so an unresolvable --created-id cannot be an
        ordinary refusal: the object may exist and could not be read back."""
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(status=201, payload={"rubric": {"title": "Lab"}})
            code, output = self.run_main(
                ["post", "courses/1/rubrics", "--yes", "--created-id", "rubric.id",
                 "-d", '{"rubric": {"title": "Lab"}}'])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertIn("rubric.id", output)

    def test_created_id_is_a_post_only_flag(self):
        parser = guard.build_parser()
        parser.parse_args(["post", "courses/1/rubrics", "--created-id", "rubric.id"])
        with mock.patch("sys.stderr", io.StringIO()):
            for verb in ("get", "put", "patch", "delete"):
                with self.assertRaises(SystemExit):
                    parser.parse_args([verb, "courses/1", "--created-id", "id"])

    def test_a_put_body_that_is_not_a_json_object_is_refused_before_anything_is_sent(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, output = self.run_main(
                ["put", "courses/1/assignments/2", "--yes", "-d", '[1, 2]'])
        self.assertEqual(code, 2)
        urlopen.assert_not_called()
        self.assertNotIn("about to PUT", output)
        self.assertIn("JSON object", self.last_stderr)

    def test_a_single_item_list_is_not_reported_as_1_items(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=[{"id": 1}])
            code, output = self.run_main(["get", "courses"])
        self.assertEqual(code, 0)
        self.assertIn("1 item returned", output)
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=[{"id": 1}, {"id": 2}])
            code, output = self.run_main(["get", "courses"])
        self.assertEqual(code, 0)
        self.assertIn("2 items returned", output)

    def test_json_get_preserves_full_object_for_specialized_validation(self):
        payload = {"id": 2, "name": "Lab", "rubric_settings": {"id": 9,
                   "rubric_association_id": 10}, "field_1": 1, "field_2": 2,
                   "field_3": 3, "field_4": 4, "field_5": 5, "field_6": 6,
                   "field_7": 7, "field_8": 8, "field_9": 9}
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload=payload)):
            code, output = self.run_main(["get", "courses/1/assignments/2", "-o", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["object"]["rubric_settings"]["id"], 9)

    def test_delete_reports_that_the_object_is_gone(self):
        responses = [FakeResponse(payload={"id": 2, "name": "Lab 4"}),  # before
                     FakeResponse(status=200, payload={"id": 2}),       # the delete
                     urllib.error.HTTPError("https://" + HOST, 404, "Not Found", {}, None)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(["delete", "courses/1/assignments/2", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("read-back after delete: 404 gone", output)

    def test_update_readback_failure_is_uncertain_and_nonzero(self):
        responses = [FakeResponse(payload={"id": 3, "grade": "60", "score": 60.0,
                                           "entered_score": 60.0}),
                     FakeResponse(payload={"id": 3, "grade": "95", "score": 95.0,
                                           "entered_score": 95.0}),
                     OSError("network unavailable")]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertIn("read-back failed", output)

    def test_update_mismatch_is_uncertain_and_nonzero(self):
        responses = [FakeResponse(payload={"id": 3, "grade": "60", "score": 60.0,
                                           "entered_score": 60.0}),
                     FakeResponse(payload={"id": 3, "grade": "95", "score": 95.0,
                                           "entered_score": 95.0}),
                     FakeResponse(payload={"id": 3, "grade": "60", "score": 60.0,
                                           "entered_score": 60.0})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 3)
        self.assertIn("did not match", output)

    def test_delete_transport_failure_is_not_reported_as_gone(self):
        responses = [FakeResponse(payload={"id": 2, "name": "Lab 4"}),
                     FakeResponse(status=200, payload={"id": 2}),
                     OSError("network unavailable")]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(["delete", "courses/1/assignments/2", "--yes"])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertNotIn("404 gone", output)


class TestAFailedWriteRequest(GuardTestCase):
    """Canvas answering 4xx means it did not apply the write; anything else - a timeout, a
    transport error, a 5xx - may have applied it, and the outcome is uncertain."""

    def put(self, failure):
        responses = [FakeResponse(payload={"id": 3, "grade": "60", "score": 60.0,
                                           "entered_score": 60.0}), failure]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            return self.run_main(["put", "courses/1/assignments/2/submissions/3", "--yes",
                                  "-d", '{"submission": {"posted_grade": 95}}'])

    def evidence_lines(self):
        return [line for line in self.log_lines() if line["event"] == "evidence"]

    def test_a_timed_out_write_is_uncertain_with_an_evidence_line(self):
        code, output = self.put(TimeoutError("timed out"))
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertEqual(len(self.evidence_lines()), 1)

    def test_a_5xx_write_is_uncertain(self):
        error = urllib.error.HTTPError("https://" + HOST, 500, "Server Error", {}, None)
        code, output = self.put(error)
        error.close()
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertEqual(len(self.evidence_lines()), 1)

    def test_a_4xx_write_stays_a_plain_failure_with_no_evidence_line(self):
        error = urllib.error.HTTPError("https://" + HOST, 403, "Forbidden", {}, None)
        code, output = self.put(error)
        error.close()
        self.assertEqual(code, 2)
        self.assertNotIn("WRITE STATUS UNCERTAIN", output)
        self.assertEqual(self.evidence_lines(), [])
        self.assertIn("403", self.last_stderr)


class TestOneVerificationRule(GuardTestCase):
    """One rule for every write, POST and PUT/PATCH alike: a requested leaf the read-back
    object exposes must match; a leaf it does not expose is reported with a null match and
    cannot fail; if it exposed none of them, nothing about the write could be verified."""

    def test_a_leaf_the_created_object_does_not_expose_is_null_not_a_failure(self):
        created = {"id": 42, "title": "Lab"}
        responses = [FakeResponse(status=201, payload=created), FakeResponse(payload=created)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["post", "courses/1/rubrics", "--yes", "-o", "json",
                 "-d", '{"title": "Lab", "association_type": "Course"}'])
        self.assertEqual(code, 0)
        self.assertEqual({row["field"]: row["match"] for row in json.loads(output)["changes"]},
                         {"title": True, "association_type": None})

    def test_a_write_whose_read_back_exposes_no_requested_leaf_is_uncertain(self):
        created = {"id": 42}
        responses = [FakeResponse(status=201, payload=created), FakeResponse(payload=created)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["post", "courses/1/rubrics", "--yes", "-d", '{"title": "Lab"}'])
        self.assertEqual(code, 3)
        self.assertIn("nothing about the write could be verified", output)
        self.assertIn("WRITE STATUS UNCERTAIN", output)

    def test_an_unexposed_leaf_does_not_fail_a_put_whose_grade_verified(self):
        graded = {"id": 3, "grade": "95", "entered_grade": "95", "score": 95.0,
                  "entered_score": 95.0}
        with mock.patch("urllib.request.urlopen",
                        side_effect=[FakeResponse(payload=graded)] * 3):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes", "-o", "json",
                 "-d", '{"submission": {"posted_grade": 95}, "rubric_assessment": '
                       '{"criterion_1": {"points": 8}}}'])
        self.assertEqual(code, 0)
        self.assertEqual({row["field"]: row["match"] for row in json.loads(output)["changes"]},
                         {"posted_grade": True, "points": None})

    def test_a_leaf_the_object_exposes_and_contradicts_still_fails(self):
        graded = {"id": 3, "grade": "60", "entered_grade": "60", "score": 60.0,
                  "entered_score": 60.0}
        with mock.patch("urllib.request.urlopen",
                        side_effect=[FakeResponse(payload=graded)] * 3):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 3)
        self.assertIn("read-back did not match requested field(s): posted_grade", output)


class TestRedirectsAreRefused(unittest.TestCase):
    @staticmethod
    def urllib_prepared(request):
        """Run the stdlib step that adds Host as an unredirected header before sending."""
        opener = urllib.request.build_opener()
        https = next(handler for handler in opener.handlers
                     if isinstance(handler, urllib.request.HTTPSHandler))
        return https.do_request_(request)

    """urllib forwards the Authorization header across a redirect, to another host or an
    http:// downgrade included. Every redirect is refused instead, so the URL that carries
    the token is always the one canvas_url() built."""

    def redirect_to(self, newurl, code=302):
        request = urllib.request.Request("https://%s/api/v1/courses" % HOST)
        return guard.RefuseRedirects().redirect_request(request, None, code, "Found", {}, newurl)

    def test_a_redirect_to_another_host_is_refused_and_names_the_url(self):
        with self.assertRaises(guard.GuardError) as caught:
            self.redirect_to("http://attacker.example.com/x")
        self.assertIn("attacker.example.com", str(caught.exception))
        self.assertIn("redirect", str(caught.exception))

    def test_a_redirect_on_the_pinned_host_is_refused_too(self):
        with self.assertRaises(guard.GuardError) as caught:
            self.redirect_to("https://%s/api/v1/courses?page=2" % HOST, code=301)
        self.assertIn(HOST, str(caught.exception))

    def test_the_refusing_opener_is_the_installed_one(self):
        opener = urllib.request._opener
        self.assertIsNotNone(opener)
        self.assertTrue(any(isinstance(handler, guard.RefuseRedirects)
                            for handler in opener.handlers))

    def test_no_attachment_hop_carries_a_credential_or_a_stale_host(self):
        """The first hop carries none of these, so no hop may reintroduce one."""
        handler = guard.AttachmentRedirects(HOST, [])
        prepared = self.urllib_prepared(
            urllib.request.Request("https://%s/files/9/download" % HOST))
        self.assertIn("host", {name.lower() for name, _ in prepared.header_items()})
        supplied = urllib.request.Request("https://%s/files/9/download" % HOST, headers={
            "Authorization": "Bearer must-not-leave-canvas", "Cookie": "not-forwarded",
            "Host": "stale.example.edu", "Proxy-Authorization": "Basic not-forwarded",
            "User-Agent": "canvas-api-guard-test"})
        for request in (prepared, supplied):
            for destination in ("https://%s/files/9/again" % HOST,
                                "https://cdn.example.edu/file"):
                with self.subTest(destination=destination):
                    redirected = handler.redirect_request(
                        request, None, 302, "Found", {}, destination)
                    sent = {name.lower() for name, _ in redirected.header_items()}
                    self.assertEqual(sent & {"authorization", "cookie", "host",
                                             "proxy-authorization"}, set())
        self.assertEqual(dict(supplied.header_items()).get("User-agent"),
                         "canvas-api-guard-test")

    def test_a_non_https_attachment_redirect_is_refused(self):
        request = urllib.request.Request("https://%s/files/9/download" % HOST)
        with self.assertRaises(guard.GuardError):
            guard.AttachmentRedirects(HOST, []).redirect_request(
                request, None, 302, "Found", {}, "http://cdn.example.edu/file")

    def test_attachment_redirect_trace_has_only_status_hostname_and_scope(self):
        trace = []
        request = urllib.request.Request("https://%s/files/9/download" % HOST)
        guard.AttachmentRedirects(HOST, trace).redirect_request(
            request, None, 307, "Temporary Redirect", {},
            "https://cdn.example.edu/file?signature=do-not-log")
        self.assertEqual(trace, [{"status": 307, "host": "cdn.example.edu",
                                  "scope": "external"}])
        self.assertNotIn("signature", json.dumps(trace))

    def test_the_guard_keeps_exactly_one_credential_free_opener(self):
        """The dead credential-free opener and its parameter are gone."""
        self.assertFalse(hasattr(guard, "CredentialFreeRedirects"))
        self.assertFalse(hasattr(guard, "_CREDENTIAL_FREE_OPENER"))
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "canvas_api_guard.py")) as handle:
            source = handle.read()
        self.assertEqual(source.count("urllib.request.urlopen("), 1)
        self.assertNotIn("credential_free_redirects", source)

    def test_attachment_download_error_records_status_not_signed_url(self):
        signed_url = "https://cdn.example.edu/file?X-Amz-Signature=do-not-log"
        error = urllib.error.HTTPError(signed_url, 403, "Forbidden", {}, None)
        failure = guard.safe_download_failure(error)
        error.close()
        self.assertEqual(failure, {"error": "HTTPError", "http_status": 403,
                                   "response_host": "cdn.example.edu"})
        self.assertNotIn("X-Amz-Signature", json.dumps(failure))
        self.assertIsNone(guard.safe_download_failure(OSError("unavailable"))["http_status"])


class TestEdgeSeam(GuardTestCase):
    """The seven names an importing edge replaces. read_token, confirm, check_provenance,
    CONFIG_PATH, DEFAULT_LOG, and REVIEW_DIR are each looked up on the module at call time, so
    replacing one changes what the guard does; build_opener is called once at import instead, so
    an edge installs its own opener with urllib.request.install_opener rather than replacing the
    name. Nothing else about the host path moves."""

    SEAM = ("read_token", "confirm", "check_provenance", "CONFIG_PATH", "DEFAULT_LOG",
            "REVIEW_DIR", "build_opener")

    def test_the_seam_names_exist_and_are_named_in_the_header(self):
        for name in self.SEAM:
            self.assertTrue(hasattr(guard, name), name)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_api_guard.py")) as handle:
            header = handle.read().split("import argparse")[0]
        self.assertIn("EDGE SEAM", header)
        for name in self.SEAM:
            self.assertIn(name, header, "%s is not named in the header's edge seam paragraph" % name)

    def test_the_installed_opener_refuses_redirects_and_uses_no_environment_proxy(self):
        # A ProxyHandler built with an explicit {} registers no protocol hooks, so the stdlib
        # OpenerDirector never lists it in .handlers - inspect what build_opener() constructs
        # with instead, the same way test_attachment_opener_disables_proxy_use does.
        opener = urllib.request._opener
        self.assertTrue(any(isinstance(h, guard.RefuseRedirects) for h in opener.handlers))
        with mock.patch("urllib.request.build_opener") as build:
            guard.build_opener()
        handlers = build.call_args[0]
        proxy = next(h for h in handlers if isinstance(h, urllib.request.ProxyHandler))
        self.assertEqual(proxy.proxies, {})
        self.assertIn(guard.RefuseRedirects, handlers)

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
            return "edge:test"
        responses = [FakeResponse(payload={"id": 1, "name": "A"}),
                     FakeResponse(payload={"id": 1, "name": "X"}),
                     FakeResponse(payload={"id": 1, "name": "X"})]
        with mock.patch.object(guard, "confirm", approve), \
                mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["put", "courses/1", "--yes",
                                     "-d", '{"course": {"name": "X"}}'])
        self.assertEqual(code, 0)
        self.assertEqual([l["confirmation"] for l in self.log_lines() if l["event"] == "request"],
                         ["edge:test"])

    def test_the_path_seam_is_read_at_call_time(self):
        """DEFAULT_LOG and REVIEW_DIR are looked up when they are used, not captured once at
        import - an edge that patches them after import still lands its log lines and its
        review directory in the patched locations."""
        log_path = os.path.join(self.state_dir, "edge-audit.jsonl")
        with open(log_path, "w"):
            pass
        os.chmod(log_path, 0o600)
        review_dir = os.path.join(self.state_dir, "edge-reviews")
        with mock.patch.object(guard, "DEFAULT_LOG", log_path), \
                mock.patch.object(guard, "REVIEW_DIR", review_dir), \
                mock.patch("urllib.request.urlopen",
                          return_value=FakeResponse(payload={"id": 1})):
            code, _ = self.run_main(["get", "courses/1"])
            self.assertEqual(code, 0)
            self.assertEqual(guard.secure_review_dir(), review_dir)
        with open(log_path) as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        self.assertTrue(lines)
        self.assertEqual(lines[-1]["event"], "read")


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


class TestAttachmentDownload(GuardTestCase):
    def test_attachment_opener_disables_proxy_use(self):
        request = urllib.request.Request("https://%s/files/9/download" % HOST)
        trace = []
        captured = {}

        class Opener(object):
            def open(self, actual_request, timeout):
                captured.update({"request": actual_request, "timeout": timeout})
                return io.BytesIO(b"")

        with mock.patch("urllib.request.build_opener", return_value=Opener()) as build:
            guard.open_attachment_request(request, HOST, trace)
        handlers = build.call_args[0]
        proxy = next(handler for handler in handlers if isinstance(handler, urllib.request.ProxyHandler))
        self.assertEqual(proxy.proxies, {})
        self.assertIs(captured["request"], request)
        self.assertEqual(captured["timeout"], guard.TIMEOUT)

    def test_download_uses_file_url_without_a_token(self):
        cfg = type("Config", (), {"log_path": self.log_path, "out": "json", "host": HOST,
                            "dry_run": False, "dry_run_request": None})()
        file_url = "https://%s/files/9/download?verifier=not-for-output" % HOST
        with mock.patch.object(guard, "send_request", return_value={"data": {"url": file_url}}) as send, \
                mock.patch.object(guard, "secure_review_dir", return_value=self.state_dir), \
                mock.patch.object(guard, "open_attachment_request", return_value=io.BytesIO(b"student work")) as open_it, \
                mock.patch("sys.stdout", io.StringIO()):
            guard.do_download_submission_file(cfg, "7", "9", "12", ".pdf")
        self.assertEqual(send.call_args[0][1:], ("GET", "files/9"))
        request = open_it.call_args[0][0]
        self.assertEqual(request.full_url, file_url)
        self.assertNotIn("authorization", {key.lower() for key, _ in request.header_items()})
        self.assertEqual([line for line in self.log_lines() if line["event"] == "evidence"], [])
        logged = [line for line in self.log_lines() if line["event"] == "download-response"][-1]
        self.assertEqual((logged["file_id"], logged["ok"]), ("9", True))

    def test_download_retries_one_transient_server_error_with_a_fresh_file_url(self):
        cfg = type("Config", (), {"log_path": self.log_path, "out": "json", "host": HOST,
                            "dry_run": False, "dry_run_request": None})()
        file_url = "https://%s/files/9/download?verifier=not-for-output" % HOST
        transient = urllib.error.HTTPError(file_url, 500, "Server Error", {}, None)
        with mock.patch.object(guard, "send_request", return_value={"data": {"url": file_url}}) as send, \
                mock.patch.object(guard, "secure_review_dir", return_value=self.state_dir), \
                mock.patch.object(guard, "open_attachment_request", side_effect=[transient, io.BytesIO(b"student work")]) as open_it, \
                mock.patch("sys.stdout", io.StringIO()):
            guard.do_download_submission_file(cfg, "7", "9", "12", ".pdf")
        transient.close()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(open_it.call_count, 2)
        responses = [line for line in self.log_lines() if line["event"] == "download-response"]
        self.assertTrue(responses[0]["will_retry"])
        self.assertEqual(responses[0]["next_route"], "file-url")
        self.assertEqual(responses[-1]["attempt"], 2)
        self.assertTrue(responses[-1]["ok"])

    def test_download_uses_submission_public_url_only_after_two_file_url_5xx_failures(self):
        cfg = type("Config", (), {"log_path": self.log_path, "out": "json", "host": HOST,
                            "dry_run": False, "dry_run_request": None})()
        file_url = "https://%s/files/9/download?verifier=not-for-output" % HOST
        public_url = "https://cdn.example.edu/submission-file?signature=not-for-output"
        first = urllib.error.HTTPError(file_url, 500, "Server Error", {}, None)
        second = urllib.error.HTTPError(file_url, 500, "Server Error", {}, None)
        responses = [{"data": {"url": file_url}}, {"data": {"url": file_url}},
                     {"data": {"public_url": public_url}}]
        with mock.patch.object(guard, "send_request", side_effect=responses) as send, \
                mock.patch.object(guard, "secure_review_dir", return_value=self.state_dir), \
                mock.patch.object(guard, "open_attachment_request",
                                  side_effect=[first, second, io.BytesIO(b"student work")]) as open_it, \
                mock.patch("sys.stdout", io.StringIO()):
            guard.do_download_submission_file(cfg, "7", "9", "12", ".pdf")
        first.close(); second.close()
        self.assertEqual(send.call_args_list[-1][0][1:], ("GET", "files/9/public_url?submission_id=12"))
        self.assertEqual(open_it.call_args_list[-1][0][0].full_url, public_url)
        logged = [line for line in self.log_lines() if line["event"] == "download-response"]
        self.assertEqual(logged[1]["next_route"], "submission-public-url")
        self.assertEqual(logged[-1]["download_route"], "submission-public-url")

    def test_a_download_failure_names_the_reason_and_never_a_signed_url(self):
        cfg = type("Config", (), {"log_path": self.log_path, "out": "json", "host": HOST,
                            "dry_run": False, "dry_run_request": None})()
        refusal = "Canvas did not return a usable HTTPS submission download URL"
        with mock.patch.object(guard, "send_request", side_effect=guard.GuardError(refusal)), \
                mock.patch.object(guard, "secure_review_dir", return_value=self.state_dir), \
                mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(guard.GuardError) as caught:
                guard.do_download_submission_file(cfg, "7", "9", "12", ".pdf")
        self.assertIn("download failed", str(caught.exception))
        self.assertIn(refusal, str(caught.exception))
        self.assertNotIn("https://", str(caught.exception))

    def test_an_oserror_making_the_review_directory_is_one_line_not_a_traceback(self):
        missing = os.path.join(self.state_dir, "submission-reviews")
        with mock.patch.object(guard, "REVIEW_DIR", missing), \
                mock.patch.object(guard.os, "makedirs",
                                  side_effect=PermissionError(13, "Permission denied")), \
                mock.patch("urllib.request.urlopen") as urlopen:
            code, output = self.run_main(["download-submission-file", "--course-id", "7",
                                          "--file-id", "9", "--submission-id", "12",
                                          "--suffix", ".pdf"])
        self.assertEqual(code, 2)
        urlopen.assert_not_called()
        self.assertEqual(output, "")
        self.assertEqual(len(self.last_stderr.strip().splitlines()), 1)
        self.assertIn("canvas-api-guard:", self.last_stderr)

    def test_every_download_attempt_closes_its_response(self):
        cfg = type("Config", (), {"log_path": self.log_path, "out": "json", "host": HOST,
                            "dry_run": False, "dry_run_request": None})()
        file_url = "https://%s/files/9/download?verifier=not-for-output" % HOST
        closed = []

        class Body(io.BytesIO):
            def close(self):
                closed.append(True)
                io.BytesIO.close(self)

        with mock.patch.object(guard, "send_request",
                               return_value={"data": {"url": file_url}}), \
                mock.patch.object(guard, "secure_review_dir", return_value=self.state_dir), \
                mock.patch.object(guard, "open_attachment_request",
                                  return_value=Body(b"student work")), \
                mock.patch("sys.stdout", io.StringIO()):
            guard.do_download_submission_file(cfg, "7", "9", "12", ".pdf")
        self.assertEqual(closed, [True])


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
                mock.patch.object(guard, "trusted_linux_secret_tool",
                                  return_value="/usr/bin/secret-tool"):
            self.assertEqual(guard.read_token(), TOKEN)
        argv, _ = self.calls[0]
        self.assertEqual(argv[:2], ["/usr/bin/secret-tool", "lookup"])
        self.assertIn(guard.KEYCHAIN_SERVICE, argv)

    def test_linux_without_secret_tool_refuses_and_names_the_package(self):
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard, "trusted_linux_secret_tool",
                                  side_effect=guard.GuardError("secret-tool libsecret missing")):
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

    def test_set_token_on_macos_sends_the_secret_twice_over_stdin_and_reads_it_back(self):
        """security(1) asks for a new item's password and a retype; both go over stdin, the
        token never appears in argv, and the stored item is read back and compared."""
        with mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True), \
                mock.patch.object(guard.sys.stdin, "isatty", return_value=True), \
                mock.patch.object(guard.getpass, "getpass", return_value=" " + TOKEN + "\n"), \
                mock.patch("sys.stdout", io.StringIO()):
            guard.set_token()
        store_argv, store_input = self.calls[0]
        self.assertEqual(store_argv[:2], [guard.SECURITY_BIN, "add-generic-password"])
        self.assertIn("-U", store_argv)
        self.assertNotIn(TOKEN, " ".join(store_argv))            # never in argv
        self.assertEqual(store_input, ((TOKEN + "\n") * 2).encode("utf-8"))   # stripped, twice
        self.assertEqual(self.calls[1][0][:2], [guard.SECURITY_BIN, "find-generic-password"])
        self.assertFalse(hasattr(guard, "pty"))                  # the pseudo-terminal path is gone

    def test_set_token_refuses_an_empty_entry_and_a_missing_terminal_before_storing(self):
        with mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True), \
                mock.patch.object(guard.sys.stdin, "isatty", return_value=True), \
                mock.patch.object(guard.getpass, "getpass", return_value="   \n"):
            with self.assertRaises(guard.GuardError) as caught:
                guard.set_token()
        self.assertIn("empty token; nothing stored", str(caught.exception))
        self.assertEqual(self.calls, [])                         # nothing reached the keychain
        with mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True), \
                mock.patch.object(guard.sys.stdin, "isatty", return_value=False), \
                mock.patch.object(guard.getpass, "getpass",
                                  side_effect=AssertionError("must not prompt without a terminal")):
            with self.assertRaises(guard.GuardError) as caught:
                guard.set_token()
        self.assertIn("visible terminal", str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_set_token_on_linux_sends_the_secret_once(self):
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard, "trusted_linux_secret_tool",
                                  return_value="/usr/bin/secret-tool"), \
                mock.patch.object(guard.sys.stdin, "isatty", return_value=True), \
                mock.patch.object(guard.getpass, "getpass", return_value=TOKEN), \
                mock.patch("sys.stdout", io.StringIO()):
            guard.set_token()
        store_argv, store_input = self.calls[0]
        self.assertEqual(store_argv[:2], ["/usr/bin/secret-tool", "store"])
        self.assertEqual(store_input, (TOKEN + "\n").encode("utf-8"))

    def test_macos_store_requires_the_readback_to_equal_the_secret(self):
        self.run_patch.stop()
        self.addCleanup(self.run_patch.start)
        with mock.patch.object(guard.subprocess, "run",
                               return_value=FakeProc(stdout=b"a-different-token\n")), \
                mock.patch.object(guard.sys, "platform", "darwin"), \
                mock.patch.object(guard.os.path, "exists", return_value=True), \
                mock.patch.object(guard.sys.stdin, "isatty", return_value=True), \
                mock.patch.object(guard.getpass, "getpass", return_value=TOKEN), \
                mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(guard.GuardError) as caught:
                guard.set_token()
        self.assertIn("did not read back as stored", str(caught.exception))


class TestLinuxTokenNeverExposed(GuardTestCase):
    def test_the_token_reaches_the_header_and_nothing_else_on_linux(self):
        self.token_patcher.stop()                      # use the real read_token
        self.addCleanup(self.token_patcher.start)
        fake_proc = mock.Mock(returncode=0, stdout=(TOKEN + "\n").encode("utf-8"), stderr=b"")
        with mock.patch.object(guard.sys, "platform", "linux"), \
                mock.patch.object(guard, "trusted_linux_secret_tool",
                                  return_value="/usr/bin/secret-tool"), \
                mock.patch.object(guard.subprocess, "run", return_value=fake_proc), \
                mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, output = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 0)
        self.assertNotIn(TOKEN, self.log_text())
        self.assertNotIn(TOKEN, output)
        self.assertEqual(urlopen.call_args[0][0].get_header("Authorization"), "Bearer " + TOKEN)


class TestProvenance(GuardTestCase):
    """The guard proves it is the installed, root-owned program before it reads the token."""

    @staticmethod
    def rooted(mode):
        """A stat result for a root-owned, non-group/world-writable path."""
        return os.stat_result((mode, 0, 0, 1, 0, 0, 0, 0, 0, 0))

    def fake_stat(self, directory_mode):
        def stat_path(path):
            return self.rooted(0o100555 if path.endswith(".py") else directory_mode)
        return stat_path

    def test_a_file_under_a_user_owned_symlinked_directory_is_refused(self):
        real = os.path.join(self.state_dir, "libexec")
        os.mkdir(real, 0o755)
        target = os.path.join(real, "canvas_api_guard.py")
        with open(target, "w") as handle:
            handle.write("#!/usr/bin/env python3\n")
        link = os.path.join(self.state_dir, "link")
        os.symlink(real, link)
        with self.assertRaises(guard.GuardError) as caught:
            guard.trusted_path(os.path.join(link, "canvas_api_guard.py"),
                               "the guard executable")
        self.assertIn("owned by root", str(caught.exception))
        self.assertIn(os.path.realpath(target), str(caught.exception))

    def test_a_root_owned_real_path_and_every_ancestor_pass(self):
        installed = "/usr/local/libexec/canvas_api_guard.py"
        with mock.patch.object(guard.os, "stat", self.fake_stat(0o040755)):
            self.assertEqual(guard.trusted_path(installed, "the guard executable"),
                             os.path.realpath(installed))

    def test_a_group_writable_ancestor_is_refused_and_named(self):
        installed = "/usr/local/libexec/canvas_api_guard.py"
        with mock.patch.object(guard.os, "stat", self.fake_stat(0o040775)):
            with self.assertRaises(guard.GuardError) as caught:
                guard.trusted_path(installed, "the guard executable")
        self.assertIn("libexec", str(caught.exception))
        self.assertIn("writable by group", str(caught.exception))

    def test_the_config_seam_is_the_only_thing_that_skips_the_check(self):
        guard.check_provenance()                 # setUp pinned a private config: skipped
        if os.stat(os.path.realpath(guard.__file__)).st_uid == 0:
            self.skipTest("this checkout is root-owned, so it is indistinguishable from an install")
        with mock.patch.object(guard, "CONFIG_PATH", guard.INSTALLED_CONFIG_PATH):
            with self.assertRaises(guard.GuardError) as caught:
                guard.check_provenance()          # installed_guard_file() runs for real here
        self.assertIn("the guard executable", str(caught.exception))

    def test_the_guard_checks_the_file_that_is_running_not_argv(self):
        """installed_guard_file must ignore sys.argv[0], which a wrapper or symlink launcher
        controls, and report the real path of this module instead."""
        real = os.path.realpath(guard.__file__)
        with mock.patch.object(guard.sys, "argv", ["/bin/ls", "get", "courses/1"]):
            self.assertEqual(guard.installed_guard_file(), real)
        if os.stat(real).st_uid == 0:
            self.skipTest("this checkout is root-owned, so it is indistinguishable from an install")
        with mock.patch.object(guard, "CONFIG_PATH", guard.INSTALLED_CONFIG_PATH), \
                mock.patch.object(guard.sys, "argv", ["/bin/ls", "get", "courses/1"]):
            with self.assertRaises(guard.GuardError) as caught:
                guard.check_provenance()
        self.assertIn(real, str(caught.exception))

    def test_a_guard_that_cannot_see_its_own_file_refuses_instead_of_raising_NameError(self):
        saved = guard.__dict__.pop("__file__")
        self.addCleanup(guard.__dict__.__setitem__, "__file__", saved)
        with self.assertRaises(guard.GuardError) as caught:
            guard.installed_guard_file()
        self.assertIn("__file__", str(caught.exception))

    def test_the_default_config_path_is_held_to_the_same_rule(self):
        """CONFIG_PATH pinned at the installed path, with os.lstat (read_config's own check)
        and os.stat (trusted_path's ancestor walk) both patched so every directory in the
        chain is root-owned 0755 but the config file itself is merely user-owned 0644."""
        user_owned_file = os.stat_result((0o100644, 0, 0, 1, os.getuid(), 0, 0, 0, 0, 0))
        def fake_stat(path):
            return user_owned_file if path == guard.INSTALLED_CONFIG_PATH else self.rooted(0o040755)
        with mock.patch.object(guard, "CONFIG_PATH", guard.INSTALLED_CONFIG_PATH), \
                mock.patch.object(guard.os, "lstat", fake_stat), \
                mock.patch.object(guard.os, "stat", fake_stat):
            with self.assertRaises(guard.GuardError) as caught:
                guard.read_config()
        # "owned by root" is trusted_path's own wording; a config that is merely missing on
        # disk raises a different message, so this pins the check that actually ran.
        self.assertIn("owned by root", str(caught.exception))
        self.assertIn(guard.INSTALLED_CONFIG_PATH, str(caught.exception))

    def test_a_live_request_refuses_before_the_token_and_before_the_network(self):
        def no_keychain():
            raise AssertionError("the credential store was touched before the provenance check")

        with mock.patch.object(guard, "check_provenance", side_effect=guard.GuardError(
                    "the guard executable is not trustworthy: /tmp/x must be owned by root")), \
                mock.patch.object(guard, "read_token", no_keychain), \
                mock.patch("urllib.request.urlopen") as urlopen:
            code, _ = self.run_main(["get", "courses/1"])
        self.assertEqual(code, 2)
        self.assertIn("not trustworthy", self.last_stderr)
        urlopen.assert_not_called()

    def test_an_unverifiable_write_exits_3_while_a_refusal_exits_2(self):
        responses = [FakeResponse(payload={"id": 3, "grade": "60"}),
                     FakeResponse(payload={"id": 3, "grade": "95"}),
                     OSError("network unavailable")]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"grade": 95}}'])
        self.assertEqual(code, 3)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        code, _ = self.run_main(["get", "https://evil.example.com/api/v1/courses/1"])
        self.assertEqual(code, 2)


class TestSourceField(GuardTestCase):
    def test_every_line_says_how_the_guard_was_invoked(self):
        with mock.patch.dict(guard.os.environ, {"CODEX_SANDBOX": "seatbelt"}), \
                mock.patch.object(guard, "parent_process_name", return_value="codex"):
            for name in guard.AGENT_MARKERS:            # isolate from this process's own env
                if name != "CODEX_SANDBOX":
                    guard.os.environ.pop(name, None)
            code, _ = self.run_main(["put", "courses/1/assignments/2", "-d", "{}", "--dry-run"])
        self.assertEqual(code, 0)
        lines = self.log_lines()
        self.assertTrue(lines)
        for line in lines:
            self.assertEqual(line["source"],
                             {"tty": False, "parent": "codex", "agent_env": ["CODEX_SANDBOX"]})
        self.assertNotIn("seatbelt", self.log_text())            # names only, never values

    def test_a_terminal_invocation_is_marked_tty(self):
        with mock.patch.dict(guard.os.environ, {}, clear=False), \
                mock.patch.object(guard, "parent_process_name", return_value="zsh"):
            for name in guard.AGENT_MARKERS:
                guard.os.environ.pop(name, None)
            code, _ = self.run_main(["put", "courses/1/assignments/2", "-d", "{}", "--dry-run"],
                                    stdin_is_tty=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.log_lines()[0]["source"],
                         {"tty": True, "parent": "zsh", "agent_env": []})

    def test_a_failed_parent_lookup_is_null_and_does_not_break_the_call(self):
        with mock.patch.object(guard.os, "getppid", side_effect=OSError("no ppid")):
            self.assertIsNone(guard.parent_process_name())
            code, _ = self.run_main(["put", "courses/1/assignments/2", "-d", "{}", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIsNone(self.log_lines()[0]["source"]["parent"])


class TestNextPage(GuardTestCase):
    LINK = ('<https://%s/api/v1/courses?page=1&per_page=10>; rel="current",'
            '<https://%s/api/v1/courses?page=2&per_page=10>; rel="next",'
            '<https://%s/api/v1/courses?page=5&per_page=10>; rel="last"') % (HOST, HOST, HOST)

    def test_a_list_with_a_next_link_prints_its_path_and_query(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(headers={"Link": self.LINK}, payload=[{"id": 1}])
            code, output = self.run_main(["get", "courses?per_page=10"])
        self.assertEqual(code, 0)
        self.assertIn("next:          /api/v1/courses?page=2&per_page=10", output)

    def test_json_output_carries_next(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(headers={"Link": self.LINK}, payload=[{"id": 1}])
            code, output = self.run_main(["get", "courses", "-o", "json"])
        self.assertEqual(json.loads(output)["next"], "/api/v1/courses?page=2&per_page=10")

    def test_a_list_without_a_next_link_says_nothing_about_pages(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=[{"id": 1}])
            code, output = self.run_main(["get", "courses"])
        self.assertEqual(code, 0)
        self.assertNotIn("next:", output)

    def test_a_next_link_on_another_host_is_reported_not_printed_as_a_path(self):
        evil = '<https://evil.example.com/api/v1/courses?page=2>; rel="next"'
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(headers={"Link": evil}, payload=[{"id": 1}])
            code, output = self.run_main(["get", "courses"])
        self.assertEqual(code, 0)
        self.assertNotIn("next:", output)
        self.assertIn("evil.example.com", output)            # named in the note
        self.assertIn("off the pinned host", output)

    def test_next_link_helper(self):
        self.assertEqual(guard.next_link({"Link": self.LINK}, HOST),
                         "/api/v1/courses?page=2&per_page=10")
        self.assertIsNone(guard.next_link({}, HOST))
        self.assertIsNone(guard.next_link({"link": '<https://%s/x>; rel="last"' % HOST}, HOST))

    def test_a_comma_or_semicolon_inside_the_url_does_not_break_parsing(self):
        link = ('<https://%s/api/v1/courses?ids=1,2;x=y&page=1>; rel="current",'
                '<https://%s/api/v1/courses?ids=1,2;x=y&page=2>; rel="next"') % (HOST, HOST)
        self.assertEqual(guard.next_link({"Link": link}, HOST),
                         "/api/v1/courses?ids=1,2;x=y&page=2")

    def page(self, number, items):
        """One Canvas page, with a Link header pointing at the next one."""
        link = '<https://%s/api/v1/courses?page=%d&per_page=2>; rel="next"' % (HOST, number + 1)
        return FakeResponse(headers={"Link": link}, payload=items)

    def test_all_pages_concatenates_every_page_and_reports_count_and_pages(self):
        responses = [self.page(1, [{"id": 1}, {"id": 2}]), self.page(2, [{"id": 3}]),
                     FakeResponse(payload=[{"id": 4}])]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            code, output = self.run_main(["get", "courses?per_page=2", "--all-pages",
                                          "-o", "json"])
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual([item["id"] for item in result["items"]], [1, 2, 3, 4])
        self.assertEqual((result["count"], result["pages"]), (4, 3))
        self.assertEqual(urlopen.call_count, 3)
        reads = [line for line in self.log_lines() if line["event"] == "read"]
        self.assertEqual(len(reads), 3)

    def test_all_pages_refuses_a_link_that_repeats_a_page_it_has_read(self):
        responses = [self.page(1, [{"id": 1}]), self.page(1, [{"id": 2}])]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, _ = self.run_main(["get", "courses?per_page=2", "--all-pages"])
        self.assertEqual(code, 2)
        self.assertIn("pagination loop", self.last_stderr)

    def test_all_pages_refuses_a_link_that_leaves_the_pinned_host(self):
        evil = '<https://evil.example.com/api/v1/courses?page=2>; rel="next"'
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(headers={"Link": evil}, payload=[{"id": 1}])
            code, output = self.run_main(["get", "courses?per_page=2", "--all-pages"])
        self.assertEqual(code, 2)
        self.assertIn("evil.example.com", self.last_stderr)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(output, "")

    def test_all_pages_stops_at_the_page_cap(self):
        responses = [self.page(number, [{"id": number}]) for number in range(1, 6)]
        with mock.patch.object(guard, "PAGE_CAP", 2), \
                mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            code, _ = self.run_main(["get", "courses?per_page=2", "--all-pages"])
        self.assertEqual(code, 2)
        self.assertIn("2 pages", self.last_stderr)
        self.assertIn("page=3", self.last_stderr)          # the runaway link, not the first page
        self.assertEqual(urlopen.call_count, 2)

    def test_all_pages_refuses_a_response_that_is_not_a_list(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1})
            code, _ = self.run_main(["get", "courses/1", "--all-pages"])
        self.assertEqual(code, 2)
        self.assertIn("list response", self.last_stderr)


class TestFieldsAndOutputDefault(GuardTestCase):
    def test_fields_projects_every_item_to_the_named_dot_paths(self):
        payload = [{"id": 1, "name": "A", "term": {"id": 8, "name": "Fall"}, "extra": "drop"},
                   {"id": 2, "name": "B"}]
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=payload)
            code, output = self.run_main(["get", "courses", "--fields", "id,term.name",
                                          "-o", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["items"],
                         [{"id": 1, "term.name": "Fall"}, {"id": 2, "term.name": None}])

    def test_fields_projects_a_single_object_and_keeps_the_requested_order(self):
        payload = {"id": 2, "name": "Lab", "rubric_settings": {"id": 9}}
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=payload)
            code, output = self.run_main(["get", "courses/1/assignments/2",
                                          "--fields", "name,rubric_settings.id,missing",
                                          "-o", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(list(json.loads(output)["object"]),
                         ["name", "rubric_settings.id", "missing"])
        self.assertEqual(json.loads(output)["object"]["missing"], None)

    def test_an_empty_field_list_is_refused(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload=[{"id": 1}])
            code, _ = self.run_main(["get", "courses", "--fields", " , "])
        self.assertEqual(code, 2)
        self.assertIn("--fields", self.last_stderr)
        self.assertEqual(urlopen.call_count, 0)

    def test_json_is_the_default_when_stdout_is_not_a_terminal(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1, "name": "Lab"})
            code, output = self.run_main(["get", "courses/1"], stdout_is_tty=False)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["object"], {"id": 1, "name": "Lab"})

    def test_text_is_the_default_at_a_terminal(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(payload={"id": 1, "name": "Lab"})
            code, output = self.run_main(["get", "courses/1"], stdout_is_tty=True)
        self.assertEqual(code, 0)
        self.assertIn("object:", output)
        self.assertNotIn("{", output.splitlines()[0])


def find_codex():
    """The Codex CLI: on PATH, or bundled in the ChatGPT app. None if absent."""
    import shutil
    for candidate in (shutil.which("codex"), "/Applications/ChatGPT.app/Contents/Resources/codex"):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    return None


def rule_lists(rules_path):
    """The name lists a rules file declares, read the way Codex reads them."""
    with open(rules_path) as handle:
        text = handle.read()
    return dict((name, re.findall(r'"([^"]+)"', body)) for name, body
                in re.findall(r"^([A-Z_]+) = \[(.*?)\]", text, re.S | re.M))


# The only two commands that may run without a prompt: the guard's read verb and the Level 2
# read operation. Pinning the allow side - rather than listing every name that must prompt -
# means a new subcommand or operation defaults to prompt with no list here to update, and a
# rules-file edit that promotes anything else to a read is caught both offline
# (TestRulesCoverage) and by the real Codex matrix (TestCodexRules).
ALLOWED_WITHOUT_PROMPT = ["get", "student-attention"]


class TestCodexRules(unittest.TestCase):
    """The shipped rules file, evaluated by Codex itself. Skipped when Codex is absent."""
    RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex",
                         "canvas-api-guard.rules")

    def setUp(self):
        self.codex = find_codex()
        if not self.codex:
            self.skipTest("codex binary not found; the rules matrix was not checked")

    def decision(self, argv):
        import subprocess
        proc = subprocess.run([self.codex, "execpolicy", "check", "--rules", self.RULES, "--"]
                              + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()
        for line in text.splitlines():
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict) and "decision" in parsed:
                return parsed.get("decision") or "none"
            if isinstance(parsed, dict) and parsed.get("matchedRules") == []:
                return "none"
        self.fail("execpolicy check did not return JSON for %r:\n%s" % (argv, text))

    GUARD = "/usr/local/libexec/canvas_api_guard.py"
    OPERATIONS = "/usr/local/libexec/canvas_api_operations.py"

    # Which decision a list means, and which program its subcommands belong to. The rows below
    # are generated from these plus whatever the rules file's own lists currently declare, so a
    # subcommand nobody hand-copied into this test still gets checked against real Codex.
    DECISION_FOR_LIST = {"READS": "allow", "WRITES": "prompt", "DOWNLOADS": "prompt",
                         "OPERATION_READS": "allow", "OPERATION_PROMPTS": "prompt"}

    def test_the_matrix(self):
        program_for_list = {"READS": self.GUARD, "WRITES": self.GUARD, "DOWNLOADS": self.GUARD,
                            "OPERATION_READS": self.OPERATIONS,
                            "OPERATION_PROMPTS": self.OPERATIONS}
        lists = rule_lists(self.RULES)
        rows = []
        for list_name, base_decision in self.DECISION_FOR_LIST.items():
            for name in lists[list_name]:
                # Anything but the two pinned read commands must prompt, however the file
                # above has classified it - that mismatch is what should fail this test.
                want = base_decision if name in ALLOWED_WITHOUT_PROMPT else "prompt"
                rows.append(([program_for_list[list_name], name], want))
        rows += [
            (["./canvas_api_guard.py", "put", "courses/1", "--yes"], "none"),
            (["python3", "/usr/local/libexec/canvas_api_guard.py", "put", "courses/1", "--yes"], "none"),
            (["security", "find-generic-password", "-s", "canvas-api-guard", "-w"], "forbidden"),
            (["secret-tool", "lookup", "service", "canvas-api-guard"], "forbidden"),
            (["/usr/bin/security", "find-generic-password", "-s", "canvas-api-guard", "-w"],
             "forbidden"),
            (["/usr/bin/secret-tool", "lookup", "service", "canvas-api-guard"], "forbidden"),
            (["/opt/homebrew/bin/secret-tool", "lookup", "service", "canvas-api-guard"],
             "forbidden"),
            (["security", "list-keychains"], "none"),
        ]
        for argv, want in rows:
            self.assertEqual(self.decision(argv), want, " ".join(argv))


class TestRulesCoverage(unittest.TestCase):
    """Runs with or without Codex: every command both programs accept must be classified."""

    RULES = TestCodexRules.RULES

    def test_every_guard_subcommand_is_classified_exactly_once(self):
        lists = rule_lists(self.RULES)
        classified = lists["READS"] + lists["WRITES"] + lists["DOWNLOADS"]
        self.assertEqual(sorted(classified), subcommand_names(guard.build_parser()))
        self.assertEqual(len(classified), len(set(classified)))

    def test_every_level_2_operation_is_classified_exactly_once(self):
        lists = rule_lists(self.RULES)
        classified = lists["OPERATION_READS"] + lists["OPERATION_PROMPTS"]
        self.assertEqual(sorted(classified), subcommand_names(load_operations().parser()))
        self.assertEqual(len(classified), len(set(classified)))

    def test_only_the_two_read_commands_are_allowed_without_a_prompt(self):
        """Classifying every subcommand exactly once (the tests above) still accepts a write
        landing in the wrong list, as long as it lands in some list. Pin the allow side: these
        are the only two names the rules may allow, and every other subcommand and operation
        must appear in a prompt list, so a promotion to allow fails offline too."""
        lists = rule_lists(self.RULES)
        self.assertEqual(lists["READS"], ALLOWED_WITHOUT_PROMPT[:1])
        self.assertEqual(lists["OPERATION_READS"], ALLOWED_WITHOUT_PROMPT[1:])
        for name in subcommand_names(guard.build_parser()):
            if name not in lists["READS"]:
                self.assertIn(name, lists["WRITES"] + lists["DOWNLOADS"], name)
        for name in subcommand_names(load_operations().parser()):
            if name not in lists["OPERATION_READS"]:
                self.assertIn(name, lists["OPERATION_PROMPTS"], name)


class TestSkillDocuments(unittest.TestCase):
    """A skill that shows a command the program does not have teaches the agent a dead path."""

    ROOT = os.path.dirname(os.path.abspath(__file__))
    GUARD_SKILL = os.path.join(ROOT, "codex", "skills", "canvas-api-guard", "SKILL.md")
    OPERATIONS_SKILL = os.path.join(ROOT, "level2", "SKILL.md")

    def shown(self, path, program):
        """Every command a skill's examples actually run, taken from the start of a line."""
        with open(path) as handle:
            text = handle.read()
        return set(re.findall(r"^/usr/local/libexec/%s\s+([a-z][a-z-]*)" % re.escape(program),
                              text, re.M))

    def test_the_level_2_skill_documents_every_operation_and_invents_none(self):
        known = set(subcommand_names(load_operations().parser()))
        shown = self.shown(self.OPERATIONS_SKILL, "canvas_api_operations.py")
        self.assertEqual(shown - known, set(), "the skill shows operations that do not exist")
        self.assertEqual(known - shown, set(), "an operation is undocumented")

    def test_the_level_2_readme_lists_the_same_operations(self):
        with open(os.path.join(self.ROOT, "level2", "README.md")) as handle:
            text = handle.read()
        for name in subcommand_names(load_operations().parser()):
            self.assertIn("`%s`" % name, text)
        for gone in ("current-courses", "roster-count", "find-student", "needs-grading",
                     "course-health", "assignment-performance", "student-trajectory",
                     "set-assignment-dates", "excuse-submission", "excuse-attendance",
                     "create-assignment", "update-assignment", "create-or-update-page",
                     "create-announcement"):
            self.assertNotIn(gone, text)

    def test_the_level_1_skill_stays_short_enough_to_be_read(self):
        with open(self.GUARD_SKILL) as handle:
            self.assertLess(len(handle.read().splitlines()), 90)

    def test_the_level_1_skill_shows_only_verbs_the_guard_has(self):
        known = set(subcommand_names(guard.build_parser()))
        shown = self.shown(self.GUARD_SKILL, "canvas_api_guard.py")
        self.assertEqual(shown - known, set(), "the skill shows a verb the guard does not have")
        self.assertEqual({"get", "post", "put", "patch", "delete"} - shown, set())

    def test_the_level_1_skill_points_at_the_documentation_not_at_recipes(self):
        with open(self.GUARD_SKILL) as handle:
            text = handle.read()
        self.assertIn("Every endpoint in the Canvas REST API documentation works here", text)
        self.assertIn("--all-pages", text)
        self.assertIn("--fields", text)
        self.assertIn("WRITE STATUS UNCERTAIN", text)
        self.assertNotIn("Fast read paths", text)
        self.assertNotIn("canvas_api_guard.py count", text)

    def test_every_skill_guard_command_parses_with_only_real_flags(self):
        """A typo'd flag (--al-pages) would silently teach the agent a dead path; catch it
        by actually parsing every command line against the real parser, not just the verb.
        Both skills are read: the Level 2 skill shows guard calls for what it does not do."""
        parsers = {"canvas_api_guard.py": guard.build_parser(),
                   "canvas_api_operations.py": load_operations().parser()}
        for skill in (self.GUARD_SKILL, self.OPERATIONS_SKILL):
            with open(skill) as handle:
                text = handle.read()
            lines = re.findall(r"^/usr/local/libexec/(canvas_api_\w+\.py) (.+)$", text, re.M)
            self.assertTrue(lines, "no command lines found in %s" % skill)
            for program, rest in lines:
                tokens = shlex.split(rest)
                with mock.patch("sys.stderr", io.StringIO()) as stderr:
                    try:
                        parsers[program].parse_args(tokens)
                    except SystemExit:
                        self.fail("skill command failed to parse: %r %r\n%s"
                                  % (program, rest, stderr.getvalue()))


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
        regraded = self.regraded()
        # Canvas returns extra fields (comments, html) that the request does not send; member-wise
        # comparison still proves the write because only the sent fields are matched.
        after = self.question([dict(a, comments="", html=None) for a in regraded])
        body = {"question": {"answers": [{"id": a["id"], "text": a["text"], "weight": a["weight"]}
                                         for a in regraded]}}
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


class TestGuardHeader(unittest.TestCase):
    """The header is the map a reviewer reads first; it must describe the file that exists."""

    SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_api_guard.py")

    def source(self):
        with open(self.SOURCE) as handle:
            return handle.read()

    def test_the_version_is_1_15_0(self):
        self.assertEqual(guard.USER_AGENT, "canvas-api-guard/1.15.0")

    def test_the_header_reading_order_matches_the_files_banners_exactly(self):
        """The map must be derived truth, not a copy that can silently go stale."""
        source = self.source()
        banners = re.findall(r"^# -+ (.+?)\s*$", source, re.M)
        order_text = source.split("READ TOP TO BOTTOM:")[1].split(".")[0]
        order_text = re.sub(r"\n#\s*", " ", order_text)
        sections = [part.strip() for part in order_text.split(",")]
        self.assertEqual(sections, banners)

    def test_the_header_states_the_provenance_and_token_invariants(self):
        header = self.source().split("import argparse")[0]
        self.assertIn("THE TOKEN IS ONLY EVER SENT TO THE HOST RECORDED IN THE FIXED SYSTEM "
                      "CONFIGURATION", header)
        self.assertIn("root-owned", header)


class TestInstallerPlan(unittest.TestCase):
    """The review step must be useful and must not require root or touch external state."""

    ROOT = os.path.dirname(os.path.abspath(__file__))
    INSTALLER = os.path.join(ROOT, "install.sh")
    BOOTSTRAP = os.path.join(ROOT, "install-from-github.sh")

    def run_installer(self, *args):
        import subprocess
        return subprocess.run([self.INSTALLER] + list(args), cwd=self.ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_help_is_successful(self):
        proc = self.run_installer("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--plan", proc.stdout)
        self.assertIn("It exits 0 when a root-owned file would change (rerun with sudo), 4 when", proc.stdout)

    def test_plan_lists_every_reviewed_hash_and_destination(self):
        proc = self.run_installer("--plan", "--host", HOST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for label in ("guard sha:", "rules sha:", "skill sha:", "Canvas host:",
                      "executable:", "config:", "audit log:", "Codex rules:",
                      "Codex skill:"):
            self.assertIn(label, proc.stdout)
        self.assertIn("no changes made", proc.stdout)
        self.assertIn("does not read or store a token", proc.stdout)
        # HOST is never a real installation's host, so the generated config always differs and
        # the plan exits 0 on any machine; each installed-file line still carries its state.
        states = re.findall(r"\) \[(same|differs|missing|link)\]$", proc.stdout, re.M)
        self.assertEqual(len(states), 4, proc.stdout)
        # whatever the developer's own ~/.codex/config.toml holds, this line is never a file state
        self.assertTrue(re.search(r"^  Codex config: .* \[settings [^\]]*\]$", proc.stdout, re.M), proc.stdout)
        self.assertNotIn("Nothing to do", proc.stdout)

    def redirected_installer(self):
        """A copy of install.sh whose destinations point into a private temp tree, with the
        ancestor-ownership check (exercised separately) stubbed out, so the plan's up-to-date
        decision can be driven through every state without root or /usr/local."""
        root = tempfile.mkdtemp(prefix="cag-plan-tree-")
        self.addCleanup(shutil.rmtree, root, True)
        with open(self.INSTALLER) as handle:
            script = handle.read()
        edits = (
            ('SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)', "SRC_DIR=%s" % shlex.quote(self.ROOT)),
            ("DEST_DIR=/usr/local/libexec", "DEST_DIR=%s/libexec" % root),
            ("CONFIG_DIR=/usr/local/etc/canvas-api-guard", "CONFIG_DIR=%s/etc" % root),
            ('LOG_DIR="$USER_DIR/.canvas-api-guard"', 'LOG_DIR="%s/log"' % root),
            ('CODEX_DIR="$USER_DIR/.codex"', 'CODEX_DIR="%s/codex"' % root),
            ('check_ancestor_ownership "$DEST_DIR"', "CHECKED=1"),
            ('check_ancestor_ownership "$CONFIG_DIR"', ":"),
            # the temp tree is user-owned; the owner/mode rule is covered by the file_state test
            ("CONFIG_TEXT=$(printf", "root_owned_and_private() { :; }\nCONFIG_TEXT=$(printf"),
        )
        for old, replacement in edits:
            self.assertEqual(script.count(old), 1, old)
            script = script.replace(old, replacement)
        copy = os.path.join(root, "install.sh")
        with open(copy, "w") as handle:
            handle.write(script)
        os.chmod(copy, 0o755)
        return root, copy

    def populate_installed(self, root):
        """Every API Only artifact except the Codex config, byte-identical to the checkout."""
        installed = {
            "libexec/canvas_api_guard.py": os.path.join(self.ROOT, "canvas_api_guard.py"),
            "codex/rules/canvas-api-guard.rules": os.path.join(self.ROOT, "codex", "canvas-api-guard.rules"),
            "codex/skills/canvas-api-guard/SKILL.md": os.path.join(
                self.ROOT, "codex", "skills", "canvas-api-guard", "SKILL.md"),
        }
        for relative, source in installed.items():
            os.makedirs(os.path.dirname(os.path.join(root, relative)), exist_ok=True)
            shutil.copyfile(source, os.path.join(root, relative))
        os.makedirs(os.path.join(root, "etc"))
        with open(os.path.join(root, "etc", "config.json"), "w") as handle:
            handle.write('{"host":"%s","profile":"level-1"}\n' % HOST)

    def test_plan_exits_3_only_when_every_installed_file_matches(self):
        import subprocess
        root, copy = self.redirected_installer()

        def plan():
            return subprocess.run([copy, "--plan", "--host", HOST], cwd=self.ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True)

        proc = plan()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("[missing]"), 4)

        self.populate_installed(root)
        with open(os.path.join(root, "codex", "config.toml"), "w") as handle:
            handle.write('sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
                         'approvals_reviewer = "user"\n')
        proc = plan()
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("[same]"), 4)
        self.assertIn("Nothing to do", proc.stdout)
        self.assertNotIn("Run the same command through sudo", proc.stdout)

        skill = os.path.join(root, "codex/skills/canvas-api-guard/SKILL.md")
        with open(skill, "a") as handle:
            handle.write("# older\n")
        proc = plan()
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("[differs]"), 1)
        self.assertIn("without --plan and without sudo", proc.stdout)
        self.assertNotIn("through sudo", proc.stdout)

        # Only a user-owned file differs, so the same command without --plan and without root
        # replaces it, backs the old copy up, and leaves the root-owned files alone.
        guard = os.path.join(root, "libexec/canvas_api_guard.py")
        before = os.stat(guard)
        proc = subprocess.run([copy, "--allow-dirty", "--host", HOST], cwd=self.ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("backed up %s" % skill, proc.stdout)
        self.assertTrue(any(name.startswith("SKILL.md.bak-")
                            for name in os.listdir(os.path.dirname(skill))))
        self.assertEqual(plan().returncode, 3)
        self.assertEqual(os.stat(guard).st_mtime_ns, before.st_mtime_ns)

        with open(guard, "a") as handle:
            handle.write("# older\n")
        proc = plan()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("through sudo", proc.stdout)
        proc = subprocess.run([copy, "--allow-dirty", "--host", HOST], cwd=self.ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("requires root ownership", proc.stderr)

    def test_codex_settings_are_added_before_the_first_table_and_never_overwritten(self):
        """A person, not a reviewer model, must answer every Canvas write prompt, so the
        installer adds the three settings a config lacks -- as top-level keys, ahead of any
        [table] -- and reports, but keeps, a value somebody chose differently."""
        import subprocess
        root, copy = self.redirected_installer()
        self.populate_installed(root)
        config = os.path.join(root, "codex", "config.toml")
        with open(config, "w") as handle:
            handle.write('model = "gpt-5"\napprovals_reviewer = "auto_review"  # chosen\n\n'
                         '[profiles.work]\napproval_policy = "never"\n')
        os.chmod(config, 0o600)

        def run(*flags):
            return subprocess.run([copy] + list(flags) + ["--allow-dirty", "--host", HOST],
                                  cwd=self.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True)

        proc = run("--plan")
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertIn("[settings missing: sandbox_mode approval_policy]", proc.stdout)
        warning = proc.stdout.split("WARNING")[1]
        self.assertIn("set differently and left alone: approvals_reviewer=auto_review", warning)
        self.assertIn("also set inside a [table], whose value overrides the top level: approval_policy", warning)
        self.assertNotIn("sandbox_mode", warning)

        proc = run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("backed up %s" % config, proc.stdout)
        self.assertIn("added: sandbox_mode approval_policy", proc.stdout)
        self.assertIn("WARNING", proc.stdout)
        with open(config) as handle:
            text = handle.read()
        self.assertEqual(text, 'model = "gpt-5"\napprovals_reviewer = "auto_review"  # chosen\n\n'
                               '# canvas-api-guard: Codex runs sandboxed and a person answers every prompt\n'
                               'sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n\n'
                               '[profiles.work]\napproval_policy = "never"\n')
        self.assertEqual(os.stat(config).st_mode & 0o777, 0o600)
        self.assertTrue(any(name.startswith("config.toml.bak-") for name in os.listdir(os.path.dirname(config))))
        proc = run("--plan")
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        self.assertIn("[settings same]", proc.stdout.split("Codex config:")[1].split("\n")[0])
        self.assertIn("need a person (exit status 5)", proc.stdout)

    def settings_run(self, root, copy, *flags):
        import subprocess
        return subprocess.run([copy] + list(flags) + ["--allow-dirty", "--host", HOST], cwd=self.ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def test_a_codex_config_with_multi_line_values_is_never_edited(self):
        """A '[' that opens a multi-line array is not a table header. Inserting there would
        put the settings inside the value and Codex would refuse to start, so such a file is
        reported and left byte-identical."""
        tail = ('sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
                'approvals_reviewer = "user"\n')
        for original, link in (('profiles = [\n  ["work"],\n]\n' + tail, False),
                               ('notes = """\n[section]\nmore\n"""\n' + tail, False),
                               ("notes = '''\n[section]\n'''\n" + tail, False),
                               ('notes = """\n[section]\n"""\n', True)):
            with self.subTest(original=original.split("\n")[0], link=link):
                root, copy = self.redirected_installer()
                self.populate_installed(root)
                config = os.path.join(root, "codex", "config.toml")
                if link:                              # a dotfile-managed config is a link
                    os.symlink(os.path.join(root, "elsewhere.toml"), config)
                with open(config, "w") as handle:
                    handle.write(original)
                proc = self.settings_run(root, copy, "--plan")
                self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
                self.assertIn("not edited: multi-line values]", proc.stdout)
                self.assertIn("add at the top yourself:", proc.stdout)
                proc = self.settings_run(root, copy)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("added: nothing", proc.stdout)
                with open(config) as handle:
                    self.assertEqual(handle.read(), original)
                self.assertEqual([name for name in os.listdir(os.path.dirname(config)) if "bak" in name], [])

    def test_single_quoted_codex_settings_count_as_the_same(self):
        root, copy = self.redirected_installer()
        self.populate_installed(root)
        with open(os.path.join(root, "codex", "config.toml"), "w") as handle:
            handle.write("sandbox_mode='workspace-write'\napproval_policy = 'on-request'  # note\n"
                         'approvals_reviewer = "user"\r\nmodel = "complex"\n')
        proc = self.settings_run(root, copy, "--plan")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("[settings same]", proc.stdout)
        self.assertNotIn("WARNING", proc.stdout)

    def test_a_symlinked_codex_config_is_reported_as_a_link_and_refused(self):
        root, copy = self.redirected_installer()
        self.populate_installed(root)
        config = os.path.join(root, "codex", "config.toml")
        target = os.path.join(root, "elsewhere.toml")
        os.symlink(target, config)
        proc = self.settings_run(root, copy, "--plan")
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertIn(") [settings link; missing:", proc.stdout.split("Codex config:")[1].split("\n")[0])
        proc = self.settings_run(root, copy)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("refusing to replace a symbolic link", proc.stderr)
        self.assertNotIn("backed up", proc.stdout)
        # a dotfile-managed config that is already right is a link too, and needs nothing
        with open(target, "w") as handle:
            handle.write('sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
                         'approvals_reviewer = "user"\n')
        proc = self.settings_run(root, copy, "--plan")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("[settings same]", proc.stdout)
        skill = os.path.join(root, "codex/skills/canvas-api-guard/SKILL.md")
        with open(skill, "a") as handle:
            handle.write("# older\n")
        proc = self.settings_run(root, copy)          # a needed install is not blocked by the link
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("backed up %s" % skill, proc.stdout)
        self.assertNotIn("symbolic link", proc.stderr)

    def extracted_file_state(self):
        """install.sh's SHA-256 state check, alone, cut out with sed like the ancestor check."""
        import subprocess
        platform = os.uname().sysname
        if platform not in ("Darwin", "Linux"):
            self.skipTest("install.sh supports macOS and Linux only")
        helpers = subprocess.run(
            "sed -n '/^    %s)$/,/^        ;;$/p' %s | sed '1d;$d'"
            % (platform, shlex.quote(self.INSTALLER)), shell=True,
            stdout=subprocess.PIPE, universal_newlines=True).stdout
        function = subprocess.run(
            ["sed", "-n", "/^root_owned_and_private() {/,/^}$/p;/^file_state() {$/,/^}$/p",
             self.INSTALLER], stdout=subprocess.PIPE, universal_newlines=True).stdout
        self.assertIn("hash_file()", helpers)
        self.assertIn("echo link", function)
        self.assertIn("echo perms", function)
        return helpers + function + '\nfile_state "$1" "$2" "$3"\n'

    def test_file_state_is_same_only_for_an_identical_regular_file(self):
        import hashlib
        import subprocess
        directory = tempfile.mkdtemp(prefix="cag-file-state-")
        self.addCleanup(shutil.rmtree, directory, True)
        script = os.path.join(directory, "state.sh")
        with open(script, "w") as handle:
            handle.write(self.extracted_file_state())
        same = os.path.join(directory, "same")
        with open(same, "w") as handle:
            handle.write("reviewed\n")
        digest = hashlib.sha256(b"reviewed\n").hexdigest()
        differs = os.path.join(directory, "differs")
        with open(differs, "w") as handle:
            handle.write("older\n")
        link = os.path.join(directory, "link")
        os.symlink(same, link)
        # Every file here is user-owned, so a root-owned destination with matching content is
        # [perms]: content alone never earns [same] for the files the guard's provenance check
        # inspects.
        for path, owner, expected in ((same, "user", "same"), (same, "root", "perms"),
                                      (differs, "user", "differs"),
                                      (os.path.join(directory, "absent"), "root", "missing"),
                                      (link, "user", "link")):
            with self.subTest(expected=expected):
                proc = subprocess.run(["sh", script, path, digest, owner], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, universal_newlines=True)
                self.assertEqual(proc.stdout.strip(), expected, proc.stderr)

    def test_plan_runs_the_ancestor_ownership_check(self):
        """The installer refuses to leave the guard's own provenance check unsatisfiable, so
        the ancestor check must run -- and be visible -- even under --plan. This does not
        simulate a bad /usr/local; it counts the components it actually inspected, so
        deleting either call site would show up here."""
        proc = self.run_installer("--plan", "--host", HOST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ancestor check", proc.stdout)
        counted = re.search(r"(\d+) components checked", proc.stdout)
        self.assertIsNotNone(counted, proc.stdout)
        self.assertGreater(int(counted.group(1)), 0)

    def extracted_ancestor_check(self):
        """install.sh's ancestor check, alone: the platform's stat helpers and the function
        itself, cut out with sed so its refusals can be exercised without root or /usr/local."""
        import subprocess
        platform = os.uname().sysname
        if platform not in ("Darwin", "Linux"):
            self.skipTest("install.sh supports macOS and Linux only")
        helpers = subprocess.run(
            "sed -n '/^    %s)$/,/^        ;;$/p' %s | sed '1d;$d'"
            % (platform, shlex.quote(self.INSTALLER)), shell=True,
            stdout=subprocess.PIPE, universal_newlines=True).stdout
        function = subprocess.run(
            ["sed", "-n", "/^check_ancestor_ownership() {$/,/^}$/p", self.INSTALLER],
            stdout=subprocess.PIPE, universal_newlines=True).stdout
        self.assertIn("stat_owner()", helpers)
        self.assertIn("is not owned by root", function)
        return "CHECKED=0\n" + helpers + function + '\ncheck_ancestor_ownership "$1"\n'

    def run_ancestor_check(self, target):
        import subprocess
        script = os.path.join(tempfile.mkdtemp(prefix="cag-ancestor-check-"), "check.sh")
        self.addCleanup(shutil.rmtree, os.path.dirname(script), True)
        with open(script, "w") as handle:
            handle.write(self.extracted_ancestor_check())
        return subprocess.run(["sh", script, target], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)

    def user_owned_directory(self):
        directory = tempfile.mkdtemp(prefix="cag-ancestor-")
        self.addCleanup(shutil.rmtree, directory, True)
        return directory

    def test_a_user_owned_destination_is_refused_with_a_chown_remedy(self):
        proc = self.run_ancestor_check(self.user_owned_directory())
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("is not owned by root", proc.stderr)
        self.assertIn("remedy: sudo chown root:", proc.stderr)

    def test_a_user_owned_ancestor_is_refused_and_offered_no_chown_remedy(self):
        """chown on a prefix somebody else manages would be destructive advice, not a fix."""
        proc = self.run_ancestor_check(os.path.join(self.user_owned_directory(), "libexec"))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("installed under a prefix a non-root user can write", proc.stderr)
        self.assertNotIn("chown", proc.stderr)

    def test_specialized_functions_plan_lists_its_separate_artifacts(self):
        proc = self.run_installer("--plan", "--profile", "specialized-functions", "--host", HOST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("profile Specialized Functions", proc.stdout)
        self.assertIn("compatibility key level-2", proc.stdout)
        self.assertIn("Specialized Functions executable:", proc.stdout)
        self.assertIn("Specialized Functions skill:", proc.stdout)

    def test_invalid_host_is_refused(self):
        proc = self.run_installer("--plan", "--host", "https://evil.example/x")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid Canvas host", proc.stderr)

    def run_bootstrap(self, *args):
        import subprocess
        return subprocess.run([self.BOOTSTRAP] + list(args), cwd=self.ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_github_bootstrap_help_is_successful(self):
        proc = self.run_bootstrap("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("FULL_COMMIT_SHA", proc.stdout)

    def test_github_bootstrap_on_main_carries_no_pin_and_says_so(self):
        """main never pins: only tools/release.sh writes RELEASE_REF, on the release branch."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertRegex(script, r"(?m)^RELEASE_REF=[ \t]*(#.*)?$")
        proc = self.run_bootstrap("--host", HOST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("carries no release pin", proc.stderr)

    def pinned_bootstrap(self, pin):
        import subprocess
        directory = tempfile.mkdtemp(prefix="cag-pinned-")
        self.addCleanup(shutil.rmtree, directory, True)
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        pinned = re.sub(r"(?m)^RELEASE_REF=.*$", "RELEASE_REF=%s" % pin, script, count=1)
        self.assertNotEqual(pinned, script)
        path = os.path.join(directory, "install-from-github.sh")
        with open(path, "w") as handle:
            handle.write(pinned)
        os.chmod(path, 0o755)

        def run(*args):
            return subprocess.run([path] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True)
        return run

    def test_github_bootstrap_uses_its_release_pin_only_when_no_ref_is_given(self):
        """The release copy needs no --ref; an explicit --ref still wins; a bad pin is refused
        exactly like a bad --ref. Every run stops at host validation, before any network."""
        run = self.pinned_bootstrap("a" * 40)
        proc = run("--host", "https://evil.example/x")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid Canvas host", proc.stderr)          # the pin was accepted
        proc = run("--ref", "main", "--host", HOST)
        self.assertIn("full lowercase hexadecimal", proc.stderr)   # explicit --ref wins, and is checked
        proc = self.pinned_bootstrap("release")("--host", HOST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("full lowercase hexadecimal", proc.stderr)

    def test_release_script_points_release_at_main_plus_one_pin_commit(self):
        """tools/release.sh against a scratch origin: release = the released commit + one
        commit whose bootstrap carries that commit's hash; main and its empty pin untouched."""
        import subprocess
        work = tempfile.mkdtemp(prefix="cag-release-")
        self.addCleanup(shutil.rmtree, work, True)
        bare, repo = os.path.join(work, "origin.git"), os.path.join(work, "repo")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.edu",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.edu", HOME=work)

        def git(*args, cwd=repo):
            return subprocess.run(["git"] + list(args), cwd=cwd, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, universal_newlines=True, check=True).stdout.strip()

        subprocess.run(["git", "init", "--quiet", "--bare", bare], env=env, check=True)
        os.makedirs(os.path.join(repo, "tools"))
        shutil.copy(self.BOOTSTRAP, os.path.join(repo, "install-from-github.sh"))
        shutil.copy(os.path.join(self.ROOT, "tools", "release.sh"), os.path.join(repo, "tools", "release.sh"))
        git("init", "--quiet")
        git("checkout", "--quiet", "-b", "main")
        git("add", "-A")
        git("commit", "--quiet", "-m", "reviewed")
        git("remote", "add", "origin", bare)
        git("push", "--quiet", "origin", "main")
        main_sha = git("rev-parse", "main")

        proc = subprocess.run(["tools/release.sh"], cwd=repo, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("release ->", proc.stdout)
        self.assertEqual(git("rev-parse", "release~1", cwd=bare), main_sha)
        released = git("show", "release:install-from-github.sh", cwd=bare)
        self.assertIn("RELEASE_REF=%s   # pinned by tools/release.sh\n" % main_sha, released)
        self.assertEqual(git("rev-parse", "main", cwd=bare), main_sha)
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(git("status", "--porcelain"), "")
        with open(os.path.join(repo, "install-from-github.sh")) as handle:
            self.assertRegex(handle.read(), r"(?m)^RELEASE_REF=[ \t]*(#.*)?$")

        # a second release is a clean replacement, not a pile of pin commits
        with open(os.path.join(repo, "NOTE"), "w") as handle:
            handle.write("later\n")
        git("add", "NOTE"); git("commit", "--quiet", "-m", "later"); git("push", "--quiet", "origin", "main")
        proc = subprocess.run(["tools/release.sh"], cwd=repo, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(git("rev-parse", "release~1", cwd=bare), git("rev-parse", "main"))
        self.assertEqual(git("rev-list", "--count", "main..release", cwd=bare), "1")

        # the released copy runs without --ref, and stops at host validation before any network
        path = os.path.join(work, "released.sh")
        with open(path, "w") as handle:
            handle.write(released)
        os.chmod(path, 0o755)
        proc = subprocess.run([path, "--host", "https://evil.example/x"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        self.assertIn("invalid Canvas host", proc.stderr)

        # a commit that is not on origin/main is refused
        git("checkout", "--quiet", "-b", "side")
        with open(os.path.join(repo, "SIDE"), "w") as handle:
            handle.write("x\n")
        git("add", "SIDE"); git("commit", "--quiet", "-m", "side"); side = git("rev-parse", "HEAD")
        git("checkout", "--quiet", "main")
        proc = subprocess.run(["tools/release.sh", side], cwd=repo, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("is not on origin/main", proc.stderr)

    def test_github_bootstrap_refuses_a_mutable_ref_before_network(self):
        proc = self.run_bootstrap("--ref", "main", "--host", HOST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("full lowercase hexadecimal commit SHA", proc.stderr)

    def test_github_bootstrap_names_the_xcode_fix_when_git_cannot_run(self):
        """On a Mac, /usr/bin/git is a shim that refuses until the command line tools exist and,
        with Xcode installed, until its license is accepted. Faculty must be told the one
        command, not shown git's message. A scratch copy points GIT_BIN at a fake git."""
        import subprocess
        directory = tempfile.mkdtemp(prefix="cag-xcode-")
        self.addCleanup(shutil.rmtree, directory, True)
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        for message, expected in (
                ("Agreeing to the Xcode/iOS license requires admin privileges, please run 'sudo xcodebuild -license'",
                 "sudo xcodebuild -license accept"),
                ("xcode-select: note: no developer tools were found", "xcode-select --install")):
            with self.subTest(expected=expected):
                fake = os.path.join(directory, "git")
                with open(fake, "w") as handle:
                    handle.write("#!/bin/sh\necho %s >&2\nexit 1\n" % shlex.quote(message))
                os.chmod(fake, 0o755)
                copy = os.path.join(directory, "bootstrap.sh")
                with open(copy, "w") as handle:
                    handle.write(script.replace("GIT_BIN=/usr/bin/git", "GIT_BIN=%s" % fake, 1))
                os.chmod(copy, 0o755)
                proc = subprocess.run([copy, "--ref", "a" * 40, "--host", HOST], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, universal_newlines=True)
                self.assertEqual(proc.returncode, 1)
                self.assertIn(expected, proc.stderr)
                self.assertNotIn("clone", proc.stderr)          # it never reached the network

    def test_github_bootstrap_needs_no_arguments_on_the_release_copy(self):
        """The human command is the bare curl | sh: host and profile default to this
        repository's institution and the reviewed commit is pinned on the release branch. A
        scratch copy with a pin and a fake git proves the defaults are accepted and the run
        gets as far as the first git call."""
        import subprocess
        directory = tempfile.mkdtemp(prefix="cag-defaults-")
        self.addCleanup(shutil.rmtree, directory, True)
        fake = os.path.join(directory, "git")
        with open(fake, "w") as handle:
            handle.write("#!/bin/sh\necho reached-git >&2\nexit 1\n")
        os.chmod(fake, 0o755)
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertIn("DEFAULT_HOST=clemson.instructure.com", script)
        self.assertIn("DEFAULT_PROFILE=specialized-functions", script)
        pinned = re.sub(r"(?m)^RELEASE_REF=.*$", "RELEASE_REF=%s" % ("a" * 40), script, count=1)
        pinned = pinned.replace("GIT_BIN=/usr/bin/git", "GIT_BIN=%s" % fake, 1)
        copy = os.path.join(directory, "install-from-github.sh")
        with open(copy, "w") as handle:
            handle.write(pinned)
        os.chmod(copy, 0o755)
        proc = subprocess.run([copy], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, stdin=subprocess.DEVNULL)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("reached-git", proc.stderr)                 # ref, host and profile all accepted
        self.assertNotIn("--host needs", proc.stderr)

    def test_github_bootstrap_runs_inline_when_it_has_a_terminal(self):
        """Pasted into Terminal, the launcher runs in that window with stdin from /dev/tty and
        skips the 'press Return to close' that only a separate window needs; without a
        terminal (Codex) the Terminal-window path below is unchanged."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        inline = script.index("if { exec 3</dev/tty; } 2>/dev/null; then")
        self.assertLess(script.index('chmod 0700 "$LAUNCHER"'), inline)
        self.assertLess(inline, script.index('"$OPEN_BIN" -g -j -a "$TERMINAL_APP"'))
        self.assertIn('CANVAS_GUARD_INLINE=1 exec /bin/sh "$LAUNCHER" </dev/tty', script)
        self.assertIn('if [ -z "\\${CANVAS_GUARD_INLINE:-}" ]; then', script)
        self.assertIn("/profile/settings", script)               # the token page, named and opened

    def test_github_bootstrap_refuses_an_invalid_host_before_network(self):
        proc = self.run_bootstrap("--ref", "a" * 40, "--host", "https://evil.example/x")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid Canvas host", proc.stderr)

    def test_github_bootstrap_uses_the_absolute_terminal_application(self):
        """Managed Macs may lack both a Terminal name lookup and a .command association."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertIn(
            "TERMINAL_APP=/System/Applications/Utilities/Terminal.app", script
        )
        self.assertIn('"$OPEN_BIN" -a "$TERMINAL_APP" "$LAUNCHER"', script)
        self.assertNotIn('-a Terminal', script)

    def test_github_bootstrap_explains_codex_gui_permission(self):
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertIn("host/GUI execution permission", script)

    def test_github_bootstrap_ends_with_a_read_only_canvas_smoke_test(self):
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertIn("In Canvas, what are my current classes?", script)

    def test_github_bootstrap_warms_terminal_and_retries_the_launcher_once_under_a_lock(self):
        """Seen live on two Macs: a cold-launched Terminal typed the launcher path into a shell
        that was still starting, and zsh got i/tmp/... . The bootstrap launches Terminal first,
        waits for it, opens the launcher, and reopens it once if "running" never appears; the
        launcher's atomic mkdir lock makes a second copy exit without doing anything."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        warm = script.index('"$OPEN_BIN" -g -j -a "$TERMINAL_APP"')
        wait_for_app = script.index("/usr/bin/pgrep -xq Terminal")
        first_open = script.index('"$OPEN_BIN" -a "$TERMINAL_APP" "$LAUNCHER"')
        self.assertLess(warm, wait_for_app)
        self.assertLess(wait_for_app, first_open)
        self.assertIn("open_launcher\nif ! launcher_running; then", script)
        self.assertEqual(script.count("open_launcher\n"), 2)              # one call, one retry
        self.assertIn("launcher_running() { grep -q '\"state\":\"running\"' \"$STATUS_FILE\"", script)
        lock = script.index('mkdir "$INSTALL_ROOT/running.lock" 2>/dev/null || exit 0')
        self.assertLess(script.index('cat > "$LAUNCHER" <<EOF'), lock)
        self.assertLess(lock, script.index('"state":"running"'))         # lock before the status write

    def test_github_bootstrap_tells_the_person_how_to_run_the_launcher_by_hand(self):
        """Terminal types the launcher path into a login shell; a slow shell startup can eat
        the first characters (seen live: zsh received i/tmp/... for /private/tmp/...). The
        bootstrap prints the launcher path as a paste-in fallback, after the open, before the
        status-file line, so a person and Codex both see it."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        fallback = script.index('paste this')
        self.assertLess(script.index('"$OPEN_BIN" -a "$TERMINAL_APP" "$LAUNCHER"'), fallback)
        self.assertLess(fallback, script.index("Completion status file:"))
        self.assertIn("printf '  %s\\n' \"$LAUNCHER\"", script)

    def test_github_bootstrap_emits_a_private_nonsecret_completion_status(self):
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertIn('STATUS_FILE="$INSTALL_ROOT/completion-status.json"', script)
        self.assertIn('"state":"launched"', script)
        self.assertIn('"state":"running"', script)
        self.assertIn('state=succeeded', script)
        self.assertIn('state=failed', script)
        self.assertIn('Completion status file:', script)
        self.assertIn('written before Terminal waits for Return', script)
        self.assertIn('Do not use a fixed polling loop', script)

    def test_github_bootstrap_installs_or_upgrades_from_one_command(self):
        """One pinned command serves a new Mac, an older install, and an up-to-date one: the
        plan's exit status 3 skips sudo, and token entry happens only when the Keychain holds
        no item -- detected by attribute lookup, never by reading the secret."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        self.assertNotIn("upgrade", script.lower())
        self.assertIn('if [ "\\$plan_status" -eq 3 ]; then', script)
        self.assertIn('elif [ "\\$plan_status" -eq 4 ]; then', script)
        self.assertIn('elif [ "\\$plan_status" -eq 5 ]; then', script)
        self.assertIn('"codex_settings":"%s"', script)
        self.assertIn("After an install, the same plan must find nothing left to change.", script)
        self.assertLess(script.index('/usr/bin/sudo "$CHECKOUT/install.sh"'),
                        script.index('./install.sh --plan --profile "$PROFILE" --host "$CANVAS_HOST" >/dev/null'))
        user_only = script.index('"$CHECKOUT/install.sh" --profile "$PROFILE" --host "$CANVAS_HOST"')
        self.assertLess(script.index('-eq 4 ]'), user_only)
        self.assertLess(user_only, script.index('/usr/bin/sudo "$CHECKOUT/install.sh"'))
        self.assertLess(script.index("plan_status=0"), script.index('/usr/bin/sudo "$CHECKOUT/install.sh"'))
        lookup = [line for line in script.splitlines() if "find-generic-password" in line]
        self.assertEqual(len(lookup), 1, lookup)
        self.assertIn('-s canvas-api-guard -a "\\$(id -un)"', lookup[0])
        self.assertNotIn(" -w", lookup[0])
        self.assertNotIn(" -g", lookup[0])
        self.assertIn('"$CHECKOUT/install.sh" --profile "$PROFILE" --host "$CANVAS_HOST"', script)

    def test_github_bootstrap_pauses_for_review_before_sudo(self):
        """The plan is worth printing only if a person can stop before the privileged step."""
        with open(self.BOOTSTRAP) as handle:
            script = handle.read()
        plan = script.index("./install.sh --plan --profile")
        pause = script.index("Press Return to continue with the installation")
        sudo = script.index('/usr/bin/sudo "$CHECKOUT/install.sh"')
        self.assertLess(plan, pause)
        self.assertLess(pause, sudo)
        self.assertIn("if ! read reviewed; then", script)
        self.assertIn("No terminal to confirm on; not installing.", script)
        self.assertLess(script.index("if ! read reviewed; then"), sudo)

    def test_replay_probe_runs_and_reports_the_working_tree_identical_to_head(self):
        import subprocess
        proc = subprocess.run([os.path.join(self.ROOT, "tools", "replay-probe.py"), "HEAD"],
                              cwd=self.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("byte-identical", proc.stdout)


class TestDocumentClaims(unittest.TestCase):
    """The reviewer documents must not describe behaviour this code does not have."""

    ROOT = os.path.dirname(os.path.abspath(__file__))
    README = os.path.join(ROOT, "README.md")
    IT_REVIEW = os.path.join(ROOT, "docs", "IT-REVIEW.md")

    def text(self, path):
        with open(path) as handle:
            return handle.read()

    def test_neither_document_claims_that_every_redirect_is_refused(self):
        for path in (self.README, self.IT_REVIEW):
            with self.subTest(document=os.path.basename(path)):
                text = self.text(path)
                self.assertNotIn("no redirects and no automatic retries", text)
                self.assertNotIn("All redirects are refused", text)
                self.assertIn("no forwarded Host", text)

    def test_both_documents_describe_the_shipped_interface(self):
        readme, review = self.text(self.README), self.text(self.IT_REVIEW)
        for text in (readme, review):
            self.assertNotIn("canvas_api_guard.py count", text)
            self.assertNotIn("timing", text)
            self.assertIn("--all-pages", text)
        self.assertIn('rg -n "urlopen\\(|build_opener|\\.open\\("', review)
        self.assertIn("test_canvas_api_operations.py", review)
        self.assertIn("submission-reviews", review)
        self.assertNotIn("clemson.instructure.com", readme)


if __name__ == "__main__":
    unittest.main()
