# canvas-api-guard

A small, audited **API Only** transport for using the Canvas REST API from Codex without
putting a Canvas token in `.env`, a repository, a command, or agent-visible output.

The review surface is deliberately small: one Python 3.9+ standard-library program
(`canvas_api_guard.py`, about 1,100 lines), one POSIX system installer, one macOS bootstrap,
one Codex rules file, two Codex skills, the optional Specialized Functions program in
`level2/`, and two stdlib test suites - 173 offline tests, all run by `python3 -m unittest`.

## The two-profile design

**API Only** provides safer raw Canvas API access:

- generic Canvas `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` paths;
- unrestricted reads within the installed Canvas token's own permissions;
- token storage in macOS Keychain or Linux Secret Service;
- a fixed, administrator-owned HTTPS Canvas host configuration;
- one fixed, private audit log;
- dry-run, human approval, pre-read, write, and fail-closed read-back verification;
- `--all-pages` and `--fields` on reads, so a complete list or a narrow projection needs no
  shell pipeline, and complete JSON output whenever stdout is not a terminal;
- refused redirects on every authenticated API request. A submitted file is fetched by a
  separate, token-free request, described under "Optional Specialized Functions" below.

**Specialized Functions** are an additive layer, not a second transport, an allow-list, or a
more privileged token. They leave API Only available for all general API work and add the six
operations that compute across several Canvas calls or validate structured input: participation
and activity analysis, submission-file review for one student or a whole assignment, and rubric
creation and grading. An operation that would be a single documented API call is
deliberately absent - API Only does those, with the Canvas documentation. These writes use the
same dry-run, explicit approval, and verified read-back as API Only.

## What this improves

Compared with a token in `.env` and direct API use, Codex never receives the token, cannot
select another destination host or audit path, and must put every write through an approved,
logged, verified operation. The installed executable and host configuration are root-owned, and
the guard checks its own path and the configuration's ownership before it reads the token,
refusing and naming the first untrusted component. See
[docs/IT-REVIEW.md](docs/IT-REVIEW.md) for exactly what that check does and does not cover.

It adds no Canvas permission. Canvas remains the source of authorization: the guard can do
only what the installed token can do.

## What it does not do

- It is a selected local path, not a system-wide network chokepoint. A determined user or
  approved process with sufficient access can use Canvas by another route.
- It does not narrow token scope. API Only intentionally leaves reads and writes generic.
- Codex rules are part of the Codex execution boundary, not an operating-system mandatory
  access-control system.
- A process approved to run outside the Codex sandbox as the user may be able to access that
  user's credential store. The shipped rules forbid the known credential read commands and
  authorize only the installed absolute guard path.
- It does not make local audit records immutable against root.
- It supports macOS and Linux, not Windows.
- The provenance check reads ownership and mode bits only, not ACLs, and proves the path of a
  copy launched as a program; it does not defend a process already running with forged globals,
  which is why the Codex rules' absolute-path match is the layer that actually stops that.

See [docs/IT-REVIEW.md](docs/IT-REVIEW.md) for the complete trust model, data flow, controls,
review commands, and residual risks.

## Codex-led installation

Codex can perform the installation, but the person reviews the plan and approves the
privileged step. The installer itself makes no network call, performs no Canvas request,
and neither reads nor stores a token.

First, inspect a no-change plan:

```sh
./install.sh --plan --host school.instructure.com
```

The plan marks each installed file `[same]`, `[differs]`, `[missing]`, `[link]`, or `[perms]`
by SHA-256 against the checkout, plus owner and mode for root-owned files. It exits with
status 3 when nothing needs to change, 5 when only the Codex settings need a person, and 4
when only the Codex rules, skills, or settings in your home differ; in that case rerun the
same command without `--plan` and without `sudo`, and only those files are replaced (a
`[link]` is refused, not replaced). After reviewing the source
revision, hashes, states, destinations, ownership, and modes:

```sh
sudo ./install.sh --host school.instructure.com
```

An actual installation from a Git checkout refuses tracked modifications. `--allow-dirty`
exists for reviewed development builds and must be explicit. Existing differing executable,
config, rule, and skill files are backed up before replacement.

The default API Only installation creates:

| File | Ownership and purpose |
|---|---|
| `/usr/local/libexec/canvas_api_guard.py` | root-owned `0555` executable |
| `/usr/local/etc/canvas-api-guard/config.json` | root-owned `0644`; fixed host and API Only profile |
| `~/.canvas-api-guard/audit.jsonl` | invoking user, `0600`; fixed confidential audit log |
| `~/.codex/rules/canvas-api-guard.rules` | Codex execution decisions |
| `~/.codex/skills/canvas-api-guard/SKILL.md` | safe Canvas operating workflow |

The installer also makes sure the three top-level Codex settings in `codex/config.toml`
(`sandbox_mode`, `approval_policy`, `approvals_reviewer`) are present in `~/.codex/config.toml`,
adding any that are missing ahead of the first `[table]` and backing the file up first. It
edits only a file of single-line values; one with multi-line strings or arrays is left
byte-identical and the plan lists the lines to add. A setting already present with another
value, or set again inside a `[table]`, is reported and left alone, and the plan exits with
status 5 so the bootstrap can say so, because `approvals_reviewer = "user"` is what keeps a
person, not a reviewer model, on every Canvas write prompt.

The optional Specialized Functions profile additionally installs the root-owned operations
executable and its separate Codex skill, as shown in its installation plan.

Then the user—not Codex—enters the token in a visible terminal with hidden input:

```sh
/usr/local/libexec/canvas_api_guard.py --set-token
```

On macOS, the token goes directly from the user's terminal to `/usr/bin/security`; the guard uses
a standard-library pseudoterminal only to rename Keychain's two generic-password labels to
`Canvas API token (hidden):` and `Retype Canvas API token (hidden):`. The guard does not capture
the token while it is being entered. On Linux, it writes the token to Secret Service through stdin.
The stored item is read back for verification and the token is never accepted through argv, a file,
or an environment variable.

### One-command macOS installation or upgrade from GitHub

One fixed command installs or updates; running it again is how you update:

```sh
curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/release/install-from-github.sh \
  | sh -s -- --host school.instructure.com --profile specialized-functions
```

The `release` branch is main plus one commit that writes the reviewed commit's hash into the
bootstrap's `RELEASE_REF` default, so the copy fetched from that branch downloads exactly that
commit and nothing else; the bootstrap never resolves a branch name or "latest". The fetch
of the bootstrap itself is a branch fetch, so the trust root of the fixed command is whoever
can push to `release`, the same people who can push to `main`; protect both branches alike.
The owner advances it with `tools/release.sh`, which refuses a commit that is not on
`origin/main`.
The same command serves a new Mac, an older installation, and an up-to-date one. The
bootstrap downloads that exact commit and opens a private, self-deleting `.command` in macOS
Terminal. The user enters the administrator password and, when none is stored, the Canvas
token in Terminal; neither secret passes through Codex or appears in the launcher.

The bootstrap addresses Terminal by its fixed macOS system path,
`/System/Applications/Utilities/Terminal.app`; it does not depend on application-name lookup or
the machine's `.command` file association.

Opening a macOS application is outside Codex's normal filesystem sandbox. When Codex starts this
bootstrap, it must run the exact pinned command with host/GUI execution permission. This is the
normal scoped command approval needed to open Terminal, not a second installation-phase approval.
Running the command without that permission can make Launch Services report the misleading
`kLSNoExecutableErr` even though Terminal is installed.

To install a specific reviewed commit instead of the release, fetch the bootstrap from that
commit and name it with `--ref`; an explicit `--ref` always wins over the pin:

```sh
curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/FULL_COMMIT_SHA/install-from-github.sh \
  | sh -s -- --ref FULL_COMMIT_SHA --host school.instructure.com
```

The Terminal workflow compiles and tests the downloaded source and prints the installation
plan, which marks every installed file `[same]`, `[differs]`, `[missing]`, `[link]`, or
`[perms]` by comparing its SHA-256 with the downloaded commit, plus owner and mode for the
root-owned files. When every file is `[same]` the plan exits
with status 3 and the workflow skips the privileged step, so no administrator password is asked
for. When only the Codex rules, skills, or settings differ, the plan exits with status 4 and the workflow
replaces those files as you, again without a password and without a second pause, since the
plan is already on screen. Otherwise it pauses for Return and installs with `sudo`, which
rewrites the root-owned files and backs up any file that differed. It then stores a token
only if the Keychain holds none, found by an attribute lookup that never reads the secret; an
existing token is kept unchanged. Finally it
reports the installed version and waits for Return before closing. It makes no Canvas API
request. If Terminal cannot be opened, the bootstrap reports failure rather than claiming a
prompt is visible and tells a Codex user that host/GUI execution permission is required.

The final Terminal message directs the user back to Codex with: `In Canvas, what are my current
classes?` That separate, read-only request is the live smoke test: it proves the stored token,
pinned host, audit path, execution rule, and skill work together without making installation
itself contact Canvas.

### Upgrading

Run the same fixed command. Specify `specialized-functions` when adding operations;
`api-only` upgrades only the core guard. Legacy `level-1` and `level-2` flags remain accepted
for existing installations. To replace a stored token, run the guard's `--set-token`
afterward in a visible terminal.

### Releasing (owner)

```sh
tools/release.sh            # release origin/main
tools/release.sh COMMIT     # release a commit that is on origin/main
```

It checks the tracked tree is clean, resets `release` to that commit plus one commit that pins
`RELEASE_REF` in `install-from-github.sh`, and force-pushes `release` with a lease. Nothing on
`main` changes, and `main`'s copy of the bootstrap keeps an empty pin.

### Copy/paste installation from a reviewed checkout (macOS and Linux)

This alternative runs entirely in the terminal where it is pasted. Both the administrator
password and token use that terminal's hidden input. Replace the commit only after reviewing a
newer revision; never substitute `main` or another mutable branch name.

```sh
(
  set -eu
  guard_commit="FULL_COMMIT_SHA"
  guard_checkout="$(mktemp -d)/canvas-api-guard"
  git clone --quiet https://github.com/chiptoe-svg/canvas-api-guard.git "$guard_checkout"
  git -C "$guard_checkout" checkout --quiet --detach "$guard_commit"
  test "$(git -C "$guard_checkout" rev-parse HEAD)" = "$guard_commit"
  cd "$guard_checkout"
  python3 -m unittest
  ./install.sh --plan --host school.instructure.com
  sudo ./install.sh --host school.instructure.com
  echo
  echo "Installation complete. Now enter your Canvas API token:"
  /usr/local/libexec/canvas_api_guard.py --set-token
)
```

The method supports macOS and Linux. Linux requires `sudo` plus an available desktop Secret
Service and a trusted, root-owned `secret-tool` at `/usr/bin/secret-tool` or
`/usr/local/bin/secret-tool`. A headless Linux host without an unlocked user keyring will refuse
token storage. The temporary reviewed checkout is intentionally retained for inspection.

## Usage

Paths may be `/api/v1/courses/123`, `api/v1/courses/123`, or `courses/123`. A path containing
a scheme, host, backslash, whitespace, or `..` is refused. The host and audit path have no
command-line overrides in the installed interface.

```sh
# Read: logged, no write approval
/usr/local/libexec/canvas_api_guard.py get \
  "courses?enrollment_type=teacher&enrollment_state=active&state[]=available&include[]=term&per_page=100" -o json
/usr/local/libexec/canvas_api_guard.py get "courses/123/students?per_page=100" -o json

# Every page of a collection, projected to the fields wanted: no jq, no repeated tool calls
/usr/local/libexec/canvas_api_guard.py get \
  "courses/123/enrollments?type[]=StudentEnrollment&state[]=active&per_page=100" \
  --all-pages --fields id,user_id

# Preview: exact request, no token read and no network call
/usr/local/libexec/canvas_api_guard.py put \
  "courses/123/assignments/9/submissions/7?include[]=user" \
  -d '{"submission":{"posted_grade":95}}' --dry-run

# After the user approves that exact preview, Codex submits the same write
/usr/local/libexec/canvas_api_guard.py put \
  "courses/123/assignments/9/submissions/7?include[]=user" \
  -d '{"submission":{"posted_grade":95}}' --yes
```

A dry run prints the exact request it did not send: as labelled lines for a person, and as
one JSON object with `dry_run`, `method`, `url`, `headers` (the Authorization header redacted)
and `body` whenever output is JSON. No token is read and nothing is sent either way.

Codex's rules prompt the person for every installed-path write, including dry-runs. `--yes`
records that the explicit Codex approval is being passed to the guard; it is not permission
for Codex to approve its own request.

### Optional Specialized Functions

Specialized Functions are a separate, additive installation profile. They use the same API Only credential,
host, and audit boundary; it neither stores nor retrieves a token itself. Install it only from a
reviewed immutable checkout:

```sh
./install.sh --plan --profile specialized-functions --host school.instructure.com
sudo ./install.sh --profile specialized-functions --host school.instructure.com
```

The read operation is `student-attention`, which reports Canvas activity, not verified
attendance. The write operations are rubric creation and rubric grading for one student or for
a batch. They accept a reviewed, allowlisted JSON definition and require
`--dry-run` followed by explicit approval for `--yes`. See
[level2/README.md](level2/README.md) for the exact boundary.

Submission-file review is read-only, and it is the one data flow that leaves the pinned API
host. The guard authenticates only the Canvas metadata request that resolves the file. The file
itself, and every HTTPS redirect Canvas issues, is fetched with no Authorization, no Cookie,
no forwarded Host, and no system proxy - any HTTPS host the redirect names is followed, and
only each hop's status and hostname are logged, never the signed URL, its query, or a response
body. A download copies a student's work onto the disk, so the Codex rules prompt for it.
Specialized Functions can prepare one student's complete attachment set
(`prepare-submission-review`, capped at 20 files) or download an assignment's complete
attachment set (`download-assignment-submissions`, including earlier submission attempts,
capped at 500 files total). The files stay in a user-private local review directory and no
grade is inferred or written.

Date changes, excusals, assignment/page/announcement authoring and the former analytics
shortcuts are ordinary API Only calls against the documented Canvas endpoints, with the same
dry-run, approval and read-back.

## Fail-closed write evidence

Every `POST`, `PUT` and `PATCH` is verified by one rule. Each requested leaf field is compared
by name with the field of the read-back object that proves it: a field the object exposes must
match, and any mismatch is `WRITE STATUS UNCERTAIN`. A requested field the object does not
expose at all is reported with `match: null` and cannot fail, because it proves nothing either
way; a write whose read-back proved nothing at all is uncertain too.

A `POST` must locate the created object first, in this order: the response field named by
`--created-id`, which defaults to the response's own top-level `id`; then, only when
`--created-id` was not given and Canvas returned no `id`, a same-host `Location` header. An
explicit `--created-id` that does not resolve is uncertain and never falls back to `Location` -
the object may exist and could not be read back. For `DELETE`, success requires a definite HTTP
404 on the read-back.

Exit codes: `0` the command completed, and any write verified; `2` refused or failed with
nothing applied (bad input, an unconfirmed write, a validation failure, or a 4xx on the write
itself, which is Canvas saying it did not apply the change); `3` a write may have been applied
and its outcome could not be verified - a failed read-back, or a timeout, transport failure or
5xx on the write itself. In that case the command exits `3` and prints:

```text
WRITE STATUS UNCERTAIN
```

This means do not retry. Inspect Canvas and the audit record first. A transport failure,
4xx or 5xx response, timeout, or still-present object is never interpreted as deletion.

When Canvas supplies a submission `user` object, the evidence and audit record include the
student name and Canvas user ID. Include `include[]=user` on submission grade paths when
human-readable student identity is required.

## Confidential data

The intended Clemson deployment assumes student names, grades, submissions, and other
confidential education records are processed only with the institution-approved Clemson
ChatGPT Edu account. That approval is an external deployment control and is not established
by this repository.

The local audit file intentionally persists student identity and before/after write evidence.
It is therefore confidential institutional data even when model processing is approved. Keep
it private, covered by endpoint controls and retention policy, and do not make extra copies.

## Audit record

Every write is appended and fsynced before the network call and again after it; every read is
recorded as one line after the fact. Response bodies and the token are never logged. Existing
audit directories and files are refused unless they are owned by the current user and mode
`0700`/`0600`; symlinked or non-regular logs are refused.

Events include:

- `read`: one line per read, written after the response: verb, normalized path, status, and
  byte count or error type;
- `request`: a write, recorded before it is sent: method, normalized path, URL, confirmation
  mode, and the request body;
- `response`: that write's status, success, and byte count or error type;
- `download`/`download-response`: one submission-file fetch attempt, recorded before and after -
  route, attempt number, and on failure whether it `will_retry` and the `next_route`; the
  metadata call that resolves each URL logs its own `read` line first;
- `evidence`: target identity, before/after changes, and verification result;
- `refusal`: a write that lacked confirmation.

A request without a response means the request was attempted but did not complete. An
`evidence` event with `verification: failed` means the write outcome requires inspection.

## Test and review

```sh
python3 -m unittest -v
sh -n install.sh
./install.sh --plan --host school.instructure.com
python3 canvas_api_guard.py --version
rg -n "urlopen\(|build_opener|\.open\(" canvas_api_guard.py
rg -n "read_token\(\)" canvas_api_guard.py
```

The tests replace all Canvas network and credential-store calls. When Codex is available,
they also evaluate the shipped rules with `codex execpolicy check`.
