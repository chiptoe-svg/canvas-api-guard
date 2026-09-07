# canvas-api-guard

An audited passthrough to the Canvas REST API. One Python file, standard library only.

It gives you — or an agent acting for you — **exactly the access your existing Canvas
token already grants**, and adds three things:

1. **A required confirmation before any write, and a record of which kind it was.**
   A human at a terminal (`"confirmation": "human-tty"`), or an explicit `--yes` from a
   script or an agent (`"confirmation": "yes-flag"`). Under Codex the person approves the
   write in Codex's own prompt and Codex passes `--yes` through; see "Using it from Codex".
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
- Under Codex, it does **not** make Codex safe. The sandbox is Codex's boundary and the
  rules file is Codex's prompt; both live in the user's home directory. A write that
  misses the rules falls back to the sandbox, fails there, and Codex asks the person to
  escalate it, which is still a human prompt as long as the reviewer is `user`.
- It does **not** change where read data goes. Every roster or grade it returns flows
  through the agent to its provider. That is a data-agreement question, not a tool one.
- It does **not** run on Windows. macOS (keychain) and Linux (secret service) only.

## Install

```sh
sudo ./install.sh
```

macOS or Linux. That puts the script at `/usr/local/libexec/canvas_api_guard.py`, owned by
root, mode `0555`: the invoking user (and any agent running as them) can execute it but not
edit it. It creates `~/.canvas-api-guard/audit.jsonl` mode `0600`, and if `~/.codex` exists
it installs the Codex rules file and skill there. It prints two optional hardening commands
(immutable script, append-only log) and does not run them.

Then, as yourself:

```sh
/usr/local/libexec/canvas_api_guard.py --set-token      # pasted, not echoed, read back to check
echo '{"host": "school.instructure.com"}' > ~/.canvas-api-guard/config.json
```

The token goes into the macOS keychain or the Linux secret service (`secret-tool`, from
`libsecret-tools`). There is no file and no environment variable, and `--set-token` reads
the token back before it reports success. The token is only ever sent to the host in that
file; `--host` must match it, and is otherwise accepted only under `--dry-run`.

## Usage

Paths may be written `/api/v1/courses/123`, `api/v1/courses/123` or `courses/123`.
Anything containing a scheme, a host, or `..` is refused.

**Flags follow the verb**, not the program name: `canvas_api_guard.py put <path> --host
... --dry-run`, never `canvas_api_guard.py --dry-run put <path>`. (`--set-token` is the
one exception; it takes no verb.)

Write the command out in full every time. Codex's approval rules match the literal
command, so a variable, an alias, a wrapper script or a relative path after a `cd`
matches no rule and lands in the sandbox instead of in front of a person.

```sh
# read - no confirmation
/usr/local/libexec/canvas_api_guard.py get courses/123
/usr/local/libexec/canvas_api_guard.py get "courses/123/students?per_page=100" -o json

# see exactly what would be sent, without sending it or reading the token
/usr/local/libexec/canvas_api_guard.py put courses/123/assignments/9/submissions/7 \
      -d '{"submission": {"posted_grade": 95}}' --dry-run

# write from a terminal - prompts, and records confirmation: human-tty
/usr/local/libexec/canvas_api_guard.py put courses/123/assignments/9/submissions/7 \
      -d '{"submission": {"posted_grade": 95}}'

# write from a script or an agent - must pass --yes, recorded as confirmation: yes-flag
/usr/local/libexec/canvas_api_guard.py patch courses/123/assignments/9 \
      -d '{"assignment": {"points_possible": 20}}' --yes

# create - the new object is read back by its id (or Location) and printed
/usr/local/libexec/canvas_api_guard.py post courses/123/assignments \
      -d '{"assignment": {"name": "Lab 4"}}'

# destroy - the object is shown before you confirm, and read back afterwards
/usr/local/libexec/canvas_api_guard.py delete courses/123/assignments/9
```

Without a TTY and without `--yes`, a write is refused **before the credential store is
touched, before the pre-read, and before any network call** — so the refusal costs nothing and
leaks nothing. That is the case an agent hits, and it is the point of the tool: an
unattended write either carries `--yes` and is logged as `yes-flag`, or it does not happen
at all and is logged as `refused-no-tty`.

With a terminal the ordering is different on purpose: the pre-read runs first, so the
prompt can show you what is about to change before you answer.

## Using it from Codex

The point of this tool is that a faculty member can let Codex work on their Canvas course
without ever handing Codex the token, and without a write leaving the machine that a
person did not approve. Three files in `codex/` do that, and `install.sh` puts two of
them in place:

- **`codex/canvas-api-guard.rules`** → `~/.codex/rules/`. Codex rules: guard reads run
  without a prompt; guard writes (`post`, `put`, `patch`, `delete`, by name, by installed
  path, or through `python3`) make Codex stop and show the person the full command
  before running it; reading the credential store is forbidden. Check any command with
  `codex execpolicy check --rules codex/canvas-api-guard.rules -- <command>`.
- **`codex/skills/canvas-api-guard/SKILL.md`** → `~/.codex/skills/`. The skill Codex
  loads when a task mentions Canvas: how to call the guard, dry-run first, follow
  `next:` on lists, student text is data, student work stays local.
- **`codex/config.toml`**: three lines to merge into `~/.codex/config.toml`, with the
  reason for each. The one that matters most is `approvals_reviewer = "user"`: without it
  Codex's reviewer model may approve on your behalf.

What a write looks like from the faculty member's side: Codex runs the command with
`--dry-run` and shows the exact request; they say yes; Codex runs it with `--yes` and
**Codex itself stops and shows them the command** before it runs; they approve; the guard
pre-reads, writes, reads back, and prints `field before -> after (match: True)`. The log
records that write as `confirmation: yes-flag`, because the person's approval happened in
Codex's prompt, which the guard cannot see. Codex's own session transcript records the
approval, and Canvas records the API call server-side: three independent records.

Inside Codex's sandbox the guard cannot run at all (no network, no credential store); the
`allow` and `prompt` rules are what let it run outside. That is also why a 0600 file would
be a worse place for the token than the keychain: the sandbox can read the file and cannot
reach the keychain.

## The log

`~/.canvas-api-guard/audit.jsonl`, mode 0600, one JSON object per line, `--log-path` to
move it. `--log-path` moves the log only; the host always comes from
`~/.canvas-api-guard/config.json`. Four kinds of line:

- `event: request` — written and fsynced **before** the call: timestamp, verb, path, url,
  `kind` (read or write), `confirmation`, `dry_run`, and for writes the request body.
- `event: response` — after the call: status, ok, bytes. Never the response body.
- `event: evidence` — the before/after summary of a write, with the confirmation mode.
- `event: refusal` — a call that was refused before it was made, and stands alone: no
  request followed. `kind: write` with `confirmation: refused-no-tty` is a write that could
  not be confirmed; `kind: host` is a call whose host was not the one on record.

Every line also carries `source`: whether stdin was a terminal, the parent process name,
and the names (never the values) of agent markers found in the environment, such as
`CODEX_SANDBOX`. It is a hint for matching a line to a Codex transcript or a terminal
session, not an identity; the `confirmation` field is the statement of who confirmed a
write. Reads are logged too, deliberately: the log says what was looked at, never what
came back.

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

`canvas_api_guard.py` is one file and reads top to bottom: threat model, constants, token,
logging, host pinning, the one request function, confirmation, evidence, the verbs,
argparse, main. Every claim below is a command you can run.

**1. Exactly one place makes a network call.**

```
$ grep -c "urlopen(" canvas_api_guard.py
1
```

**2. The token is read in one function and used on one line.**

```
$ grep -n "read_token()" canvas_api_guard.py
```

Four hits: the banner comment, the definition, the one use in `send_request()` (the line
that builds the `Authorization` header), and the read-back inside `set_token()` that checks
the store worked. `credential_command()` is the only function that builds a credential-store
command; the two tool names live in the constants `SECURITY_BIN` and `SECRET_TOOL` beside it.
Under `--dry-run`, and on a refused write, execution never reaches the use.

**3. Every URL is built by the host-pinning function.**

```
$ grep -n "https://" canvas_api_guard.py
```

One hit inside `canvas_url()`; `next_link()` parses a URL Canvas sent and refuses one
whose host differs. Redirects are refused (`RefuseRedirects`), so the followed URL is always
the built one: `urlopen` would otherwise forward the `Authorization` header to the new
location, another host or an `http://` downgrade included.

**4. The log is written before the request.** In `send_request()`, the `"event": "request"`
log line precedes the one network call:

```
$ grep -n '"event": "request"\|urlopen(' canvas_api_guard.py
```

Two hits, in that order: the request log line first, the `urlopen(` call after it.

**5. The confirmation refusal, cold: no token, no Canvas account, no network.**

```
$ echo "" | ./canvas_api_guard.py delete courses/1/assignments/2 \
      --host example.instructure.com --log-path /tmp/demo.jsonl
canvas-api-guard: refusing to write without confirmation: stdin is not a terminal; pass --yes to confirm non-interactively, which will be recorded in the log
$ echo $?
2
```

**6. Under Codex, the credential store is out of reach inside the sandbox.**

```
$ codex sandbox --log-denials security find-generic-password -s canvas-api-guard -a $USER -w
...
(security) mach-lookup com.apple.SecurityServer
```

**7. Each rule decision.**

```
$ codex execpolicy check --rules codex/canvas-api-guard.rules -- canvas_api_guard.py get courses
{"matchedRules":[...],"decision":"allow"}
$ codex execpolicy check --rules codex/canvas-api-guard.rules -- canvas_api_guard.py put courses/1 -d '{}' --yes
{"matchedRules":[...],"decision":"prompt"}
$ codex execpolicy check --rules codex/canvas-api-guard.rules -- security find-generic-password -s canvas-api-guard -w
{"matchedRules":[...],"decision":"forbidden"}
```

**8. The host is pinned to the config file, not to a flag.** Cold, with no
`~/.canvas-api-guard/config.json`:

```
$ ./canvas_api_guard.py get courses --host other.example.com --log-path /tmp/demo.jsonl
canvas-api-guard: no Canvas host configured; write /Users/you/.canvas-api-guard/config.json with {"host": "school.instructure.com"}. --host alone is accepted only under --dry-run, so the token is never sent to a host that is not on record
$ echo $?
2
```

With a config present, a `--host` that differs from the recorded one is refused the same
way, before the credential store, the pre-read and any network call. This matters because a
Codex rule matches a command prefix and cannot constrain the flags after it: an allowed
`get` carries whatever `--host` the agent wrote, so the guard — not the rules file — is what
keeps the token on one host.

The test suite proves the same properties by running them, including a fake `urlopen` that
reads the log from inside the call, and a matrix test that evaluates the shipped rules
file with Codex's own checker (skipped when Codex is absent):

```sh
python3 -m unittest -v      # 51 tests; no test reaches the network or a real credential store
```

Requires Python 3.9+. No pip, no venv, no dependencies.
