#!/usr/bin/env python3
"""Tests for canvas_api_guard. Stdlib unittest only: python3 -m unittest -v

Every test that touches the request path replaces urllib.request.urlopen, so the suite
never reaches the network. Two tests prove that directly.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
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

    def run_main(self, argv, stdin_is_tty=False):
        """Run main() with private fixed config/log paths and captured output."""
        return self.run_argv(list(argv), stdin_is_tty)

    def run_argv(self, argv, stdin_is_tty=False):
        """Run main() on exactly this argv, with the same patches run_main uses."""
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
        self.pin_config(self.temp_config(HOST, profile="level-2"))
        with self.no_keychain(), self.no_network():
            code, _ = self.run_argv(["get", "courses"])
        self.assertEqual(code, 2)
        self.assertIn("implements level-1 only", self.last_stderr)


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
        student = {"id": 3, "name": "Student Example"}
        responses = [FakeResponse(payload={"id": 3, "user_id": 3, "user": student,
                                           "posted_grade": 60}),             # before
                     FakeResponse(payload={"id": 3, "user_id": 3,
                                           "posted_grade": 95}),             # the write
                     FakeResponse(payload={"id": 3, "user_id": 3, "user": student,
                                           "posted_grade": 95})]             # read-back
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 0)
        self.assertIn("posted_grade", output)
        self.assertIn("60 -> 95", output)
        self.assertIn("match: True", output)
        self.assertIn("Student Example", output)
        evidence = [line for line in self.log_lines() if line["event"] == "evidence"][-1]
        self.assertEqual(evidence["target"], {"student_name": "Student Example", "user_id": 3})
        self.assertEqual(evidence["verification"], "passed")

    def test_post_without_an_id_or_location_is_uncertain_and_nonzero(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(status=201, headers={}, payload={"ok": True})
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 2)
        self.assertIn("neither an id nor a usable Location header", output)
        self.assertIn("WRITE STATUS UNCERTAIN", output)

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

    def test_post_readback_mismatch_is_uncertain_and_nonzero(self):
        responses = [FakeResponse(status=201, payload={"id": 42, "name": "Lab 4"}),
                     FakeResponse(payload={"id": 42, "name": "Different name"})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["post", "courses/1/assignments", "--yes",
                 "-d", '{"assignment": {"name": "Lab 4"}}'])
        self.assertEqual(code, 2)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertIn("created object did not match requested field", output)

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

    def test_delete_reports_that_the_object_is_gone(self):
        responses = [FakeResponse(payload={"id": 2, "name": "Lab 4"}),  # before
                     FakeResponse(status=200, payload={"id": 2}),       # the delete
                     urllib.error.HTTPError("https://" + HOST, 404, "Not Found", {}, None)]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(["delete", "courses/1/assignments/2", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("read-back after delete: 404 gone", output)

    def test_update_readback_failure_is_uncertain_and_nonzero(self):
        responses = [FakeResponse(payload={"id": 3, "posted_grade": 60}),
                     FakeResponse(payload={"id": 3, "posted_grade": 95}),
                     OSError("network unavailable")]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 2)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertIn("read-back failed", output)

    def test_update_mismatch_is_uncertain_and_nonzero(self):
        responses = [FakeResponse(payload={"id": 3, "posted_grade": 60}),
                     FakeResponse(payload={"id": 3, "posted_grade": 95}),
                     FakeResponse(payload={"id": 3, "posted_grade": 60})]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(
                ["put", "courses/1/assignments/2/submissions/3", "--yes",
                 "-d", '{"submission": {"posted_grade": 95}}'])
        self.assertEqual(code, 2)
        self.assertIn("did not match", output)

    def test_delete_transport_failure_is_not_reported_as_gone(self):
        responses = [FakeResponse(payload={"id": 2, "name": "Lab 4"}),
                     FakeResponse(status=200, payload={"id": 2}),
                     OSError("network unavailable")]
        with mock.patch("urllib.request.urlopen", side_effect=responses):
            code, output = self.run_main(["delete", "courses/1/assignments/2", "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("WRITE STATUS UNCERTAIN", output)
        self.assertNotIn("404 gone", output)


class TestRedirectsAreRefused(unittest.TestCase):
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
                mock.patch.object(guard, "trusted_linux_secret_tool",
                                  return_value="/usr/bin/secret-tool"), \
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


class TestSourceField(GuardTestCase):
    def test_every_line_says_how_the_guard_was_invoked(self):
        with mock.patch.dict(guard.os.environ, {"CODEX_SANDBOX": "seatbelt"}), \
                mock.patch.object(guard, "parent_process_name", return_value="codex"):
            for name in guard.AGENT_MARKERS:            # isolate from this process's own env
                if name != "CODEX_SANDBOX":
                    guard.os.environ.pop(name, None)
            code, _ = self.run_main(["get", "courses/1", "--dry-run"])
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
            code, _ = self.run_main(["get", "courses/1", "--dry-run"], stdin_is_tty=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.log_lines()[0]["source"],
                         {"tty": True, "parent": "zsh", "agent_env": []})

    def test_a_failed_parent_lookup_is_null_and_does_not_break_the_call(self):
        with mock.patch.object(guard.os, "getppid", side_effect=OSError("no ppid")):
            self.assertIsNone(guard.parent_process_name())
            code, _ = self.run_main(["get", "courses/1", "--dry-run"])
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


def find_codex():
    """The Codex CLI: on PATH, or bundled in the ChatGPT app. None if absent."""
    import shutil
    for candidate in (shutil.which("codex"), "/Applications/ChatGPT.app/Contents/Resources/codex"):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    return None


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

    def test_the_matrix(self):
        rows = [
            (["/usr/local/libexec/canvas_api_guard.py", "get", "courses"], "allow"),
            (["/usr/local/libexec/canvas_api_guard.py", "put", "courses/1/assignments/2", "-d", "{}", "--yes"], "prompt"),
            (["/usr/local/libexec/canvas_api_guard.py", "post", "courses/1/assignments", "-d", "{}", "--yes"], "prompt"),
            (["/usr/local/libexec/canvas_api_guard.py", "patch", "courses/1", "-d", "{}", "--yes"], "prompt"),
            (["/usr/local/libexec/canvas_api_guard.py", "delete", "courses/1", "--yes"], "prompt"),
            (["canvas_api_guard.py", "get", "courses/1"], "none"),
            (["./canvas_api_guard.py", "put", "courses/1", "--yes"], "none"),
            (["python3", "/usr/local/libexec/canvas_api_guard.py", "put", "courses/1", "--yes"], "none"),
            (["security", "find-generic-password", "-s", "canvas-api-guard", "-w"], "forbidden"),
            (["secret-tool", "lookup", "service", "canvas-api-guard"], "forbidden"),
            (["/usr/bin/security", "find-generic-password", "-s", "canvas-api-guard", "-w"],
             "forbidden"),
            (["/usr/bin/secret-tool", "lookup", "service", "canvas-api-guard"], "forbidden"),
            (["security", "list-keychains"], "none"),
        ]
        for argv, want in rows:
            self.assertEqual(self.decision(argv), want, " ".join(argv))

    def test_every_guard_write_verb_has_a_prompt_rule(self):
        """If the guard grows a verb, the rules file must grow with it."""
        with open(self.RULES) as handle:
            rules = handle.read()
        for verb in sorted(guard.VERBS):
            self.assertIn('"%s"' % verb, rules, "verb %r is not in the rules file" % verb)


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

    def test_plan_lists_every_reviewed_hash_and_destination(self):
        proc = self.run_installer("--plan", "--host", HOST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for label in ("guard sha:", "rules sha:", "skill sha:", "Canvas host:",
                      "executable:", "config:", "audit log:", "Codex rules:",
                      "Codex skill:"):
            self.assertIn(label, proc.stdout)
        self.assertIn("no changes made", proc.stdout)
        self.assertIn("does not read or store a token", proc.stdout)

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

    def test_github_bootstrap_refuses_a_mutable_ref_before_network(self):
        proc = self.run_bootstrap("--ref", "main", "--host", HOST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("full lowercase hexadecimal commit SHA", proc.stderr)

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


if __name__ == "__main__":
    unittest.main()
