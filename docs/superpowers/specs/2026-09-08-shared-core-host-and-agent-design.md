# Shared core for the Codex host and the NanoClaw agent

Date: 2026-09-08. Status: proposal for the owner's review. Supersedes PR #4's staging plan and
the reverted PR #2 (f61027e).

## Goal

One reviewed guard core serves two callers: a faculty member working interactively in Codex on
a Mac (**host**), and a NanoClaw personal assistant that uses OpenAI as its model provider
(**agent**). The vast majority of the code is shared. Only three things differ: where the
credential lives, how a person approves a write, and how the software is installed.

Two properties are non-negotiable in both environments:

1. **The guard is the only credentialed path to Canvas.** Something the model cannot edit makes
   every other path fail.
2. **A person approves every write**, and the model cannot manufacture or replay that approval.

## What the two environments already provide

| | Host (Codex on a Mac) | Agent (NanoClaw, Apple Container) |
|---|---|---|
| Model's network | none inside the sandbox; escalation prompts a person | open egress from the container |
| Credential | user Keychain, unreachable from the sandbox; keychain tools forbidden by rule | OneCLI gateway injects per client identity; the token never enters a container |
| Per-command approval | Codex execution rules prompt on the guard's write verbs | none inside the container; a host-side Telegram approval exists for registered actions |
| What the model can edit | the workspace only, everything else prompts | anything under `/workspace`, including its own mailbox |
| Authoritative approval record | the person at the keyboard | `pending_approvals` in the host database, never mounted into a container |

Consequence: on the host the guard file inside the sandbox is the chokepoint because Codex
enforces it. In the agent's container nothing enforces anything, so the guard cannot live
there. It runs on the NanoClaw host, outside every container, and OneCLI grants the Canvas
credential to the guard's identity alone.

## Architecture

```
HOST (Mac)                                AGENT (NanoClaw host)
Codex sandbox                             container (model)            host processes
  └─ canvas_api_guard.py ──Keychain──┐      └─ MCP client (NanoClaw's)     guard MCP server (python3, launchd)
       TTY / --yes + execpolicy      │            │ streamable HTTP + bearer ├─ imports canvas_api_guard
                                     │            └──────────────────────►  ├─ OneCLI identity: canvas-guard
                                  Canvas ◄──────────── OneCLI gateway ◄──── ├─ confirm(): NanoClaw approval
                                                        (injects for the       │   over ncl.sock → Telegram card
                                                         guard identity only)  └─ audit log, evidence, Level 2 ops
```

The core is the same file in both places. The host runs it as today. The agent edge imports it
and replaces exactly the names listed under *The seam*.

## The seam in `canvas_api_guard.py` (this repository)

The edge replaces module-level names; the core never branches on where it runs. The suite has
patched these names by attribute for weeks, which proves the seam grips. Seven names:

| Name | Host meaning | Agent edge |
|---|---|---|
| `read_token()` | Keychain / Secret Service | returns `None`: the request leaves bearer-free and OneCLI injects |
| `build_opener()` | `ProxyHandler({})` + `RefuseRedirects` (no proxy, system CAs) | OneCLI proxy address and CA bundle from the service's root-owned config; the edge installs its opener with `urllib.request.install_opener` |
| `confirm(cfg, lines)` | TTY prompt or `--yes` | a NanoClaw approval request; blocks for the verdict |
| `check_provenance()` | installed path root-owned, ancestors clean | the service's own installed path and config |
| `CONFIG_PATH`, `DEFAULT_LOG`, `REVIEW_DIR` | `/usr/local/etc/...`, `~/.canvas-api-guard/audit.jsonl`, `~/.canvas-api-guard/submission-reviews` | the service's paths |

`build_opener()` is called once at import, so it is not patched by attribute like the other six
names: the edge installs its own opener with `urllib.request.install_opener` instead of replacing
the name. `DEFAULT_DIR` is not in this list - it is inert, read only once at import to derive
`DEFAULT_LOG` and `REVIEW_DIR`, so patching it after import has no effect.

Two small code changes make this real, and neither changes host behaviour:

- `send_request` attaches `Authorization` only when `read_token()` returns a value. Today it
  always returns one or raises, so the host path is unchanged.
- The API path builds its opener through a named `build_opener()` that uses `ProxyHandler({})`,
  the same choice the attachment path already makes. Today the API path uses urllib's default
  opener, which honours `https_proxy` from the caller's environment. Closing that is the one
  behaviour change, and it is the direction IT expects: the pinned host is reached directly or
  not at all.

`build_opener()` is the guard's own function and serves only the pinned API call. The
attachment path (`open_attachment_request`) constructs its own opener with
`urllib.request.build_opener(ProxyHandler({}), ...)` and calls it directly, so that a signed
file URL never traverses any proxy; it is not part of the seam, an edge must not patch
`urllib.request.build_opener`, and the agent server fetches attachments directly as the host
does. The seam is deliberately one transport for the API call and none for attachments.

Not in the file: no policy class, no `token_source` or approver keys in the config, no
receipt argument, no new fields on any audit line. The host's audit format, prompts, exit codes
and help are byte-identical before and after (see *Acceptance*).

A test class, `TestEdgeSeam`, pins the seven names and their signatures and proves each one is
looked up by module attribute at call time (replacing `guard.read_token` changes what
`send_request` sends). The file header gains a short "Edge seam" paragraph naming them.

## The agent edge (the agent's repository)

Three parts, all outside the model's container.

**The guard service is an MCP server.** A Python 3 process on the NanoClaw host, its own
launchd user agent like NanoClaw and OneCLI, speaking MCP over streamable HTTP on a
host-gateway address. This is the only MCP shape in use on that install (seven servers, all
`url`-configured, none spawned inside a container), so NanoClaw's client, per-group bearer
headers and URL discovery are inherited rather than written; the container needs nothing
added to its image. The server vendors `canvas_api_guard.py` at a pinned release commit and
refuses to start unless the file's SHA-256 matches the pin, then replaces the seven seam names.

Its tools are the allowlist made typed. Reads: `canvas_get(path, fields, all_pages)` for any
documented endpoint, plus `student_attention`, `prepare_submission_review` and
`download_assignment_submissions`. Writes: exactly the four named tools in the table below,
each with a JSON Schema that admits only the listed arguments. There is no generic write
tool for the agent, so an off-list write is unrepresentable rather than merely refused.
Reads run as they do on the host: audited, no approval. A write tool runs `confirm()`,
which sends a NanoClaw approval request naming the tool, its arguments and the dry-run plan,
waits for the verdict within the approval's TTL, and refuses on reject or expiry. The
verdict never leaves the host; the audit line records `confirmation: "telegram:<approval row
id>"`, a new value of an existing field. Approval cannot live anywhere else: NanoClaw has no
per-tool approval hook in the provider path, and a hook inside the container would be
editable by the model.

**What the agent may write.** The owner's requirement: reads, plus limited writes around
course administration. The service therefore carries an allowlist of write shapes, checked
before any approval is requested, so an approver never sees a card for a write that is not on
it. A write is allowed only if the verb, path and body match one entry exactly; the body may
carry no keys beyond those listed.

| Purpose | Shape | Verification |
|---|---|---|
| Excuse an absence | `put courses/C/assignments/A/submissions/U` body `{"submission": {"excuse": true}}` | the guard's read-back of `excused` |
| Regrade a quiz question | Level 2 `regrade-quiz-question` (to be built, shared with the host; see the quiz-regrade note) | per-attempt read-back |
| Change dates | `put courses/C/assignments/A` body with only `due_at`, `lock_at`, `unlock_at` | the guard's read-back |
| Make an announcement | `post courses/C/discussion_topics` body with `is_announcement: true`, `title`, `message`, optional `delayed_post_at` | `--created-id id` read-back |

Everything else, including grading and rubric writes, is refused by the service with a
message naming the allowlist; it can be extended later by editing one table in the service,
with the owner's review. Each allowed write costs exactly one Telegram approval, which shows
the dry-run plan; a Level 2 operation that makes several individually audited writes is
approved once, as its plan, not once per write.

**Identity and credential.** Decided 2026-09-09: each person uses their own Canvas account, so
the server holds one OneCLI identity per person, `canvas-guard-<person>`, each granted only that
person's Canvas secret; the group's bearer maps to the person, and the audit line names them.
OneCLI identifies a client by HTTP Basic credentials in the proxy URL (`http://x:<token>@host`),
so the worker for a call carries that person's proxy URL in its environment only, never argv;
the file holding those URLs is 0600, and the gateway CA reaches Python through `SSL_CERT_FILE`.
The earlier single identity, `canvas-guard`,
granted the Canvas secret with selective scope. No agent-group identity is granted Canvas. The
service's OneCLI token is host-side only, readable by the service user, never mounted or
exported into any container. A direct curl from the model through the gateway therefore gets
no injection. Each group that may use Canvas presents its per-group bearer on every MCP call; the server
maps it to the group's scope and approver and refuses unknown bearers before doing anything.

**Client, discovery and the skill.** No client is written: the server's URL and its
per-group bearer go into the group's MCP config in NanoClaw's database, which is materialized
into the container at spawn and read once at startup. A short skill says what the tools are
for; the tool schemas carry the argument contract. The container's Canvas skill drops the
"curl the real URL through the gateway" instruction for this host. Review downloads land in a
host directory the service owns, mounted read-only into the container as a DIRECTORY: Apple
Container silently drops a nested file mount, so a file mount here would vanish without error.

**Bind address.** A host-side edge serving containers must not listen on loopback only: on
Apple Container a container reaches the host over the vmnet bridge gateway, so a loopback-only
listener is invisible to every agent while looking healthy from the host. The server's bind
setting is a list, and it refuses to start unless every listed address binds, rather than
silently serving a subset. (Found when the read-only edge first went live.)

**Known limits of the runtime, recorded so nothing depends on them.** `container.json` is
not immutable inside the container on Apple Container; the pin holds because the host
re-materializes it from the database at every spawn and the runner reads it once. Per-group
bearers are static today; minting at spawn is new NanoClaw work and a later hardening. A
server that is down when a session starts leaves that group without Canvas tools until the
next spawn; that is fail-closed and is the operational cost of the MCP form.

**Embedding contract for Level 2.** The operations in `canvas_api_operations.py` are
command-line programs: they print their plan and their outcome as JSON documents on stdout
and return nothing (`regrade-quiz-question` prints two: the plan first, the outcome last). An
edge that runs them in-process must capture stdout and parse those documents; forwarding the
return value yields null and loses the rows, deltas and counts. Found by the agent edge's own
tests.

**More than one agent group.** The service never trusts the network. Each container presents a
per-group client token minted by NanoClaw at spawn and present only in that container; unknown
callers are refused first. Each group maps to its own OneCLI identity `canvas-guard:<group>`,
granted only that group's Canvas secret, so a group can act only as the account it was given.
Approver, audit log and download directory are per group. Today the map has one row. If
stronger isolation is ever wanted, one service process per group is the same code on another
port.

**NanoClaw change.** No approval endpoint exists for a separate process today: `requestApproval`
is an in-process host function and `ncl.sock` carries CLI commands. B2 is built in two slices:
the guard-side half against an approval-client interface with a fake (the server refuses every
write while the fake is in use unless a development variable is set, and refuses to start if
that variable is set in a launchd plist), then the real NanoClaw transport implementing the same
interface. The reference is minted and matched server-side; a restart mid-wait fails closed; a
verdict for an unknown or expired reference is discarded; the card shows the guard's own dry-run
plan.

## Acceptance

1. **Replay probe, byte-identical.** For a stock `{"host","profile"}` install: audit records,
   stdout, stderr, exit codes and `--help` are identical before and after the seam change,
   with `urlopen` and `read_token` mocked. This probe is run on every PR that touches the guard
   and its result is quoted in the PR.
2. **Existing tests pass unchanged.** Needing to edit a test is a signal something moved.
3. **Seam test.** `TestEdgeSeam` as above.
4. **Edge conformance.** In the agent repository, the service's tests drive the same guard
   assertions the host suite uses for pinning, redirects, refusal-before-credential and
   evidence read-back, against a fake OneCLI and a fake approval endpoint, so a behavioural
   difference between host and agent must be one of the seven names or the build fails.
5. **Cutover proof.** From a container: the `canvas_get` tool lists courses; a direct
   `curl https://<canvas>/api/v1/users/self` through the gateway returns 401; an
   `excuse_absence` tool call produces a Telegram card and nothing reaches Canvas until it is
   approved; a `put` to any other path is not a tool the model has.

## Staging and ownership

| Stage | Where | Who | Gate |
|---|---|---|---|
| A. Seam in the guard | this repository, one PR | the agent session proposes; this session reviews | acceptance 1–3, then the owner merges |
| 0. Revoke the Canvas grant from every agent-group identity in OneCLI | NanoClaw host | the agent session, now | a direct curl through the gateway returns 401 |
| B1. Read-only MCP server, launchd, group config, skill, `canvas-guard` identity | the agent's repository | the agent session; this session reviews the guard-facing parts | acceptance 4 for reads |
| B2. Writes: NanoClaw socket endpoint, allowlist, once-per-operation approval, download directories; `regrade-quiz-question` in this repository | agent repository and this one | the agent session proposes; this session reviews | acceptance 4 for writes |
| C. Cutover: `canvas-guard` identity granted, group grants removed, skill swapped | NanoClaw host | the agent session with the owner present | acceptance 5 |

Nothing merges without the owner's word. The agent works in its own clone. The faculty release
moves only when Stage A has been reviewed and the replay probe is byte-identical.

## Out of scope, deliberately

- Codex execution rules for the agent: NanoClaw has no command-line matcher, and one inside the
  container would be editable by the model. The service is the gate instead.
- Writes before the approval endpoint exists: until NanoClaw exposes `requestApproval` on its
  socket, the service refuses every write and says why. Reads work from Stage B1.
- A receipt argument on the guard. The model can forge anything it can read, so approval is
  requested by the service and never handled by the model.
- File-splitting the guard into core and edges. The seam is seven names; a split earns nothing.
