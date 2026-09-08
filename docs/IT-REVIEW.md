# IT review: canvas-api-guard Level 1 and optional Level 2

## Decision requested

Approve a controlled Codex-only deployment of `canvas-api-guard` as a safer local transport
for an instructor's existing Canvas API token. This is not a request for additional Canvas
permissions, a shared service account, an MCP server, or ChatGPT Work integration.

## Review boundary

The runtime and installation boundary consists of:

| File | Responsibility |
|---|---|
| `canvas_api_guard.py` | credential retrieval, host/path validation, HTTP, audit, confirmation, and evidence |
| `install.sh` | no-network plan and root-owned installation |
| `install-from-github.sh` | immutable-commit download and visible macOS Terminal launcher |
| `codex/canvas-api-guard.rules` | installed-path reads allowed; installed-path writes prompt; known credential reads forbidden |
| `codex/config.toml` | recommended Codex sandbox and human-review settings |
| `codex/skills/canvas-api-guard/SKILL.md` | operating procedure and data-handling instructions |
| `test_canvas_api_guard.py` | offline Level 1 security and behavior tests |
| `level2/` | optional specialized operations, installed only with `--profile level-2` |

The documents under `docs/superpowers/` are historical design/implementation records, not
runtime components.

## Intended data flow

```text
Instructor request
  -> Codex skill and execution rules
  -> root-owned /usr/local/libexec/canvas_api_guard.py
  -> user Keychain or Secret Service token lookup
  -> fixed https://<installed Canvas host>/api/v1/...
  -> Canvas response
  -> Codex result in the Clemson-approved ChatGPT Edu account

Local evidence
  -> fixed ~/.canvas-api-guard/audit.jsonl (0700 directory, 0600 file)
```

The bearer token is read only by the installed process and placed only in the Authorization
header for the fixed host. It is never accepted through argv, environment, or file input and
is never printed or logged.

## Deployment assumptions

1. The user authenticates to Canvas with an individually issued token carrying only their
   existing Canvas permissions.
2. Canvas content is processed only in the institution-approved Clemson ChatGPT Edu account.
   The repository does not independently prove the institution's contractual or policy
   approval; deployment owners must verify the effective account and workspace.
3. The workstation is managed and the local audit log is handled as confidential education
   data because it can contain names, grades, and before/after changes.
4. `approvals_reviewer = "user"` remains effective, so a person—not an automated reviewer—
   answers Codex prompts for Canvas writes.
5. The installed script and system configuration remain root-owned and unmodified.

## Security objectives and implementation

### Keep the token out of agent-controlled storage

- macOS uses the fixed `/usr/bin/security` executable. A Python standard-library pseudoterminal
  relays the user's keystrokes directly to `security` and rewrites only its two misleading display
  labels as `Canvas API token (hidden):` and `Retype Canvas API token (hidden):`. The guard never
  captures the token during entry; it does not enter argv, a file, or an environment variable.
- Linux accepts only a fixed, root-owned, non-group/world-writable `secret-tool` executable
  at `/usr/bin/secret-tool` or `/usr/local/bin/secret-tool`.
- Account selection uses the effective UID's password-database entry rather than `USER` or
  `LOGNAME` environment variables.
- Dry-runs and refused non-TTY writes do not read the token.

### Keep the token on one destination

- `/usr/local/etc/canvas-api-guard/config.json` is the only host configuration.
- It must be a regular file owned by root or the current user and not writable by group or
  others. The installer creates it as root-owned `0644`.
- There is no production `--host` option.
- The URL builder forces HTTPS and rejects paths containing a scheme, host, traversal,
  whitespace, or backslash.
- All redirects are refused, including same-host redirects.
- Pagination links are returned only when their host matches; they are never followed
  automatically.

### Require and record write approval

- `POST`, `PUT`, `PATCH`, and `DELETE` require a TTY confirmation or explicit `--yes`.
- A non-TTY write without `--yes` is refused before credential or network access.
- The Codex rules authorize only `/usr/local/libexec/canvas_api_guard.py`.
- Installed-path reads are allowed; installed-path writes prompt the user.
- Source-tree copies, interpreter invocations, aliases, and wrappers match no allow rule.
- Known direct Keychain/Secret Service read commands are forbidden by the rules file.

`--yes` is evidence that the user approved in Codex's prompt; it is not cryptographic proof
of identity. The local audit, Codex transcript, and Canvas server record provide separate
correlation sources.

### Fail closed after consequential writes

- `PUT`/`PATCH`: all requested leaf fields must match the read-back.
- `POST`: Canvas must return an ID or usable same-host Location, and every requested field must
  match the created object's read-back.
- `DELETE`: the read-back must return HTTP 404.
- Any mismatch, timeout, transport error, 401, 403, 5xx, missing created-object location, or
  still-present delete target exits nonzero as `WRITE STATUS UNCERTAIN`.
- No automatic write retry is implemented.

### Produce useful, protected audit evidence

- The fixed log path has no command-line override.
- The directory must be owned by the current user and mode `0700`.
- The file is opened with append and no-follow semantics where supported and must be a
  regular user-owned `0600` file.
- A request event is flushed and fsynced before network I/O.
- Response bodies and credentials are excluded.
- Response timing records contain only numeric request-audit, credential, network, and
  total-before-response-audit durations; they do not contain credentials or response bodies.
- Write evidence includes the Canvas user ID and student name when Canvas returns the user
  object, plus requested/before/after fields and the verification result.

The audit log is not protected from root and has no retention, forwarding, or rotation policy.
Those remain deployment controls.

## Installation controls

`install.sh --plan --host <host>` runs without root and changes nothing. It reports:

- source Git revision and whether tracked files differ;
- SHA-256 of the exact guard, Codex rule, and skill sources;
- Canvas host;
- every destination, owner, and mode;
- an explicit statement that it performs no Canvas or credential operation.

Actual installation:

- requires root;
- refuses a tracked, modified Git checkout unless `--allow-dirty` is explicit;
- installs the executable and host configuration as root-owned;
- backs up differing executable, config, Codex rule, and skill files;
- refuses symbolic-link destinations and preserves existing Codex directory modes;
- verifies the installed guard, rule, and skill hashes against the reviewed sources;
- creates but never populates the credential store;
- makes no network call.

The user separately enters the token through hidden terminal input after installation.

### Optional macOS GitHub bootstrap

`install-from-github.sh` requires a full 40-character commit SHA and the Canvas host. It clones
that exact commit into a private `/private/tmp` directory, verifies the checked-out SHA and clean
state, then creates a mode-`0700`, token-free `.command` launcher. It opens that launcher with
the explicit system application path `/System/Applications/Utilities/Terminal.app`, avoiding
dependence on an application-name lookup or `.command` file association. The test suite and
installation plan run there before `sudo` requests the user's administrator password. After a
successful installation, the guard itself requests the Canvas token with hidden input and stores
it in Keychain. The launcher deletes only itself; the reviewed checkout remains available for
inspection. No Canvas API request is made.

Codex's ordinary filesystem sandbox cannot launch macOS applications. Therefore, Codex must run
the exact immutable bootstrap command with scoped host/GUI execution permission. Without that
permission, Launch Services may return `kLSNoExecutableErr` even when Terminal and its executable
are present. This permission is only the platform approval for the bootstrap command; the
Terminal workflow does not add a second approval gate after displaying the installation plan.

After local installation succeeds, Terminal suggests the separate read-only Codex request
`In Canvas, what are my current classes?`. Keeping that authenticated smoke test outside the
installer preserves a clear review boundary: installation makes no Canvas request, while the
user's subsequent question explicitly authorizes the first audited Canvas read.

The raw bootstrap URL should use the same immutable commit supplied to `--ref`. A mutable branch
URL such as `main` is not the reviewed installation contract.

### Cross-platform reviewed-checkout alternative

The README also supplies a terminal copy/paste workflow for macOS and Linux. It clones a full
immutable commit, checks out detached HEAD, verifies the resulting SHA, runs the offline tests
and installation plan, then invokes the same root installer through the terminal's `sudo`.
After installation, the guard requests the token through hidden input in that same terminal.

This alternative does not open Terminal or use a generated launcher. On Linux it requires a
working user Secret Service session and the trusted `secret-tool` path enforced by the guard.
The checkout remains in the system temporary directory for review rather than being deleted
automatically.

## Level 1 versus optional Level 2

Level 1 intentionally permits every supported method and path allowed by the Canvas token.
Its security improvement over `.env` plus direct API use is credential isolation, destination
pinning, fixed audit, explicit write approval, and verified evidence.

Both `get` and `count` are read-only operations. `count` follows only pagination links that pass
the same pinned-host validation as `get`, and returns a total without requiring an agent-created
shell pipeline or repeated API tool calls. Codex rules allow these reads while continuing to
prompt for every write verb.

Level 2 is optional and specialized rather than a replacement for Level 1. Its installed
program contains no token logic and no HTTP client; it invokes only the installed Level 1 guard,
so every underlying Canvas request keeps Level 1's host pinning and audit. The first Level 2
release is read-only analysis: course/assignment patterns, student engagement and submission
signals, individual trajectories, and clearly labelled non-attendance activity summaries.

Future named Level 2 writes—rubrics, rubric grading, assignments, pages, and announcements—must
be separately reviewed with their own live-object validation and operation-specific read-back.
They are not present in the installed program or Codex allow rule until that code and its offline
tests exist.

## Residual risks

- This is not a mandatory network proxy. Users and sufficiently privileged approved processes
  can bypass it with another Canvas client.
- Level 1 does not reduce the Canvas token's privileges or restrict write endpoints.
- Codex rules are prefix decisions and cannot enumerate every possible OS-level bypass.
- A user-approved process outside the sandbox may be able to access that user's credential
  store.
- Read data is returned to the model. Correct use of the approved Clemson account is an
  external identity and policy control.
- A malicious root user can replace the executable/configuration or alter the audit.
- The local audit can grow without bound until deployment adds rotation and retention.
- Before/after comparison is generic and compares requested leaf fields to same-named fields
  in the returned Canvas object; unusual endpoints may need endpoint-specific verification in
  Level 2.

## Reviewer commands

Run from a clean checkout. The tests do not contact Canvas or a real credential store.

```sh
git status --short --branch
git rev-parse HEAD
shasum -a 256 canvas_api_guard.py codex/canvas-api-guard.rules \
  codex/skills/canvas-api-guard/SKILL.md       # macOS
python3 -m py_compile canvas_api_guard.py test_canvas_api_guard.py
python3 -m unittest -v
sh -n install.sh
sh -n install-from-github.sh
./install-from-github.sh --help
./install.sh --plan --host school.instructure.com
rg -n "urlopen\(" canvas_api_guard.py
rg -n "read_token\(\)" canvas_api_guard.py
codex execpolicy check --rules codex/canvas-api-guard.rules -- \
  /usr/local/libexec/canvas_api_guard.py get courses
codex execpolicy check --rules codex/canvas-api-guard.rules -- \
  /usr/local/libexec/canvas_api_guard.py put courses/1 -d '{}' --yes
```

Expected policy decisions are `allow` for the installed read and `prompt` for the installed
write. A source-tree command such as `./canvas_api_guard.py get courses` should have no rule.

## Pilot acceptance checks

1. Confirm the effective Clemson ChatGPT Edu account and relevant workspace controls.
2. Review the no-change installation plan and source hashes.
3. Install with the exact Clemson Canvas hostname.
4. Verify executable/config ownership and audit modes.
5. Enter a purpose-created instructor token through hidden input.
6. Run one harmless `GET users/self/profile` and verify the request/response audit pair.
7. Run a write dry-run and confirm that Codex prompts while Canvas remains unchanged.
8. On a test object, approve one write and verify target identity, before/after fields, and
   `verification: passed` in the audit.
9. Induce or mock a read-back failure and verify nonzero `WRITE STATUS UNCERTAIN` behavior.
10. Establish local audit retention and incident-review ownership before broader use.
