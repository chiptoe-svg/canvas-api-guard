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

**Flags follow the verb**, not the program name: `canvas_api_guard.py put <path> --host
... --dry-run`, never `canvas_api_guard.py --dry-run put <path>`. (`--set-token` is the
one exception; it takes no verb.)

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

Without a TTY and without `--yes`, a write is refused **before the keychain is touched,
before the pre-read, and before any network call** — so the refusal costs nothing and
leaks nothing. That is the case an agent hits, and it is the point of the tool: an
unattended write either carries `--yes` and is logged as `yes-flag`, or it does not happen
at all and is logged as `refused-no-tty`.

With a terminal the ordering is different on purpose: the pre-read runs first, so the
prompt can show you what is about to change before you answer.

## The log

`~/.canvas-api-guard/audit.jsonl`, mode 0600, one JSON object per line, `--log-path` to
move it. Three kinds of line:

- `event: request` — written and fsynced **before** the call: timestamp, verb, path, url,
  `kind` (read or write), `confirmation`, `dry_run`, and for writes the request body.
- `event: response` — after the call: status, ok, bytes. Never the response body.
- `event: evidence` — the before/after summary of a write, with the confirmation mode.
- `event: refusal` — a write that could not be confirmed, `confirmation: refused-no-tty`.
  It stands alone: no request was made.

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
argparse, main. Four properties you can grep for, and one you can run cold with no
token and no Canvas account.

**1. Exactly one place makes a network call.**

```
$ grep -n "urlopen" canvas_api_guard.py
135:# There is exactly one call to urlopen in this file. Everything else routes through here.
160:        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
```

**2. The token is in exactly two places.** One function reads it from the keychain; one
line puts it into a header. Nothing else touches it.

```
$ grep -n "read_token_from_keychain" canvas_api_guard.py
46:# The token is in exactly two places in this file: read_token_from_keychain() reads it, and one
50:def read_token_from_keychain():
157:    headers["Authorization"] = "Bearer " + read_token_from_keychain()     # the only use
```

Note line 157: under `--dry-run`, and on a refused write, execution never reaches it — so
neither can leak a token that was never read.

**3. Every URL is built by the host-pinning function, and it is called by the one request
function before anything else.**

```
$ grep -n "canvas_url\|urlopen" canvas_api_guard.py | head -5
 99:# Every URL this tool builds comes from canvas_url(). A path carrying a scheme, a netloc or a
121:def canvas_url(host, path):
135:# There is exactly one call to urlopen in this file. Everything else routes through here.
139:    url, npath = canvas_url(cfg.host, path), normalise_path(path)
160:        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
```

**4. The log is written before the request, not after.** Line 141 is the `request` line;
the call is on line 160.

```
$ grep -n "log_event\|urlopen(" canvas_api_guard.py | sed -n '1,4p'
 84:def log_event(log_path, fields):
141:    log_event(cfg.log_path, {
160:        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
164:        log_event(cfg.log_path, {"event": "response", "verb": method, "path": npath, "ok": False,
```

**5. See the confirmation refusal for yourself — no token, no Canvas account, no network.**
Clone the repo and run this cold:

```
$ echo "" | ./canvas_api_guard.py delete courses/1/assignments/2 \
      --host example.instructure.com --log-path /tmp/demo.jsonl
canvas-api-guard: refusing to write without confirmation: stdin is not a terminal; pass --yes to confirm non-interactively, which will be recorded in the log
$ echo $?
2
$ cat /tmp/demo.jsonl
{"confirmation": "refused-no-tty", "event": "refusal", "kind": "write", "path": "/api/v1/courses/1/assignments/2", "pid": 75350, "timestamp": "2026-09-07T13:18:05Z", "verb": "DELETE"}
```

`echo "" |` makes stdin a pipe rather than a terminal, which is exactly what an agent or a
CI job looks like. The refusal is `refuse_unconfirmed_write()`, called from `main()` before
the verb runs:

```
$ grep -n "refuse_unconfirmed_write" canvas_api_guard.py
184:# A write that cannot be confirmed is refused by refuse_unconfirmed_write() before anything
186:def refuse_unconfirmed_write(cfg, verb, path):
391:        refuse_unconfirmed_write(cfg, args.verb, args.path)
```

`test_the_refusal_precedes_the_keychain_and_every_network_call` proves the ordering: it
replaces both the keychain reader and `urlopen` with functions that raise, and every write
verb still refuses cleanly.

The test suite proves the same four properties by running them, including a test whose
fake `urlopen` reads the log from inside the call to show the line is already on disk:

```sh
python3 -m unittest -v      # 23 tests; no test reaches the network
```

Requires Python 3.9+ (the version macOS ships). No pip, no venv, no dependencies.
