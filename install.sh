#!/bin/sh
# Install canvas_api_guard.py so the invoking user can execute it but not edit it, and
# put the Codex rules and skill where Codex looks for them.
#
#   sudo ./install.sh
#
# macOS and Linux. Installs the script root-owned, mode 0555, into /usr/local/libexec;
# creates the audit log 0600 owned by the invoking user; copies codex/ files into that
# user's ~/.codex. Prints optional hardening commands; does not run them.

set -eu

SRC_DIR=$(cd "$(dirname "$0")" && pwd)
SCRIPT="$SRC_DIR/canvas_api_guard.py"
DEST_DIR=/usr/local/libexec
DEST="$DEST_DIR/canvas_api_guard.py"

if [ "$(id -u)" -ne 0 ]; then
    echo "install.sh must run as root: sudo ./install.sh" >&2
    exit 1
fi
if [ ! -f "$SCRIPT" ]; then
    echo "cannot find $SCRIPT" >&2
    exit 1
fi

case "$(uname -s)" in
    Darwin) ROOT_GROUP=wheel; IMMUTABLE="chflags schg"; APPEND_ONLY="chflags sappnd" ;;
    Linux)  ROOT_GROUP=root;  IMMUTABLE="chattr +i";    APPEND_ONLY="chattr +a" ;;
    *) echo "unsupported platform $(uname -s): macOS and Linux only" >&2; exit 1 ;;
esac

# the user who invoked sudo owns the log and the Codex files; root owns the script
USER_NAME=${SUDO_USER:-$(id -un)}
USER_HOME=$(eval echo "~$USER_NAME")
LOG_DIR="$USER_HOME/.canvas-api-guard"
LOG="$LOG_DIR/audit.jsonl"
CODEX_HOME="$USER_HOME/.codex"

install -d -o root -g "$ROOT_GROUP" -m 0755 "$DEST_DIR"
install -o root -g "$ROOT_GROUP" -m 0555 "$SCRIPT" "$DEST"
echo "installed $DEST (root:$ROOT_GROUP, 0555 - executable by everyone, writable by no one)"

install -d -o "$USER_NAME" -m 0700 "$LOG_DIR"
[ -f "$LOG" ] || : > "$LOG"
chown "$USER_NAME" "$LOG"
chmod 0600 "$LOG"
echo "log ready at $LOG ($USER_NAME, 0600)"

if [ -d "$CODEX_HOME" ]; then
    install -d -o "$USER_NAME" -m 0755 "$CODEX_HOME/rules" "$CODEX_HOME/skills"
    install -d -o "$USER_NAME" -m 0755 "$CODEX_HOME/skills/canvas-api-guard"
    install -o "$USER_NAME" -m 0644 "$SRC_DIR/codex/canvas-api-guard.rules" "$CODEX_HOME/rules/canvas-api-guard.rules"
    install -o "$USER_NAME" -m 0644 "$SRC_DIR/codex/skills/canvas-api-guard/SKILL.md" "$CODEX_HOME/skills/canvas-api-guard/SKILL.md"
    echo "Codex rules installed at $CODEX_HOME/rules/canvas-api-guard.rules"
    echo "Codex skill installed at $CODEX_HOME/skills/canvas-api-guard/SKILL.md"
else
    echo "no $CODEX_HOME: Codex is not set up for $USER_NAME; run this again after it is, or copy"
    echo "  codex/canvas-api-guard.rules -> ~/.codex/rules/  and  codex/skills/canvas-api-guard -> ~/.codex/skills/"
fi

cat <<EON

Next, as $USER_NAME:
  $DEST --set-token
  echo '{"host": "school.instructure.com"}' > $LOG_DIR/config.json

Then merge these lines into $CODEX_HOME/config.toml (the reasons are in codex/config.toml):
  sandbox_mode       = "workspace-write"
  approval_policy    = "on-request"
  approvals_reviewer = "user"

Optional hardening (not run automatically; each needs a boot-time change to undo):
  sudo $IMMUTABLE $DEST      # the script cannot be modified or replaced
  sudo $APPEND_ONLY $LOG     # the log can be added to but not rewritten or truncated
EON
