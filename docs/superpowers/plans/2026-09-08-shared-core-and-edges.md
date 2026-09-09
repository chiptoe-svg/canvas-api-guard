# Shared core, two edges — a plan for the host and agent installations to coexist

Goal: one implementation of the reviewed core, two thin edges (a Mac host, an agent container),
and NO forked copy of the tool. A fork-by-copy is the failure mode to design against: fifteen
copies of a department skill in this operator's own install drifted apart inside a week, and the
whole value of this tool is that a reviewer read ONE file.

## What this week established

Driving both behaviours from config first (PRs #2, #3) was not the destination; it was the
experiment that identified the seam. The result: the variant surface is **exactly three things**,
and a keychain installation's audit record is byte-for-byte unchanged (test-pinned).

| Seam | Host edge | Agent edge |
|---|---|---|
| Credential | macOS keychain / Linux secret service | none held; a proxy injects at the TLS boundary |
| Confirmation | a human at a TTY, or `--yes` | a receipt from a named external approver; self-approval refused |
| Trust & install | root-owned `/usr/local`, admin password, macOS installer, provenance of a login shell | baked at image build, non-root runtime user, no admin account, provenance of a supervised runner |

Everything else is shared and must never diverge: host and path pinning, `normalise_path`,
redirect stripping, the audit log and its fsync-before-the-request, evidence read-back and
verification, refusal-before-credential, output shaping, and the level-2 operations.

## Stages

**Stage 0 — done.** Both behaviours reachable, seam list proven, Mac record unchanged, 203 tests.

**Stage 1 — name the seams in place.** No file split, no behaviour change. Introduce a `Policy`
with `read_credential()`, `confirm(cfg, lines)` and `trust_rules()`, and two instances selected by
config. The existing suite is the safety net; a reviewer then sees the entire variant surface on
one screen. Decide here whether `allow_yes_flag` stays a key or becomes a property of the proxy
policy (which refuses self-approval by construction).

**Stage 2 — split, only if Stage 1's seam is clean.**

- `canvas_api_core.py` — policy-free, the part IT reviews
- `canvas_api_policy_host.py` — keychain, TTY, `/usr/local` trust
- `canvas_api_policy_proxy.py` — no credential, external approver, image trust
- `canvas_api_guard.py` — one entry point: read config, select policy, call core

Multi-file installation is already solved here: `install.sh` installs and SHA-256-verifies two
root-owned files for level-2, so the plan and the hash comparison extend naturally.

**Stage 3 — how NanoClaw consumes it.** Not a fork. Vendor core + proxy policy at a pinned
immutable commit and verify SHA-256 at image build, mirroring the installer's own model, carrying
zero local modifications. If the proxy policy cannot be upstreamed it is ONE small file downstream
and the core is still consumed untouched.

## The anti-drift mechanism

A conformance suite that runs the SAME assertions against BOTH policies: pinning holds, a refusal
happens before the credential is touched, the audit line is written and fsynced before the request,
redirects drop authorization, evidence is read back. Any behaviour that differs between edges must
be a declared seam or conformance fails.

This is worth stating as the load-bearing part of the plan. The operator's other codebase adopted
exactly this shape for provider contracts, and it is what caught a silent regression there — a
capability that quietly stopped reaching one provider while every existing test stayed green.

## Risks, and what they cost

- **Splitting weakens "read one file".** Mitigation: the core stays one file, the policies are
  small enough to read in full, and the installer hashes each. If Stage 1 shows the seam is not
  clean, STOP at Stage 1 — config-driven with a named policy is already a good resting place.
- **Two edges drift in their seams.** Mitigation: one entry point, not two, plus the conformance
  suite.
- **The release pin serves both.** One reviewed commit is what the Mac bootstrap pins and what the
  image build pins. That single pinned commit IS the coexistence property; anything that makes the
  two edges want different commits should be treated as a design failure.
