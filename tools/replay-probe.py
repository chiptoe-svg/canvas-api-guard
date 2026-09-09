#!/usr/bin/env python3
"""Replay probe: is a stock installation of the guard byte-identical before and after?

    tools/replay-probe.py BASE_COMMIT        # compares BASE_COMMIT's guard with the working tree

Exports BASE_COMMIT with git archive into a temp dir, then runs the same seven scenarios
against both guards with urlopen and read_token replaced, the config exactly as install.sh
writes it, and diffs: audit records (timestamp and pid normalised), stdout, stderr, exit codes,
--help and --version. Exit 0 = identical, 1 = differs (the diff is printed), 2 = usage.
Nothing here touches the network, a credential store, or the installed guard.
The version string is normalised; a release bump is not a behaviour change. Everything else must match.
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
    # Normalise version strings: replace this tree's USER_AGENT with canonical form
    for result in results.values():
        result["stdout"] = result["stdout"].replace(guard.USER_AGENT, "canvas-api-guard/<version>")
        result["stderr"] = result["stderr"].replace(guard.USER_AGENT, "canvas-api-guard/<version>")
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
