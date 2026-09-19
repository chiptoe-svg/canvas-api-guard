# A native macOS installer package (.pkg) as an optional install path

Date: 2026-09-18
Branch: `spec/macos-installer-package`
Status: design proposal, not implemented, not planned. Written for a later implementation plan to
argue from or against.

## Where this came from

The faculty install path today is `curl | sh` against `install-from-github.sh`, which clones one
pinned commit, opens a visible Terminal window, compiles and tests the source, prints
`install.sh --plan`, waits for Return, runs `sudo install.sh`, and finally has the guard itself
prompt for the Canvas token with hidden input. That is reviewable end to end and needs nothing
beyond git and Python. It also has no story for an IT-managed fleet: Jamf, Intune, and similar
tools push `.pkg` files, not shell one-liners, and a campus rollout of more than a handful of Macs
is not going to be done by asking each faculty member to paste a curl command.

This document asks what a native `.pkg`, built by a script in this repository from native Apple
tools, would add as an **optional alternative** next to the existing bootstrap — not a
replacement. It does not propose removing `install-from-github.sh` or `install.sh`; both keep
working exactly as they do today. It does not implement anything, and it is not itself an
implementation plan.

## What a `.pkg` can and cannot do here

### The root-owned payload: a natural fit

`install.sh` already installs two things as root:

- `/usr/local/libexec/canvas_api_guard.py` (and, for the Specialized Functions profile,
  `canvas_api_operations.py`), mode `0555`
- `/usr/local/etc/canvas-api-guard/config.json`, mode `0644`, containing the fixed Canvas host
  and profile

Both are static files with no dynamic content beyond `config.json`, whose only variables (`host`,
`profile`) are pkg install-time choices, not runtime state. This is exactly the shape
`pkgbuild(1)` is built for: package a destination root, install it under a fixed prefix, done.
Confirmed from the local `pkgbuild(1)` man page: `--root root-path` packages "the entire contents
of the directory tree," and `--ownership recommended` (the default) applies root:wheel to every
payload file regardless of the ownership those files happen to have on the build machine — so the
build script does not need to run as root, and does not need a separate `chown` step, to produce a
root-owned payload. `pkgbuild` also supports `--scripts` for `preinstall`/`postinstall`, and
`--identifier`/`--version` to give the Installer a package identity Installer can compare across
runs.

`config.json`'s host and profile are the two things `install-from-github.sh` takes as
command-line arguments today (`--host`, `--profile`); a pkg has no command line, so those need to
become either build-time bake-in (one pkg per host/profile combination, e.g.
`canvas-api-guard-clemson-specialized-functions.pkg`) or an install-time `choices.xml` selection
in a `productbuild` distribution. Baking them in at build time is simpler, matches "compact and
reviewable," and matches what campus IT actually wants: one signed artifact per institution, not
a chooser UI. This repository's institution default (`clemson.instructure.com`,
`specialized-functions`) is already a build-time constant in `install-from-github.sh`; a pkg build
script can read the same defaults.

### The per-user parts: must run in postinstall, as the console user, not root

`install.sh` also writes files nobody but the user should own:

- `~/.codex/rules/canvas-api-guard.rules`
- `~/.codex/skills/canvas-api-guard/SKILL.md` (and the Specialized Functions skill)
- three settings merged into `~/.codex/config.toml`
- `~/.canvas-api-guard/` (created empty; the audit log and `installed-commit` land there over
  time)

A `.pkg`'s payload and its `preinstall`/`postinstall` scripts all run as root, and `$HOME` in that
script's environment is root's home, not the person's. This is a long-standing, widely used
pattern among Mac administrators rather than something with its own dedicated Apple documentation
page: a `postinstall` script determines the console (logged-in GUI) user — typically by reading
`/dev/console`'s owner (`stat -f%Su /dev/console`) or asking `scutil` for the console-user
state — resolves that user's home directory, and writes the per-user files there with the right
ownership, the same way `install.sh` itself resolves `SUDO_USER`'s home when run under `sudo`. I
could not find an Apple page documenting this technique directly, so it is labeled **unverified as
an Apple-sanctioned pattern**, though `pkgbuild(1)`'s own man page (`man pkgbuild`, read locally)
confirms that `preinstall`/`postinstall` are ordinary scripts run by the Installer with no special
per-user awareness, which is why this workaround exists at all.

Known pitfalls, all of which `install.sh` avoids today by simply running as the invoking user (or
`SUDO_USER`) with a real terminal attached:

- **No logged-in console user.** Under MDM, a pkg is frequently pushed while nobody is logged in,
  or before First Boot / at a login window. `/dev/console` may report `root` or `loginwindow` in
  that case, and there is no home directory to write the Codex files into. The postinstall script
  must detect this and either skip the per-user step (leaving Codex unconfigured until first
  login) or use a LaunchAgent that runs once at the next login — more moving parts than
  `install.sh` has today.
- **Multiple logged-in users / fast user switching.** `/dev/console` names one console user; a
  faculty Mac with more than one local account only gets that one account's `~/.codex/` files
  from a single pkg install. `install.sh` has the same limitation (it targets one user per run),
  so this is not a regression, just a fact the pkg inherits.
- **A user directory that does not yet exist**, or is on a network home, complicates the same
  `ensure_user_dir`/`chown` logic `install.sh` already has to redo in the postinstall script,
  since a pkg cannot simply invoke `install.sh`'s shell functions from inside a signed payload
  without shipping `install.sh` itself as a script resource (a second copy of the same logic,
  against the "no second copy" constraint — see Reproducibility, below).

### The Keychain token: cannot happen inside a pkg, at all

`set_token()` (`canvas_api_guard.py:215`) requires `sys.stdin.isatty()` and calls
`getpass.getpass()` for hidden terminal input; the token is then handed twice (macOS asks for the
new item's password and a retype) to `/usr/bin/security add-generic-password` over stdin, and read
back to confirm it stored correctly. None of that is available to a `postinstall` script:

- Installer runs scripts with no attached terminal, so `isatty()` is false and `set_token()`
  refuses by design, on the same line that protects it from Codex or any other non-interactive
  caller.
- Even if input could be piped in, a `postinstall` running as root would be storing the token in
  **root's** keychain, not the console user's — the opposite of what `read_token()`
  (`canvas_api_guard.py:204`) looks up, which is scoped to `account_name()`, the OS account
  running the guard.
- Under MDM there may be nobody at the keyboard at all when the package installs.

So a pkg cannot include token entry in any form, and should not try. The pkg's job stops at "the
guard and its configuration are correctly installed"; the existing `--set-token` step remains the
only path to a stored token, run by the person, in a real terminal, exactly as it is today. Two
shapes for that step, both reusing existing code with no new logic:

1. **Self-installing faculty member (no MDM).** The pkg's `postinstall` prints (to
   `/var/log/install.log`, which `-dumplog` surfaces, and to a Notification Center alert via
   `osascript -e 'display notification'` run as the console user) that installation is complete
   and to open Terminal and run `/usr/local/libexec/canvas_api_guard.py --set-token`. This is
   strictly less guided than today's launcher, which opens the Canvas token page automatically
   and reads the token in the same window as the install; a pkg-installed Mac needs a second,
   separate step the person must remember to do.
2. **MDM-deployed fleet.** The same "run `--set-token` in Terminal" instruction, but as an IT
   communication (email, onboarding doc) rather than anything the pkg itself can drive, since MDM
   pushes happen with no user present. A tiny "first-run" `.command` launcher — the existing
   Terminal launcher from `install-from-github.sh`, trimmed to just the token-entry section (no
   clone, no compile, no plan, no `sudo`) — dropped by the pkg into the user's Desktop or opened
   once via a LaunchAgent at next login, would close this gap without inventing new credential
   logic; it would just re-run `--set-token` in a visible terminal. That LaunchAgent-at-next-login
   mechanism is exactly the kind of postinstall complexity flagged above, and should be scoped
   out of a first pkg unless IT specifically wants it.

## Signing and notarization

### What each piece requires

- **Apple Developer Program membership.** $99/year, individual or organization; an organization
  additionally needs a legal-entity name and a D-U-N-S number, and its enrollment is verified by
  Apple before purchase. Accredited educational institutions, along with nonprofits and government
  entities, can enroll with a fee waived, separately from the $99 program
  (docs: https://developer.apple.com/help/account/membership/program-enrollment).
- **Developer ID Installer certificate**, distinct from a Developer ID Application certificate:
  "A certificate used to sign a Mac Installer Package, containing your signed app." Only the
  account's Account Holder can create Developer ID certificates directly, though an admin with the
  "cloud-managed Developer ID certificate access role" can also obtain cloud-managed ones; up to
  five of each certificate type are permitted per account
  (docs: https://developer.apple.com/help/account/certificates/create-developer-id-certificates/).
  Signing itself uses either `pkgbuild --sign "Developer ID Installer: <name>"` at build time, or
  `productsign --sign <identity> in.pkg out.pkg` afterward — both confirmed from the local
  `pkgbuild(1)` and `productsign(1)` man pages; no third-party signing tool is needed.
- **A meaningful difference from app certificates: validity is checked at install time, not sign
  time.** For an app, "Gatekeeper will evaluate the validity of your Developer ID certificate when
  your application is installed... users can download and run your app, even after the expiration
  date of the certificate" (as long as it was valid when built). For an installer package the rule
  is stricter: "Gatekeeper will evaluate the validity of your Developer ID Installer certificate
  when your installer package is run. Your installer package will only launch if your Developer ID
  Installer certificate is valid. Installer packages signed with a Developer ID Installer
  certificate that has expired must be re-signed with a valid Developer ID Installer certificate in
  order to run"
  (docs: https://developer.apple.com/help/account/certificates/create-developer-id-certificates/).
  This means a signed pkg does not stay installable indefinitely the way a signed app does; the
  release process (see Reproducibility, below) has to re-sign, not just keep shipping the same
  signed artifact, once the certificate nears expiry.
- **Notarization.** A separate, free step after signing: submit the signed pkg to Apple's notary
  service with `notarytool submit --wait` (authenticated with either an App Store Connect API key
  or an Apple ID app-specific password stored in a keychain item), then staple the returned ticket
  with `xcrun stapler staple`. Apple's notarizing-overview page explicitly lists "Flat installer
  packages" among the deliverable types the notary service accepts alongside apps, kernel
  extensions, and disk images
  (docs: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).
  The customization page adds one caveat worth flagging: "If you distribute your software via a
  custom third-party installer, you need two rounds of notarization. First you notarize the
  installer's payload... You then package the notarized (and stapled) items into the installer and
  notarize it as you would any other executable"
  (docs: https://developer.apple.com/documentation/security/customizing-the-notarization-workflow).
  This repository's payload is a Python script, a JSON config, a rules file, and Markdown skill
  files — none of it a Mach-O executable or app bundle — so it is **unverified** whether the
  "notarize the payload separately first" requirement actually applies here, versus notarizing the
  single flat `.pkg` in one pass the way `pkgbuild` builds it. This should be tested against a real
  build before it is relied on; it is not a blocking unknown, since a failed notarization attempt
  just means building the pkg with `--scripts` content signed and re-submitting, not a redesign.
- **Who holds the identity.** Either the guard's author personally, or Clemson IT, enrolls in the
  Apple Developer Program and creates the Developer ID Installer certificate; whichever party holds
  it is the one whose name Gatekeeper will show as the software's identified developer, and the one
  responsible for renewing the certificate before every pkg-relevant expiry. This is an open
  question below, not something this document can settle.

### What Gatekeeper actually does with each distribution shape

Apple's security guide states the general rule plainly: "When a user downloads and opens an app, a
plug-in, or an installer package from outside the App Store, Gatekeeper verifies that the software
is from an identified developer, is notarized by Apple to be free of known malicious content, and
hasn't been altered... Users and organizations have the option to allow only software installed
from the App Store. Alternatively, users can override Gatekeeper policies to open any software
unless restricted by a device management service"
(docs: https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web).
Two distribution shapes follow from this:

- **Downloaded and double-clicked (self-installing faculty).** A pkg downloaded through a browser
  picks up the `com.apple.quarantine` extended attribute, and Gatekeeper's first-launch check runs
  when the person double-clicks it. Unsigned, that check refuses to run the installer outright on
  a default-configured Mac ("Apple could not verify..."); signed and notarized, the same check
  passes and shows the identified-developer name instead of blocking. An unsigned pkg is
  effectively unusable for a person who is not comfortable right-clicking to bypass Gatekeeper,
  which is a materially worse experience than the existing `curl | sh` bootstrap, which is a shell
  script, not something Gatekeeper inspects at all today.
- **Pushed by MDM (fleet deployment).** Apple documents a dedicated MDM payload,
  `com.apple.systempolicy.control`, whose keys — `EnableAssessment` (turn Gatekeeper on/off) and
  `AllowIdentifiedDevelopers` (Mac App Store + identified developers, vs. Mac App Store only) —
  exist specifically to manage this "Gatekeeper" UI/policy from a device management service
  (docs: https://github.com/apple/device-management/blob/release/mdm/profiles/com.apple.systempolicy.control.yaml,
  Apple's own device-management schema repository). MDM tools like Jamf typically install packages
  by invoking `/usr/sbin/installer` directly (as root, non-interactively) rather than through
  Finder/LaunchServices, and a pkg delivered that way was never downloaded through a browser, so it
  never gets `com.apple.quarantine` and never triggers the interactive Gatekeeper prompt that a
  double-clicked download does. **This is inferred, not found in an Apple page that states it
  directly**, from the shape of Gatekeeper's own description above (it acts "when a user downloads
  and opens" software) plus the existence of a separate MDM policy specifically for the
  interactively-triggered check. It should be labeled unverified until confirmed against a real
  Jamf or Intune push in this institution's environment, but it matches the universal experience
  of Mac administrators: IT-signed-but-unnotarized packages are routinely pushed through MDM
  without a Gatekeeper prompt, precisely because the MDM path never triggers the check that
  notarization exists to satisfy.

The practical consequence: signing and notarization matter most for the self-install path, where a
faculty member is double-clicking a downloaded file and needs Gatekeeper to let it run without a
scary warning or a right-click workaround. They matter least — though IT policy may still require
them — for a pure MDM push, where the mechanism that would show a warning is not in the path at
all.

## MDM deployment as the real win

A `.pkg` is the one artifact shape every campus device-management tool already knows how to
target: Jamf Pro policies, Intune Win32/macOS app deployments, Munki catalogs, and any other
MDM-adjacent tool all consume `.pkg` (or `.mobileconfig` for configuration alone, which does not
apply here since there is no profile payload, just files). `curl | sh` cannot be pushed by any of
these tools in a way IT would sign off on: it requires a human at a keyboard pasting a URL, and no
enterprise change-control process treats "download and run an arbitrary shell script from GitHub"
as equivalent to "IT pushes a signed, versioned, revocable package."

What MDM deployment changes for the IT review:

- **Installation becomes a fleet-wide, auditable IT action** instead of something each faculty
  member individually pastes into Terminal. IT can target specific Macs, roll out gradually, see
  install success/failure per device, and revoke/replace with a new version the same way it
  manages every other piece of managed software.
- **The trust root shifts from "whoever can push to the `release` branch"** — which is how
  `install-from-github.sh` frames it today (docs/IT-REVIEW.md, "Optional macOS GitHub bootstrap")
  — **to "whoever can push a policy in Jamf/Intune,"** which is IT's own existing chain of custody,
  not a GitHub branch protection setting IT has no visibility into.
- **The root-owned install step needs no interactive `sudo` password prompt**, because the MDM
  agent runs `installer` as root already; today's flow always needs a human to type an
  administrator password.

What MDM deployment does **not** change:

- **The token still has to be entered by the person**, in a real terminal, exactly as described
  above — nothing about MDM changes `set_token()`'s TTY requirement or the fact that a token
  belongs to one individual's Canvas account, never a shared or provisioned credential. This is the
  one step of the entire flow that categorically cannot be centralized, by design: it is not a
  gap in the pkg, it is the guard's entire security model (`docs/IT-REVIEW.md`, "Keep the token out
  of agent-controlled storage").
- **The per-user Codex files still need a console user present** or a next-login mechanism, as
  described above; MDM pushing the pkg while nobody is logged in does not make `~/.codex/` appear
  for a user who has never logged in.
- **The guard's own provenance check, audit boundary, write-approval flow, and every other control
  documented in `docs/IT-REVIEW.md` are unchanged.** A pkg only changes how the same root-owned
  files and user-owned files get onto disk; it does not touch `canvas_api_guard.py` itself, and
  none of the security objectives in that document weaken.

## Reproducibility and trust

The standing rule here is "compact and reviewable above all," and the existing installation story
earns that by having exactly one artifact (the Git commit) and exactly one script
(`install.sh`) that turns it into installed files, with `--plan` letting a reviewer see the exact
diff before anything changes. A pkg path must not become a second, divergent way to install the
guard; it must be a thin, native-tool wrapper around the same source that `install.sh` already
installs, built reproducibly enough that a reviewer can rebuild it and compare hashes rather than
trust a downloaded binary.

- **Build script in the repo, no third-party tooling.** `tools/build-pkg.sh`, alongside the
  existing `tools/release.sh`, would invoke `pkgbuild` directly against the same source files
  `install.sh` already reads (`canvas_api_guard.py`, `codex/canvas-api-guard.rules`,
  `codex/skills/...`, and the Specialized Functions equivalents for that profile), with the
  per-user postinstall script also drawn from the same source tree rather than duplicating
  `install.sh`'s logic inline. `productbuild` is not needed unless a `choices.xml` UI for
  host/profile selection is wanted later; a single `pkgbuild --root ... --scripts ... --sign ...`
  invocation matches this repository's "no dependency, no second copy" constraint better than
  a multi-package product archive would. munkipkg and Packages.app were considered and rejected
  for the same reason: both wrap `pkgbuild`/`productbuild` with their own project-file format and
  Python/Objective-C tooling, adding a dependency this repository does not need for a single
  component package with two scripts.
- **Payload SHA-256s recorded.** The same `hash_file` shape `install.sh` already uses (SHA-256 of
  the guard script, rules, skill, and generated config) should be printed by `build-pkg.sh` and
  ideally embedded in the pkg's own metadata (a `ReadMe` resource, or a build-log artifact
  committed alongside a tagged release) so a reviewer with only the `.pkg` file can verify it
  against `pkgutil --expand` output without rebuilding from source, and can verify it *does*
  rebuild identically from a pinned commit when they want the stronger check.
- **Version mapping.** `pkgbuild --identifier <reverse-dns id> --version <version>` should use the
  same `USER_AGENT` version constants `install.sh` and `tools/release.sh` already read
  (`canvas-api-guard/1.18.0`, `canvas-api-operations/0.15.0` today) rather than inventing a
  separate pkg version number, and the identifier should encode the profile
  (`edu.clemson.canvas-api-guard.specialized-functions`, say) so Jamf/Intune's own upgrade
  comparison — which is keyed on `--identifier` plus `--version`, confirmed from the local
  `pkgbuild(1)` man page — lines up with what `RELEASE.md` already reports. The commit itself
  (`tools/release.sh`'s `$TARGET`) should be recorded too, since that is the granularity
  `~/.canvas-api-guard/installed-commit` needs, not just a guard version number.
- **`installed-commit` still gets written.** `install-from-github.sh` writes the reviewed commit to
  `$HOME/.canvas-api-guard/installed-commit` after a successful install (`install-from-github.sh:217`),
  and the existing Codex skill compares that against `RELEASE.md` to tell a person an update is
  waiting. A pkg's `postinstall` script must do the same write, to the console user's home, with
  the commit baked into the pkg at build time (the same commit `build-pkg.sh` built from) — the
  one piece of runtime state a pkg's static payload cannot supply on its own, and the one thing a
  `build-pkg.sh` absolutely must not omit, or the "an update is waiting" check silently stops
  working for every pkg-installed Mac.
- **`install.sh --plan` on a pkg-installed system.** Read directly from `install.sh`: `file_state()`
  (`install.sh:218`) compares only the installed file's SHA-256, and for root-owned destinations
  also owner and mode, against the reviewed source — it has no concept of *how* a file got there.
  So a correctly built and installed pkg, whose payload byte-for-byte matches what `install.sh`
  would have written from the same commit (root:wheel, `0555`/`0644`, identical content) and whose
  postinstall wrote the same per-user files with the same content and ownership, reports `[same]`
  across the board, exactly like a Mac installed the ordinary way. This is a genuine strength of
  the existing design: it already treats "what is installed" as the only thing that matters, not
  "how it got there," so nothing about `--plan` needs to change to support a pkg-installed Mac; the
  pkg just needs to actually reproduce what `install.sh` would have written, byte for byte.

## Update and uninstall

- **Reinstalling a newer pkg over an older one.** `installer(8)` (man page, read locally) requires
  root and simply lays down the payload and re-runs scripts; it does not itself skip or refuse a
  reinstall based on version the way some package managers do — version comparison
  (`--identifier`/`--version`) is metadata Installer.app's GUI and MDM tools use to decide whether
  to offer/push an update, not something the command-line tool enforces on its own. So running a
  newer pkg's postinstall again is exactly like running `install.sh` again: `backup_if_different`
  style behavior needs to be reproduced in the postinstall script (or accepted as "always
  overwrite," which is what a plain payload install already does, since `pkgbuild` payloads are
  laid down unconditionally). `install.sh`'s own backup-before-replace behavior for the Codex
  files is worth preserving in the postinstall script for the same reason it exists today: a
  person's local edits to `~/.codex/config.toml` should not vanish silently.
- **Receipts.** `pkgutil --pkgs` (local `pkgutil(1)` man page, read locally) lists installed
  package identifiers; `pkgutil --forget <id>` "discard[s] all receipt data about package-id, but
  do not touch the installed files" — explicitly not a substitute for actually removing anything,
  which matters for the uninstall script below (forgetting the receipt without removing the files
  would leave a root-owned guard installed with no record it came from a pkg).
- **An uninstall script.** Not currently something `install.sh` provides even for its own
  install — there is no `install.sh --uninstall` today — so this is new functionality either way,
  not something the pkg path uniquely needs. A `tools/uninstall.sh` (or a
  `postinstall`-adjacent `preremove`-style script triggered by `pkgutil --forget` plus a manual
  `rm`, since flat packages have no built-in "uninstall" verb of their own) would need to remove
  the root-owned executable/config and the per-user Codex rules/skill files, matching exactly what
  `install.sh` writes, and print rather than silently skip anything it declines to touch.
- **The audit log and Keychain item are never removed automatically, by either path.**
  `~/.canvas-api-guard/audit.jsonl` is confidential education-record data
  (`docs/IT-REVIEW.md`, "Produce useful, protected audit evidence") and the guard already documents
  that it has "no automatic retention, forwarding, or rotation policy." An uninstall script must
  say this explicitly rather than deleting the log or the Keychain item as a matter of course —
  deleting either silently would be a data-loss surprise for something IT and the person may still
  need for incident review, and the existing security posture already treats both as things a
  human decides to remove, not something an install/uninstall tool does on its own.

## The Intel-Homebrew hazard

`install.sh` already documents this failure mode and refuses closed before writing anything:
Homebrew on Intel Macs owns `/usr/local` itself (not root), so `check_ancestor_ownership`
(`install.sh:138`) walks up from `/usr/local/libexec` and `/usr/local/etc`, finds `/usr/local`
owned by the console user, and refuses with an explanation rather than a remedy, since "sudo chown"
on a Homebrew-managed prefix would be destructive advice.

A `.pkg` behaves differently here in a way that is **worse**, not better, unless the pkg
deliberately replicates the same check:

- Confirmed from the local `pkgbuild(1)` man page: `--ownership recommended` bakes root:wheel into
  the **archived payload**, and "pkgbuild never changes the ownership of the actual on-disk files,
  only the ownership that is archived into the package." That describes the build step; the
  install step (`installer(8)`, run as root) does the actual writing, and Installer creates any
  missing intermediate directories with the ownership specified by the package, but does **not**
  retroactively `chown` a directory that already exists — the existing `/usr/local`, if
  Homebrew-owned, keeps its existing owner even after a pkg drops root-owned files underneath it.
  This is consistent with, not contradicted by, `install.sh`'s own behavior, which likewise never
  changes an ancestor's ownership; the difference is that `install.sh` refuses before writing
  anything, while a plain `installer -pkg` run has no such refusal built in.
- **The consequence:** on an Intel Homebrew Mac, a pkg with no equivalent check would install
  "successfully" — `pkgutil --pkgs` shows it, the payload's own files are root-owned and correctly
  permissioned — while the guard's `trusted_path()` (`canvas_api_guard.py:111`) still refuses at
  first run, because `/usr/local` itself remains group/other-writable-by-a-non-root-owner in the
  ancestor walk. That is the same fail-closed outcome `install.sh` reaches, but reached later and
  with a worse message: instead of "refusing: /usr/local is owned by staff; the guard cannot be
  installed under a prefix a non-root user can write" printed by the installer before anything
  changed, the person (or IT, watching an MDM install report "succeeded") sees the guard itself
  fail the first time anyone tries to use it, with no indication the pkg is the reason.
- **The fix belongs in `build-pkg.sh`/`preinstall`, not in the guard.** A `preinstall` script that
  runs the same ancestor-ownership walk `install.sh` already implements (`check_ancestor_ownership`,
  `install.sh:138`) and exits non-zero — which aborts the Installer run before any payload is
  written, per the ordinary preinstall/postinstall contract described in the `pkgbuild(1)` man
  page — would restore the same fail-closed-before-writing behavior `install.sh` already has. This
  is exactly the kind of "no second copy of the guard's logic" tension the repository's standing
  rule warns about: the check must exist in the pkg's scripts too, or the pkg regresses a control
  `install.sh` already has, and the two copies (`install.sh`'s shell function and the pkg's
  `preinstall` script) will need to be kept in lockstep by hand unless `build-pkg.sh` generates the
  `preinstall` script's check directly from `install.sh`'s own function rather than
  hand-transcribing it — a concrete task for whatever plan implements this.

## Comparison table

| | `curl \| sh` (today) | `.pkg`, self-install | `.pkg`, MDM-deployed |
|---|---|---|---|
| Prerequisites | Xcode Command Line Tools (for `git`); Terminal | None beyond macOS itself for install; no `git`/CLT needed since the pkg carries the payload, not a checkout | Same as self-install, plus enrollment in the institution's MDM |
| Root step | `sudo` password, typed by the person, mid-Terminal-session | Gatekeeper prompt (signed+notarized: identified-developer dialog; unsigned: blocked or right-click bypass) then the macOS admin-password prompt Installer.app shows | None — MDM agent runs `installer` as root; no person needed to be present |
| Per-user step (Codex rules/skills/settings) | Runs as the invoking user in the same script, no extra logic | `postinstall` resolves console user; fails or defers if nobody is logged in | Same fragility, worse odds nobody is logged in at push time |
| Token step | Guard prompts inline, same Terminal session, right after install | Separate, manual: person must remember to open Terminal and run `--set-token`; a trimmed first-run launcher can prompt them | Same as self-install; IT communicates the step out-of-band, cannot be pushed |
| Update | Re-run the same one-line command; `--plan` skips unchanged files | Push/download a newer signed pkg; same `--plan`-equivalent hash comparison applies to what the payload contains | IT re-pushes the policy; same idempotency requirement on `postinstall` |
| Uninstall | Not supported by any script today | Needs a new uninstall script either way | Same, but IT can also just stop pushing/remove the policy — files remain until something removes them |
| What IT reviews | The GitHub repo, `release` branch protection, and this shell script | The signed pkg (identity + notarization ticket), plus this repo as the source it was built from | Same artifact review, plus IT's own MDM policy/scoping, which IT already knows how to audit |
| What could go wrong | Person distrusts pasting a shell command; no fleet story | Gatekeeper blocks an unsigned/unnotarized pkg; console-user detection fails silently | Ancestor-ownership hazard installs "successfully" but the guard refuses at first use, with no visible link to the pkg |

## Recommendation

Build the pkg as an **additional**, not replacement, install path, gated on two things this
document cannot resolve on its own (see Open questions): whether a Developer ID Installer
certificate is realistically obtainable, and whether the intended first audience is a self-
installing faculty pilot or an IT-deployed fleet. If neither is available yet, an **unsigned** pkg
is still worth building for the MDM case specifically, since MDM-pushed installs plausibly never
hit the Gatekeeper check that unsigned software fails — but it should not be offered as a
self-install download link until it is signed and notarized, because an unsigned pkg downloaded
through a browser is a strictly worse experience than the existing `curl | sh` line, which at
least runs without Gatekeeper's involvement at all.

The reasoning: this repository's actual constraint is not "can a pkg technically install these
files" (it obviously can, trivially, with native tools and no new dependency) — it is whether the
extra machinery (postinstall console-user detection, Gatekeeper/signing/notarization, ancestor-
ownership re-implementation, a version/receipt story that stays honest with `install.sh --plan`)
earns its keep against "compact and reviewable above all." It earns its keep specifically for MDM
deployment, which `curl | sh` structurally cannot serve; it does not obviously earn its keep as a
second self-install option next to a launcher that already does more hand-holding (opens the
Canvas token page, reads the token in the same window, shows the exact plan before `sudo`) than a
pkg realistically can.

### Tasks a later implementation plan would contain

1. `tools/build-pkg.sh`: assemble a `pkgbuild --root` payload from the same source files
   `install.sh` reads, generate `config.json` from the same `--host`/`--profile` inputs
   `install-from-github.sh` already exposes, write a `preinstall` script that reimplements (or is
   generated from) `install.sh`'s `check_ancestor_ownership`, and a `postinstall` script that
   resolves the console user, writes the per-user Codex files with `install.sh`'s
   backup-before-replace behavior, merges the three Codex settings the same way, and writes
   `~/.canvas-api-guard/installed-commit`.
2. Decide and implement the host/profile selection story: one pkg per institution/profile
   combination (simplest, matches the repo default) versus a `productbuild` distribution with a
   `choices.xml` picker (more general, more surface area).
3. A signing/notarization step in `tools/build-pkg.sh` or a sibling script, conditioned on a
   Developer ID Installer identity being available in the build environment's keychain; falls back
   to an unsigned build with a clear warning when it is not.
4. A first-run token-entry launcher (trimmed from `install-from-github.sh`'s existing `.command`
   generation) that the pkg either tells the person to run manually, or drops as a LaunchAgent for
   the MDM case — decide which, per the open questions below.
5. `tools/uninstall.sh` (useful independent of the pkg work, since `install.sh` has no uninstall
   today), written once and reused by both a pkg-based uninstall and a manual one.
6. Extend `docs/IT-REVIEW.md`'s "Installation controls" section to describe the pkg path once it
   exists, without weakening anything currently stated there.
7. A reviewer command list for the pkg equivalent of `docs/IT-REVIEW.md`'s existing "Reviewer
   commands" section: `pkgutil --check-signature`, `pkgutil --expand` plus hash comparison against
   the reviewed commit, and rebuilding `build-pkg.sh` from the same commit to compare output
   byte-for-byte.

## Open questions only the owner can answer

- **Apple Developer account.** Does the guard's author already hold, or want to newly enroll in,
  an Apple Developer Program membership ($99/year, or a fee waiver if enrolling as or through an
  accredited institution)? Signing and notarization are blocked on this either way.
- **Clemson IT's own signing identity or MDM.** Does Clemson IT already have a Developer ID
  (organizational enrollment, which needs a D-U-N-S number and legal-entity verification) or an
  existing MDM (Jamf, Intune, or otherwise) this could be pushed through? If IT already signs and
  distributes other internal tools this way, that changes who should hold the identity and who
  builds/signs releases.
- **Intended audience.** Is the near-term goal still "faculty install this themselves," in which
  case the existing `curl | sh` launcher already does more than a pkg realistically can (opens the
  token page, single guided session) and a pkg's main value is smaller than it looks — or is the
  goal now (or soon) "IT deploys this to a managed fleet," in which case the pkg is the only path
  that actually fits how IT operates, and is worth building even unsigned as a first cut for MDM
  testing?
- **Whether `python3` from the Command Line Tools can be assumed on managed Macs.** `install.sh`
  already refuses to install without a root-owned, executable `/usr/bin/python3`
  (`install.sh:107`-`126`), and the README states this is "the case on Apple silicon Macs" as a
  precondition today. A managed Mac provisioned by IT may or may not have the Command Line Tools
  present out of the box, and unlike a person running `curl | sh` interactively (who gets a clear
  "run `xcode-select --install`" message today), an MDM-pushed pkg has nobody watching to see, let
  alone act on, that message if the precondition is not met. Whether Clemson's standard managed
  image includes the Command Line Tools is something only the owner (or Clemson IT) can confirm.
