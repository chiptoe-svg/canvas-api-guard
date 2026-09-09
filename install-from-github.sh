#!/bin/sh
# Download one immutable canvas-api-guard commit, then open a real macOS Terminal window for
# the reviewed installation and token entry. This bootstrap never receives either secret.

set -eu

REPOSITORY=https://github.com/chiptoe-svg/canvas-api-guard.git
GIT_BIN=/usr/bin/git
OPEN_BIN=/usr/bin/open
TERMINAL_APP=/System/Applications/Utilities/Terminal.app
CANVAS_HOST=
SOURCE_REF=
RELEASE_REF=c08ad4c43de11e164a0bcbc329d4d151f88e0847   # pinned by tools/release.sh
DEFAULT_HOST=clemson.instructure.com    # this repository's institution; --host overrides
DEFAULT_PROFILE=specialized-functions
PROFILE=

die() {
    printf 'canvas-api-guard bootstrap: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Install or update canvas-api-guard. Paste into Terminal:

  curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/release/install-from-github.sh | sh

Options: [--ref FULL_COMMIT_SHA] [--host school.instructure.com] [--profile api-only|specialized-functions]
Defaults: the reviewed commit pinned on the release branch, clemson.instructure.com, specialized-functions.

Downloads exactly one commit, checks it, shows what will change, and installs it. Run from
a terminal, it asks its questions right there: Return to continue, the Mac administrator
password only when a root-owned file must change, and a Canvas API token only when the
Keychain holds none (an existing token is kept and never read or displayed). Running it again
is how you update; an up-to-date Mac is told so and nothing changes.

Run without a terminal (Codex), it opens a macOS Terminal window for those questions instead
and prints a private, non-secret completion-status file for Codex to watch. Codex must run it
with host/GUI execution permission, since its sandbox cannot open applications.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --ref) shift; [ "$#" -gt 0 ] || die "--ref needs a value"; SOURCE_REF=$1 ;;
        --host) shift; [ "$#" -gt 0 ] || die "--host needs a value"; CANVAS_HOST=$1 ;;
        --profile) shift; [ "$#" -gt 0 ] || die "--profile needs a value"; PROFILE=$1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

CANVAS_HOST=${CANVAS_HOST:-$DEFAULT_HOST}
PROFILE=${PROFILE:-$DEFAULT_PROFILE}
case "$PROFILE" in
    api-only|level-1) PROFILE=level-1 ;;
    specialized-functions|level-2) PROFILE=level-2 ;;
    *) die "--profile must be api-only or specialized-functions" ;;
esac

if [ -z "$SOURCE_REF" ]; then
    [ -n "$RELEASE_REF" ] || die "this copy carries no release pin; pass --ref FULL_COMMIT_SHA or fetch it from the release branch"
    SOURCE_REF=$RELEASE_REF
fi
case "$SOURCE_REF" in
    *[!0-9a-f]*|"") die "--ref must be a full lowercase hexadecimal commit SHA" ;;
esac
[ "${#SOURCE_REF}" -eq 40 ] || die "--ref must contain exactly 40 hexadecimal characters"

case "$CANVAS_HOST" in
    ""|*[!A-Za-z0-9.-]*|.*|*..*|*.) die "invalid Canvas host: $CANVAS_HOST" ;;
esac

[ "$(uname -s)" = Darwin ] || die "the .command workflow is available only on macOS"
[ -x "$GIT_BIN" ] || die "git is required at $GIT_BIN"
# On a Mac, /usr/bin/git is a shim for the Xcode command line tools: it refuses to run until
# the tools are installed and, when Xcode itself is present, until its license is accepted.
# Say which, and the one command that fixes it, instead of surfacing git's own message.
GIT_CHECK=$("$GIT_BIN" --version 2>&1) || {
    case "$GIT_CHECK" in
        *icense*) die "the Xcode license has not been accepted; in Terminal run: sudo xcodebuild -license accept   then rerun this command" ;;
        *) die "the Xcode command line tools are not usable ($GIT_CHECK); run: xcode-select --install   then rerun this command" ;;
    esac
}
[ -x "$OPEN_BIN" ] || die "the macOS open command is required at $OPEN_BIN"
[ -d "$TERMINAL_APP" ] || die "macOS Terminal is required at $TERMINAL_APP"

INSTALL_ROOT=$(mktemp -d /private/tmp/canvas-api-guard-install.XXXXXX)
chmod 0700 "$INSTALL_ROOT"
CHECKOUT="$INSTALL_ROOT/repository"
LAUNCHER="$INSTALL_ROOT/install-canvas-api-guard.command"
STATUS_FILE="$INSTALL_ROOT/completion-status.json"

cleanup_before_open() {
    rm -rf "$INSTALL_ROOT"
}
trap cleanup_before_open EXIT HUP INT TERM

"$GIT_BIN" clone --quiet "$REPOSITORY" "$CHECKOUT" || die "GitHub clone failed"
"$GIT_BIN" -C "$CHECKOUT" checkout --quiet --detach "$SOURCE_REF" \
    || die "commit $SOURCE_REF is not available from the repository"

ACTUAL_REF=$("$GIT_BIN" -C "$CHECKOUT" rev-parse HEAD)
[ "$ACTUAL_REF" = "$SOURCE_REF" ] || die "downloaded commit does not match --ref"
[ -z "$("$GIT_BIN" -C "$CHECKOUT" status --porcelain)" ] \
    || die "downloaded checkout is not clean"

umask 077
printf '{"state":"launched","commit":"%s","profile":"%s"}\n' "$SOURCE_REF" "$PROFILE" > "$STATUS_FILE"
chmod 0600 "$STATUS_FILE"

cat > "$LAUNCHER" <<EOF
#!/bin/sh
set -eu
# One run only: the bootstrap may open this launcher twice if Terminal's first attempt lost
# the path while the shell was starting. mkdir is atomic; a second copy exits quietly.
mkdir "$INSTALL_ROOT/running.lock" 2>/dev/null || exit 0
settings=ok

finish() {
    status=\$?
    trap - EXIT HUP INT TERM
    if [ "\$status" -eq 0 ]; then
        state=succeeded
    else
        state=failed
    fi
    status_temp="$STATUS_FILE.\$\$.tmp"
    (umask 077; printf '{"state":"%s","commit":"%s","profile":"%s","exit_status":%s,"codex_settings":"%s"}\n' \
        "\$state" "$SOURCE_REF" "$PROFILE" "\$status" "\$settings" > "\$status_temp" && mv -f "\$status_temp" "$STATUS_FILE") \
        || printf 'Warning: could not update completion-status file.\n' >&2
    rm -f "\$0"
    printf '\n'
    if [ "\$status" -eq 0 ]; then
        printf 'canvas-api-guard is installed at this commit with a stored token.\n'
        [ "\$settings" = ok ] || printf 'The Codex settings WARNING above still needs your attention.\n'
    else
        printf 'The workflow stopped with exit status %s. Review the output above.\n' "\$status" >&2
    fi
    printf 'The reviewed checkout remains at:\n  %s\n' "$CHECKOUT"
    if [ -z "\${CANVAS_GUARD_INLINE:-}" ]; then
        printf '\nPress Return to close this window. '
        read unused || true
    fi
    exit "\$status"
}
trap finish EXIT HUP INT TERM

status_temp="$STATUS_FILE.\$\$.tmp"
(umask 077; printf '{"state":"running","commit":"%s","profile":"%s"}\n' \
    "$SOURCE_REF" "$PROFILE" > "\$status_temp" && mv -f "\$status_temp" "$STATUS_FILE") \
    || { printf 'Could not initialize completion-status file.\n' >&2; exit 1; }

cd "$CHECKOUT"
printf 'Installing reviewed canvas-api-guard commit:\n  %s\n\n' "$SOURCE_REF"
python3 -m py_compile canvas_api_guard.py test_canvas_api_guard.py
python3 -m unittest
sh -n install.sh
git diff --check
plan_status=0
./install.sh --plan --profile "$PROFILE" --host "$CANVAS_HOST" || plan_status=\$?
if [ "\$plan_status" -eq 3 ]; then
    printf '\nThis Mac already has this commit installed; no administrator password is needed.\n'
elif [ "\$plan_status" -eq 5 ]; then
    printf '\nThis Mac already has this commit installed. The Codex settings WARNING above needs your attention.\n'
    settings=attention
elif [ "\$plan_status" -eq 4 ]; then
    printf '\nOnly the Codex rules, skills, or settings differ; updating them needs no administrator password.\n\n'
    "$CHECKOUT/install.sh" --profile "$PROFILE" --host "$CANVAS_HOST"
elif [ "\$plan_status" -ne 0 ]; then
    exit "\$plan_status"
else
    printf '\nThat plan is what the next step will do. Nothing has changed yet.\n'
    printf 'Press Return to continue with the installation, or Ctrl-C to stop now. '
    if ! read reviewed; then
        printf '\nNo terminal to confirm on; not installing.\n' >&2
        exit 1
    fi
    printf '\nThe next prompt is for your Mac administrator password.\n'
    printf 'Nothing will appear while you type it.\n\n'
    /usr/bin/sudo "$CHECKOUT/install.sh" --profile "$PROFILE" --host "$CANVAS_HOST"
fi

# After an install, the same plan must find nothing left to change.
if [ "\$plan_status" -eq 0 ] || [ "\$plan_status" -eq 4 ]; then
    after=0
    ./install.sh --plan --profile "$PROFILE" --host "$CANVAS_HOST" >/dev/null || after=\$?
    case "\$after" in
        3) ;;
        5) settings=attention ;;
        *) printf '\nAfter installing, the plan still reports changes (exit status %s).\n' "\$after" >&2; exit 1 ;;
    esac
fi

# Attribute lookup only (no -w): it reports whether a token item exists and never prints it.
if /usr/bin/security find-generic-password -s canvas-api-guard -a "\$(id -un)" >/dev/null 2>&1; then
    printf '\nA Canvas API token is already stored; it was not read, changed, or re-entered.\n'
    printf 'To replace it later, run: /usr/local/libexec/canvas_api_guard.py --set-token\n'
else
    printf '\nThe next prompt is for your Canvas API token. Make one at\n'
    printf '  https://$CANVAS_HOST/profile/settings  (Approved Integrations, "+ New Access Token")\n'
    printf 'That page is opening in your browser. Paste the token here and press Return; it will not appear on screen.\n\n'
    /usr/bin/open "https://$CANVAS_HOST/profile/settings" 2>/dev/null || true
    /usr/local/libexec/canvas_api_guard.py --set-token
fi

# Record what is installed where Codex can read it, so the skill can compare it with the
# release note on GitHub and tell the person when an update is waiting.
printf '%s\n' "$SOURCE_REF" > "\$HOME/.canvas-api-guard/installed-commit"

printf '\nInstalled version:\n'
/usr/local/libexec/canvas_api_guard.py --version

printf '\nDone. Quit and reopen the ChatGPT app, start a new conversation, and ask it:\n'
printf '  In Canvas, what are my current classes?\n'
EOF

chmod 0700 "$LAUNCHER"
# A person who pasted this into a terminal already has a window: run the launcher right here,
# with stdin from that terminal (under "curl | sh", stdin is the script itself). Codex has no
# terminal, so /dev/tty cannot be opened, and it takes the Terminal-window path below.
if { exec 3</dev/tty; } 2>/dev/null; then
    exec 3<&-
    trap - EXIT HUP INT TERM
    CANVAS_GUARD_INLINE=1 exec /bin/sh "$LAUNCHER" </dev/tty
fi
trap - EXIT HUP INT TERM
# Terminal runs a .command file by starting a login shell and typing the file's path into it.
# On a cold launch of Terminal the shell can still be starting when the path is typed, and
# characters are lost (seen live on two Macs: zsh received i/tmp/... for /private/tmp/...).
# So: launch Terminal first and wait for it, then open the launcher, then confirm the
# launcher reported "running"; if it did not, open it once more. The launcher's lock makes a
# second copy exit without doing anything.
"$OPEN_BIN" -g -j -a "$TERMINAL_APP" 2>/dev/null || true
waited=0
until /usr/bin/pgrep -xq Terminal || [ "$waited" -ge 20 ]; do sleep 0.5; waited=$((waited + 1)); done
launcher_running() { grep -q '"state":"running"' "$STATUS_FILE" 2>/dev/null; }
open_launcher() {
    "$OPEN_BIN" -a "$TERMINAL_APP" "$LAUNCHER" || {
        rm -f "$LAUNCHER"
        die "macOS could not open the Terminal launcher. If Codex ran this command, it must be rerun with host/GUI execution permission; checkout retained at $CHECKOUT"
    }
    waited=0
    until launcher_running || [ "$waited" -ge 30 ]; do sleep 0.5; waited=$((waited + 1)); done
}
open_launcher
if ! launcher_running; then
    printf 'Terminal did not start the launcher on the first try; opening it again.\n'
    open_launcher
fi

printf 'Opened a visible macOS Terminal installation window.\n'
# Terminal types the launcher's path into a fresh login shell. A slow or interactive shell
# startup can swallow the first characters, and the shell then reports "no such file or
# directory" for a truncated path. The launcher is untouched by that, so say how to run it.
printf 'If that window shows "no such file or directory", or stays at a bare prompt, paste this\n'
printf 'whole line into it and press Return (the launcher waits and deletes itself after running):\n'
printf '  %s\n' "$LAUNCHER"
printf 'Downloaded and verified commit: %s\n' "$SOURCE_REF"
printf 'Completion status file: %s\n' "$STATUS_FILE"
printf 'It contains only workflow state, commit, profile, and exit status; never a password, token, or Canvas data.\n'
printf 'A succeeded or failed state is final immediately and is written before Terminal waits for Return.\n'
printf 'For an active Codex task: read this file once; if it is still launched/running, use one watcher that exits at a final state. Do not use a fixed polling loop.\n'
printf 'The temporary launcher contains no password or Canvas token and deletes itself.\n'
