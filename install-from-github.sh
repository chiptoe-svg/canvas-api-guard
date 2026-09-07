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

die() {
    printf 'canvas-api-guard bootstrap: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage: install-from-github.sh --ref FULL_COMMIT_SHA --host school.instructure.com

Downloads exactly FULL_COMMIT_SHA, creates a private self-deleting .command launcher, and
opens it in macOS Terminal. Terminal prompts for the Mac administrator password and then the
Canvas API token. Neither secret is passed to this bootstrap or stored in the launcher.

When Codex runs this bootstrap, the command must be granted host/GUI execution permission;
macOS applications cannot be launched from the normal Codex filesystem sandbox.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --ref) shift; [ "$#" -gt 0 ] || die "--ref needs a value"; SOURCE_REF=$1 ;;
        --host) shift; [ "$#" -gt 0 ] || die "--host needs a value"; CANVAS_HOST=$1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

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

cat > "$LAUNCHER" <<EOF
#!/bin/sh
set -eu

finish() {
    status=\$?
    trap - EXIT HUP INT TERM
    rm -f "\$0"
    printf '\n'
    if [ "\$status" -eq 0 ]; then
        printf 'canvas-api-guard installation and token storage completed successfully.\n'
    else
        printf 'The workflow stopped with exit status %s. Review the output above.\n' "\$status" >&2
    fi
    printf 'The reviewed checkout remains at:\n  %s\n' "$CHECKOUT"
    printf '\nPress Return to close this window. '
    read unused || true
    exit "\$status"
}
trap finish EXIT HUP INT TERM

cd "$CHECKOUT"
printf 'Installing reviewed canvas-api-guard commit:\n  %s\n\n' "$SOURCE_REF"
python3 -m py_compile canvas_api_guard.py test_canvas_api_guard.py
python3 -m unittest
sh -n install.sh
git diff --check
./install.sh --plan --host "$CANVAS_HOST"

printf '\nThe next prompt is for your Mac administrator password.\n'
printf 'Nothing will appear while you type it.\n\n'
/usr/bin/sudo "$CHECKOUT/install.sh" --host "$CANVAS_HOST"

printf '\nThe next prompt is for your Canvas API token.\n'
printf 'Paste the token and press Return; it will not appear on screen.\n\n'
/usr/local/libexec/canvas_api_guard.py --set-token

printf '\nInstalled version:\n'
/usr/local/libexec/canvas_api_guard.py --version
EOF

chmod 0700 "$LAUNCHER"
trap - EXIT HUP INT TERM
"$OPEN_BIN" -a "$TERMINAL_APP" "$LAUNCHER" || {
    rm -f "$LAUNCHER"
    die "macOS could not open the Terminal launcher. If Codex ran this command, it must be rerun with host/GUI execution permission; checkout retained at $CHECKOUT"
}

printf 'Opened a visible macOS Terminal installation window.\n'
printf 'Downloaded and verified commit: %s\n' "$SOURCE_REF"
printf 'The temporary launcher contains no password or Canvas token and deletes itself.\n'
