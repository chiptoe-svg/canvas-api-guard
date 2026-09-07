# canvas-api-guard

An audited passthrough to the Canvas REST API. One Python file, standard library only.

It gives you — or an agent acting for you — **exactly the access your existing Canvas
token already grants**, and adds three things:

1. **A required confirmation before any write, and a record of which kind it was.**
   A human at a terminal, or an explicit `--yes` from a script. The log says which:
   `"confirmation": "human-tty"` or `"confirmation": "yes-flag"`.
2. **Before/after evidence.** Every write reads the object first, shows what is about to
   change, and reads it back afterwards so you see what Canvas actually stored.
3. **An append-only record, written before the fact.** One JSON object per line, fsynced
   *before* the request is sent, with a second line for the outcome.

It adds **no capability**. Everything it can do, the token could already do with `curl`.

## What it does not do

This matters more than the guarantees, so it comes second rather than last:

- It does **not** restrict what the token can reach. Scope is set in Canvas, not here.
- It does **not** stop anyone using `curl`, a browser, or the Canvas UI instead. It is a
  chosen path, not a chokepoint.
- It does **not** contain a determined user, or an agent that can run `sudo`. Such an
  actor can edit the script, delete the log, or bypass the tool entirely. The hardening
  step below raises that cost; it does not eliminate it.
- It does **not** protect the log against root.
- It does **not** verify that the confirming human understood the change — only that a
  confirmation of a recorded kind occurred.

## Install

```sh
sudo ./install.sh
```

That puts the script at `/usr/local/libexec/canvas_api_guard.py`, owned by root, mode
`0555`: the invoking user (and any agent running as them) can execute it but not edit it.
It also creates `~/.canvas-api-guard/audit.jsonl` mode `0600`. The installer prints two
optional `chflags` commands for further hardening and does not run them.

Then store your token and name your Canvas host:

```sh
/usr/local/libexec/canvas_api_guard.py --set-token          # prompts; not echoed
echo '{"host": "school.instructure.com"}' > ~/.canvas-api-guard/config.json
```

The token goes into the macOS keychain (`security add-generic-password`, service
`canvas-api-guard`), read from a prompt — never from argv, a file, or an environment
variable. If the keychain is unavailable the tool refuses to run; there is no fallback.
The host is not a secret and lives in a plain file beside the log; `--host` overrides it.

## Usage

Paths may be written `/api/v1/courses/123`, `api/v1/courses/123` or `courses/123`.
Anything containing a scheme, a host, or `..` is refused.

```sh
guard=/usr/local/libexec/canvas_api_guard.py

# read - no confirmation
$guard get courses/123
$guard get "courses/123/students?per_page=100" -o json

# see exactly what would be sent, without sending it or reading the token
$guard put courses/123/assignments/9/submissions/7 \
      -d '{"submission": {"posted_grade": 95}}' --dry-run

# write from a terminal - prompts, and records confirmation: human-tty
$guard put courses/123/assignments/9/submissions/7 \
      -d '{"submission": {"posted_grade": 95}}'

# write from a script or an agent - must pass --yes, recorded as confirmation: yes-flag
$guard patch courses/123/assignments/9 -d '{"assignment": {"points_possible": 20}}' --yes

# create - the new object is read back by its id (or Location) and printed
$guard post courses/123/assignments -d '{"assignment": {"name": "Lab 4"}}'

# destroy - the object is shown before you confirm, and read back afterwards
$guard delete courses/123/assignments/9
```

Without a TTY and without `--yes`, a write is refused before anything is sent. That is the
case an agent hits, and it is the point of the tool: an unattended write leaves a log line
that says a machine authorised it.

## The log

`~/.canvas-api-guard/audit.jsonl`, mode 0600, one JSON object per line, `--log-path` to
move it. Three kinds of line:

- `event: request` — written and fsynced **before** the call: timestamp, verb, path, url,
  `kind` (read or write), `confirmation`, `dry_run`, and for writes the request body.
- `event: response` — after the call: status, ok, bytes. Never the response body.
- `event: evidence` — the before/after summary of a write, with the confirmation mode.

The token never appears on any line. A `request` line with no matching `response` line
means the call was attempted and did not complete.

```sh
# every write, as it was recorded
grep '"kind": "write"' ~/.canvas-api-guard/audit.jsonl

# every write as one line: when, what, and who confirmed it
python3 -c 'import json,sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get("kind") == "write":
        print(r["timestamp"], r["verb"], r["path"], r["confirmation"])' \
  ~/.canvas-api-guard/audit.jsonl
```

## For reviewers

`canvas_api_guard.py` is under 400 lines and reads top to bottom: threat model, constants,
token, logging, host pinning, the one request function, confirmation, evidence, the verbs,
argparse, main. Four properties, four greps.

**1. Exactly one place makes a network call.**

```
$ grep -n "urlopen" canvas_api_guard.py
137:# There is exactly one call to urlopen in this file. Everything else routes through here.
163:        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
```

**2. The token is in exactly two places.** One function reads it from the keychain; one
line puts it into a header. Nothing else touches it.

```
$ grep -n "read_token_from_keychain" canvas_api_guard.py
47:# The token is in exactly two places in this file: read_token_from_keychain() reads it, and one
51:def read_token_from_keychain():
160:    headers["Authorization"] = "Bearer " + read_token_from_keychain()     # the only use
```

Note line 160: under `--dry-run` the function returns before reaching it, so a dry run
cannot leak a token it never read.

**3. Every URL is built by the host-pinning function, and it is called by the one request
function before anything else.**

```
$ grep -n "canvas_url\|urlopen" canvas_api_guard.py | head -5
101:# Every URL this tool builds comes from canvas_url(). A path carrying a scheme, a netloc or a
123:def canvas_url(host, path):
137:# There is exactly one call to urlopen in this file. Everything else routes through here.
141:    url, npath = canvas_url(cfg.host, path), normalise_path(path)
163:        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
```

**4. The log is written before the request, not after.** Line 143 is the `request` line;
the call is on line 163.

```
$ grep -n "log_event\|urlopen(" canvas_api_guard.py | sed -n '1,4p'
86:def log_event(log_path, fields):
143:    log_event(cfg.log_path, {
163:        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
167:        log_event(cfg.log_path, {"event": "response", "verb": method, "path": npath,
```

The test suite proves the same four properties by running them, including a test whose
fake `urlopen` reads the log from inside the call to show the line is already on disk:

```sh
python3 -m unittest -v      # 22 tests; no test reaches the network
```

Requires Python 3.9+ (the version macOS ships). No pip, no venv, no dependencies.
