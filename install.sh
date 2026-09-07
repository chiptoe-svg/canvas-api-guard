#!/bin/sh
# Install canvas_api_guard.py so the invoking user can execute it but not edit it.
#
#   sudo ./install.sh
#
# Installs root-owned mode 0555 into /usr/local/libexec, and creates the audit log
# mode 0600 owned by the invoking user. Prints two optional hardening commands; it
# does not run them.

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

# the user who invoked sudo owns the log; root owns the script
USER_NAME=${SUDO_USER:-$(id -un)}
USER_HOME=$(eval echo "~$USER_NAME")
LOG_DIR="$USER_HOME/.canvas-api-guard"
LOG="$LOG_DIR/audit.jsonl"

install -d -o root -g wheel -m 0755 "$DEST_DIR"
install -o root -g wheel -m 0555 "$SCRIPT" "$DEST"
echo "installed $DEST (root:wheel, 0555 - executable by everyone, writable by no one)"

install -d -o "$USER_NAME" -m 0700 "$LOG_DIR"
if [ ! -f "$LOG" ]; then
    : > "$LOG"
fi
chown "$USER_NAME" "$LOG"
chmod 0600 "$LOG"
echo "log ready at $LOG ($USER_NAME, 0600)"

cat <<EOF

Next, as $USER_NAME:
  $DEST --set-token
  echo '{"host": "school.instructure.com"}' > $LOG_DIR/config.json

Optional hardening (not run automatically - both require a reboot into single-user
mode, or a boot-time change, to undo):

  sudo chflags schg $DEST
      system-immutable: nobody, including root at the current securelevel, can modify
      or replace the script until the flag is cleared.

  sudo chflags sappnd $LOG
      system append-only: the log can be added to but not rewritten or truncated,
      so past entries cannot be edited away.
EOF
