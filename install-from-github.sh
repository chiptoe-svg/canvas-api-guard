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
PROFILE=level-1                         # stable on-disk compatibility key

die() {
    printf 'canvas-api-guard bootstrap: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage: install-from-github.sh --ref FULL_COMMIT_SHA --host school.instructure.com [--profile api-only|specialized-functions]

Downloads exactly FULL_COMMIT_SHA, creates a private self-deleting .command launcher, and
opens it in macOS Terminal. The same command serves a new Mac, an older installation, and an
up-to-date one: the reviewed plan compares every installed file's SHA-256 with the downloaded
commit, and the administrator password is asked for only when a file needs to change. The
Canvas API token is asked for only when the Keychain holds none; an existing token is kept and
never read or displayed. Neither secret is passed to this bootstrap or stored in the launcher.
A private, non-secret completion-status JSON file is printed after Terminal launches so an
active Codex task can wait for success or failure without observing either prompt.

When Codex runs this bootstrap, the command must be granted host/GUI execution permission;
macOS applications cannot be launched from the normal Codex filesystem sandbox.
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

case "$PROFILE" in
    api-only|level-1) PROFILE=level-1 ;;
    specialized-functions|level-2) PROFILE=level-2 ;;
    *) die "--profile must be api-only or specialized-functions" ;;
esac

case "$SOURCE_REF" in
    *[!0-9a-f]*|"") die "--ref must be a full lowercase hexadecimal commit SHA" ;;
esac
[ "${#SOURCE_REF}" -eq 40 ] || die "--ref must contain exactly 40 hexadecimal characters"

case "$CANVAS_HOST" in
    ""|*[!A-Za-z0-9.-]*|.*|*..*|*.) die "invalid Canvas host: $CANVAS_HOST" ;;
esac

[ "$(uname -s)" = Darwin ] || die "the .command workflow is available only on macOS"
[ -x "$GIT_BIN" ] || die "git is required at $GIT_BIN"
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

finish() {
    status=\$?
    trap - EXIT HUP INT TERM
    if [ "\$status" -eq 0 ]; then
        state=succeeded
    else
        state=failed
    fi
    status_temp="$STATUS_FILE.\$\$.tmp"
    (umask 077; printf '{"state":"%s","commit":"%s","profile":"%s","exit_status":%s}\n' \
        "\$state" "$SOURCE_REF" "$PROFILE" "\$status" > "\$status_temp" && mv -f "\$status_temp" "$STATUS_FILE") \
        || printf 'Warning: could not update completion-status file.\n' >&2
    rm -f "\$0"
    printf '\n'
    if [ "\$status" -eq 0 ]; then
        printf 'canvas-api-guard is installed at this commit with a stored token.\n'
    else
        printf 'The workflow stopped with exit status %s. Review the output above.\n' "\$status" >&2
    fi
    printf 'The reviewed checkout remains at:\n  %s\n' "$CHECKOUT"
    printf '\nPress Return to close this window. '
    read unused || true
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

# Attribute lookup only (no -w): it reports whether a token item exists and never prints it.
if /usr/bin/security find-generic-password -s canvas-api-guard -a "\$(id -un)" >/dev/null 2>&1; then
    printf '\nA Canvas API token is already stored; it was not read, changed, or re-entered.\n'
    printf 'To replace it later, run: /usr/local/libexec/canvas_api_guard.py --set-token\n'
else
    printf '\nThe next prompt is for your Canvas API token.\n'
    printf 'Paste the token and press Return; it will not appear on screen.\n\n'
    /usr/local/libexec/canvas_api_guard.py --set-token
fi

printf '\nInstalled version:\n'
/usr/local/libexec/canvas_api_guard.py --version

printf '\nReturn to Codex and use this read-only Canvas smoke test:\n'
printf '  In Canvas, what are my current classes?\n'
EOF

chmod 0700 "$LAUNCHER"
trap - EXIT HUP INT TERM
"$OPEN_BIN" -a "$TERMINAL_APP" "$LAUNCHER" || {
    rm -f "$LAUNCHER"
    die "macOS could not open the Terminal launcher. If Codex ran this command, it must be rerun with host/GUI execution permission; checkout retained at $CHECKOUT"
}

printf 'Opened a visible macOS Terminal installation window.\n'
printf 'Downloaded and verified commit: %s\n' "$SOURCE_REF"
printf 'Completion status file: %s\n' "$STATUS_FILE"
printf 'It contains only workflow state, commit, profile, and exit status; never a password, token, or Canvas data.\n'
printf 'A succeeded or failed state is final immediately and is written before Terminal waits for Return.\n'
printf 'For an active Codex task: read this file once; if it is still launched/running, use one watcher that exits at a final state. Do not use a fixed polling loop.\n'
printf 'The temporary launcher contains no password or Canvas token and deletes itself.\n'
