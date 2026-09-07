# canvas-api-guard

A small, audited Level 1 transport for using the Canvas REST API from Codex without
putting a Canvas token in `.env`, a repository, a command, or agent-visible output.

The review surface is deliberately small: one Python 3.9+ standard-library program,
one POSIX system installer, one macOS bootstrap, one Codex rules file, one Codex skill,
and a stdlib test suite.

## The two-level design

This release implements **Level 1: Safer Raw Canvas API**:

- generic Canvas `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` paths;
- unrestricted reads within the installed Canvas token's own permissions;
- token storage in macOS Keychain or Linux Secret Service;
- a fixed, administrator-owned HTTPS Canvas host configuration;
- one fixed, private audit log;
- dry-run, human approval, pre-read, write, and fail-closed read-back verification;
- no redirects and no automatic retries.

**Level 2: Restricted Writes** is a future policy layer, not a second transport. It will
leave reads open and apply a small, reviewable allowlist to write methods, paths, and fields
before Level 1 reads the credential or contacts Canvas. Level 2 is intentionally not
implemented in this release.

## What this improves

Compared with a token in `.env` and direct API use, Codex never receives the token, cannot
select another destination host or audit path, and must put every write through an approved,
logged, verified operation. The installed executable and host configuration are root-owned.

It adds no Canvas permission. Canvas remains the source of authorization: the guard can do
only what the installed token can do.

## What it does not do

- It is a selected local path, not a system-wide network chokepoint. A determined user or
  approved process with sufficient access can use Canvas by another route.
- It does not narrow token scope. Level 1 intentionally leaves reads and writes generic.
- Codex rules are part of the Codex execution boundary, not an operating-system mandatory
  access-control system.
- A process approved to run outside the Codex sandbox as the user may be able to access that
  user's credential store. The shipped rules forbid the known credential read commands and
  authorize only the installed absolute guard path.
- It does not make local audit records immutable against root.
- It supports macOS and Linux, not Windows.

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

After reviewing the source revision, SHA-256 hashes, destinations, ownership, and modes:

```sh
sudo ./install.sh --host school.instructure.com
```

An actual installation from a Git checkout refuses tracked modifications. `--allow-dirty`
exists for reviewed development builds and must be explicit. Existing differing executable,
config, rule, and skill files are backed up before replacement.

Installation creates:

| File | Ownership and purpose |
|---|---|
| `/usr/local/libexec/canvas_api_guard.py` | root-owned `0555` executable |
| `/usr/local/etc/canvas-api-guard/config.json` | root-owned `0644`; fixed host and Level 1 profile |
| `~/.canvas-api-guard/audit.jsonl` | invoking user, `0600`; fixed confidential audit log |
| `~/.codex/rules/canvas-api-guard.rules` | Codex execution decisions |
| `~/.codex/skills/canvas-api-guard/SKILL.md` | safe Canvas operating workflow |

Merge the reviewed lines in `codex/config.toml` into the user's existing Codex config. Do
not replace unrelated settings.

Then the user—not Codex—enters the token in a visible terminal with hidden input:

```sh
/usr/local/libexec/canvas_api_guard.py --set-token
```

The token is written to Keychain/Secret Service through stdin, read back for verification,
and never accepted through argv, a file, or an environment variable.

### One-command macOS installation from GitHub

For a new Mac, Codex can run the immutable bootstrap URL supplied with a reviewed commit. The
bootstrap downloads that exact commit and opens a private, self-deleting `.command` in macOS
Terminal. The user enters both the administrator password and Canvas token in Terminal; neither
secret passes through Codex or appears in the launcher.

```sh
curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/FULL_COMMIT_SHA/install-from-github.sh \
  | sh -s -- --ref FULL_COMMIT_SHA --host school.instructure.com
```

The Terminal workflow compiles and tests the downloaded source, prints the installation plan,
installs the root-owned files with `sudo`, stores the token, reports the installed version, and
waits for Return before closing. It makes no Canvas API request. If Terminal cannot be opened,
the bootstrap reports failure rather than claiming a prompt is visible.

## Usage

Paths may be `/api/v1/courses/123`, `api/v1/courses/123`, or `courses/123`. A path containing
a scheme, host, backslash, whitespace, or `..` is refused. The host and audit path have no
command-line overrides in the installed interface.

```sh
# Read: logged, no write approval
/usr/local/libexec/canvas_api_guard.py get courses/123
/usr/local/libexec/canvas_api_guard.py get "courses/123/students?per_page=100" -o json

# Preview: exact request, no token read and no network call
/usr/local/libexec/canvas_api_guard.py put \
  "courses/123/assignments/9/submissions/7?include[]=user" \
  -d '{"submission":{"posted_grade":95}}' --dry-run

# After the user approves that exact preview, Codex submits the same write
/usr/local/libexec/canvas_api_guard.py put \
  "courses/123/assignments/9/submissions/7?include[]=user" \
  -d '{"submission":{"posted_grade":95}}' --yes
```

Codex's rules prompt the person for every installed-path write, including dry-runs. `--yes`
records that the explicit Codex approval is being passed to the guard; it is not permission
for Codex to approve its own request.

## Fail-closed write evidence

For `PUT` and `PATCH`, success requires every requested field to match the read-back. For
`POST`, success requires locating the created object and matching every requested field on
the read-back. For `DELETE`, success requires a definite HTTP 404 on the read-back.

If Canvas accepted a write but verification fails, the command exits nonzero and prints:

```text
WRITE STATUS UNCERTAIN
```

This means do not retry. Inspect Canvas and the audit record first. A transport failure,
401, 403, 5xx response, timeout, or still-present object is never interpreted as deletion.

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

Every request is appended and fsynced before the network call. Response bodies and the token
are never logged. Existing audit directories and files are refused unless they are owned by
the current user and mode `0700`/`0600`; symlinked or non-regular logs are refused.

Events include:

- `request`: method, normalized path, URL, read/write kind, confirmation mode, and write body;
- `response`: status, success, byte count or error type;
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
```

The tests replace all Canvas network and credential-store calls. When Codex is available,
they also evaluate the shipped rules with `codex execpolicy check`.
