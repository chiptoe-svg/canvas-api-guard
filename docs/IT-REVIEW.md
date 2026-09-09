# IT review: canvas-api-guard API Only and optional Specialized Functions

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
| `test_canvas_api_guard.py` | offline API Only security and behavior tests, plus the rules and skill coverage tests |
| `test_canvas_api_operations.py` | offline Specialized Functions behavior tests |
| `level2/` | optional Specialized Functions, installed with `--profile specialized-functions` |

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

Submitted-file review (the one flow that leaves the pinned API host)
  -> pinned https://<installed Canvas host>/api/v1/files/<id> (authenticated) for the file URL;
     on a 500/502/503/504, retried once, then falls back once to the pinned, authenticated
     https://<installed Canvas host>/api/v1/files/<id>/public_url?submission_id=<id>
  -> that URL, then any HTTPS redirect Canvas issues, with no Authorization, no Cookie,
     no forwarded Host, and no system proxy
  -> ~/.canvas-api-guard/submission-reviews/ (0700 directory, 0600 files)

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
- Before any token read, the guard requires its own real path, the fixed configuration file,
  and every ancestor directory to be owned by root and not writable by group or others, naming
  the first component that fails. This runs only after the configuration is found and read, so
  on a machine with no installed configuration a source-tree copy is refused earlier, with "no
  Canvas configuration"; on a machine that does have the configuration installed, that same copy
  is refused here instead, because its own path is not root-owned. The check stands down only
  when the configuration path has been redirected by the offline test seam, which the installed
  guard never does. It reads ownership and mode bits only - a POSIX ACL granting extra write
  access is invisible to it - and it proves the path of a copy launched as a program, not an
  already-running process with forged globals; the Codex rules' absolute-path match is the layer
  that stops those.

### Keep the token on one destination

- `/usr/local/etc/canvas-api-guard/config.json` is the only host configuration.
- At the installed path, the file and every ancestor directory must be owned by root and not
  writable by group or others; the installer creates it as root-owned `0644`. "Owned by root or
  the current user" is the offline test seam's rule for a redirected config, never the installed
  guard's.
- There is no production `--host` option.
- The URL builder forces HTTPS and rejects paths containing a scheme, host, traversal,
  whitespace, or backslash.
- Every redirect on an authenticated API request is refused, including a same-host redirect.
- A submitted-file download does follow Canvas's HTTPS redirects, and no hop carries the token,
  a cookie, a forwarded Host header, or proxy credentials - the first hop already carries none.
  On a 500/502/503/504, the file-URL fetch is retried once, then Canvas's submission-authorized
  `public_url` endpoint is tried once; nothing else retries. Each attempt's `download`/
  `download-response` audit pair records its route and, on failure, whether it will retry and
  the next route, plus each hop's status and hostname - never the signed URL.
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

- `POST`/`PUT`/`PATCH`: one rule. Every requested leaf field the read-back object exposes must
  match it. A requested field the object does not expose is reported with `match: null` and
  cannot fail, because it proves nothing either way; a write whose read-back proved none of the
  requested fields is uncertain.
- `POST` must locate the created object first, in this order: the response field named by
  `--created-id`, which defaults to the response's own top-level `id`; then, only when
  `--created-id` was not given and no `id` came back, a usable same-host `Location` header. An
  explicit `--created-id` that does not resolve is `WRITE STATUS UNCERTAIN` and never falls
  back to `Location`.
- `DELETE`: the read-back must return HTTP 404.
- Any mismatch, unprovable write, read-back failure, missing created-object location, or
  still-present delete target is `WRITE STATUS UNCERTAIN` and is never retried automatically. So is a write whose
  own request timed out, failed in transport, or returned 5xx: Canvas may have applied it.
  A 4xx on the write itself is Canvas answering that it did not apply the change, so that is
  an ordinary failure. Submission-file downloads retry separately, on their own schedule.
- Exit codes: `0` completed, and any write verified; `2` refused or failed with nothing
  applied; `3` a write may have been applied and could not be verified (`WRITE STATUS
  UNCERTAIN`).

### Produce useful, protected audit evidence

- The fixed log path has no command-line override.
- The directory must be owned by the current user and mode `0700`.
- The file is opened with append and no-follow semantics where supported and must be a
  regular user-owned `0600` file.
- A write's request event is flushed and fsynced before network I/O.
- Response bodies and credentials are excluded.
- A read is one line, written after the response: verb, path, status, and byte count. A write
  is three: the request before it is sent, the response after it, and the evidence - plus the
  pre-read and read-back each add their own `read` line, so a `put` command produces five audit
  lines in total.
- Write evidence includes the Canvas user ID and student name when Canvas returns the user
  object, plus requested/before/after fields and the verification result.

The audit log is not protected from root and has no retention, forwarding, or rotation policy.
Those remain deployment controls.

## Installation controls

`install.sh --plan --host <host>` runs without root and changes nothing. It reports:

- source Git revision and whether tracked files differ;
- SHA-256 of the exact guard, Codex rule, and skill sources;
- Canvas host;
- every destination, owner, and mode, each marked `[same]`, `[differs]`, `[missing]`,
  `[link]`, or `[perms]`: `[same]` means the installed file's SHA-256 matches the reviewed
  source (the generated config included) and, for root-owned files, that it is root-owned and
  not group/other-writable; `[perms]` is matching content with wrong owner or mode;
- an explicit statement that it performs no Canvas or credential operation.

It exits 0 when a root-owned file would change, 4 when only the user-owned Codex rules,
skills, or settings would change, 3 when every file is already `[same]`, and 5 when the files
are current but the Codex settings need a person (see below). The macOS bootstrap uses those
statuses to skip the privileged step: on 4 it reruns the installer as the user, which replaces
only the user-owned files and refuses if a root-owned file differs. After any install it runs
the plan again and fails unless it reports 3 or 5; a 5 is carried into the completion-status
file as `"codex_settings":"attention"`.

Actual installation:

- requires root for any root-owned file; without root it replaces only the user-owned Codex
  rules and skills, and only when every root-owned file is already installed correctly;
- refuses a tracked, modified Git checkout unless `--allow-dirty` is explicit;
- installs the executable and host configuration as root-owned;
- backs up differing executable, config, Codex rule, and skill files;
- adds any of the three top-level Codex settings in `codex/config.toml` that
  `~/.codex/config.toml` lacks, ahead of the first `[table]`, after backing the file up. Only
  a file of single-line values is edited: one with a triple-quoted string or a multi-line
  array is reported and left byte-identical, with the lines to add. A setting present with
  another value, or set again inside a `[table]` (a profile's value overrides the top level),
  is reported in the plan and the report and never changed;
- refuses symbolic-link destinations and preserves existing Codex directory modes;
- verifies the installed guard, rule, and skill hashes against the reviewed sources;
- creates but never populates the credential store;
- makes no network call.

The user separately enters the token through hidden terminal input after installation.

### Edge seam

The API opener now disables environment proxies (`ProxyHandler({})`), as attachment downloads
already did: the pinned host is reached directly or not at all. The importable edge seam is six
named module attributes; the host path never branches on them, and the replay probe pins the
stock audit format.

### Optional macOS GitHub bootstrap

`install-from-github.sh` requires a full 40-character commit SHA and the Canvas host. It clones
that exact commit into a private `/private/tmp` directory, verifies the checked-out SHA and clean
state, then creates a mode-`0700`, token-free `.command` launcher. It opens that launcher with
the explicit system application path `/System/Applications/Utilities/Terminal.app`, avoiding
dependence on an application-name lookup or `.command` file association. The test suite and
installation plan run there, and the workflow waits for Return between the printed plan and
`sudo`, so a person can stop before the privileged step rather than watch it scroll past.
`sudo` then requests the user's administrator password. After a successful installation, the
guard itself requests the Canvas token with hidden input and stores it in Keychain. The
launcher deletes only itself; the reviewed checkout remains available for inspection. No
Canvas API request is made.

The bootstrap is fetched from the `release` branch, whose only difference from `main` is one
commit that writes the reviewed commit's hash into the bootstrap's `RELEASE_REF` default; the
bootstrap refuses to run without a full commit hash from that default or `--ref`, verifies
the checkout matches it, and never resolves a branch name. The fetch of the bootstrap is a
branch fetch, so the trust root of the fixed command is whoever can push to `release`: the
same people who can push to `main`, and the branch should carry the same protection.
`tools/release.sh` advances the branch and refuses a commit that is not on `origin/main`;
that check is a convention of the tool, not a server-side control.

Codex's ordinary filesystem sandbox cannot launch macOS applications. Therefore, Codex must run
the exact bootstrap command with scoped host/GUI execution permission. Without that
permission, Launch Services may return `kLSNoExecutableErr` even when Terminal and its executable
are present.

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

## API Only versus optional Specialized Functions

API Only intentionally permits every supported method and path allowed by the Canvas token.
Its security improvement over `.env` plus direct API use is credential isolation, destination
pinning, fixed audit, explicit write approval, and verified evidence.

`get` is the only read verb. `--all-pages` follows only pagination links that pass the same
pinned-host validation, refuses a page it has already read, and stops at 200 pages; `--fields`
projects each returned object to named dot-paths, so a total or a narrow list needs no
agent-created shell pipeline or repeated tool calls. Codex rules allow those reads, and prompt
for every write verb and for `download-submission-file`, which copies student work to disk.

Specialized Functions are optional rather than a replacement for API Only. Their installed
program contains no token logic and no HTTP client; it invokes only the installed API Only guard,
so every underlying Canvas request keeps API Only's host pinning and audit. The one read
operation is `student-attention`, an activity signal, not verified attendance.

It also provides named rubric, rubric-grading, and submission-review workflows. Each accepts
only an allowlisted JSON definition, resolves the live Canvas target before acting, requires a
reviewed `--dry-run` before `--yes`, and delegates the write and its read-back to API Only.
Rubric creates name the created rubric's ID in the create response (`--created-id rubric.id`)
so the read-back is the rubric itself; grading rejects stale or
invented rubric criterion IDs; batches are capped at 50 students and are individually audited
and read back rather than sent through an opaque asynchronous bulk endpoint. Codex rules prompt
for each Specialized Functions write and for each of the two operations that download student
work. An API Only exit status of 3 - a write that was sent and could not be verified -
propagates out of these operations unchanged and is never retried.

## Residual risks

- This is not a mandatory network proxy. Users and sufficiently privileged approved processes
  can bypass it with another Canvas client.
- API Only does not reduce the Canvas token's privileges or restrict write endpoints.
- Codex rules are prefix decisions and cannot enumerate every possible OS-level bypass.
- A user-approved process outside the sandbox may be able to access that user's credential
  store.
- Read data is returned to the model. Correct use of the approved Clemson account is an
  external identity and policy control.
- A malicious root user can replace the executable/configuration or alter the audit.
- The local audit can grow without bound until deployment adds rotation and retention.
- Submission review writes copies of student work to `~/.canvas-api-guard/submission-reviews/`
  (user-owned, mode 0700). Those files are education records, they are not deleted
  automatically, and no retention policy is enforced here; deployment owns their lifetime.
- Before/after comparison is generic and compares requested leaf fields to same-named fields
  in the returned Canvas object; unusual endpoints may need endpoint-specific verification in
  Specialized Functions.

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
rg -n "urlopen\(|build_opener|\.open\(" canvas_api_guard.py
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
6. Run one harmless `GET users/self/profile` and verify the resulting `read` audit line.
7. Run a write dry-run and confirm that Codex prompts while Canvas remains unchanged.
8. On a test object, approve one write and verify target identity, before/after fields, and
   `verification: passed` in the audit.
9. Induce or mock a read-back failure and verify exit `3` (`WRITE STATUS UNCERTAIN`) behavior.
10. Verify on a test course whether `courses/<id>/rubric_associations/<id>` reads back. Canvas
    documents no `GET` for a single rubric association, so the guard may report `WRITE STATUS
    UNCERTAIN` (exit `3`) for that one create even though it succeeded; if it does not read
    back, the note in `level2/SKILL.md` stands and the attachment is confirmed instead from
    the assignment's `rubric_settings`.
11. Establish local audit retention and incident-review ownership before broader use.
