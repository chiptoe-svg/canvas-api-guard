#!/bin/sh
# Reviewable Codex-led installer. It performs no authentication and makes no network calls.
#
#   ./install.sh --plan --host school.instructure.com
#   sudo ./install.sh --host school.instructure.com

set -eu

usage() {
    destination=${1:-2}
    if [ "$destination" = 1 ]; then
        echo "usage: $0 [--plan] [--allow-dirty] --host school.instructure.com"
        exit 0
    fi
    echo "usage: $0 [--plan] [--allow-dirty] --host school.instructure.com" >&2
    exit 2
}

PLAN=no
ALLOW_DIRTY=no
CANVAS_HOST=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) PLAN=yes ;;
        --allow-dirty) ALLOW_DIRTY=yes ;;
        --host) shift; [ "$#" -gt 0 ] || usage; CANVAS_HOST=$1 ;;
        -h|--help) usage 1 ;;
        *) usage ;;
    esac
    shift
done

case "$CANVAS_HOST" in
    ""|*[!A-Za-z0-9.-]*|.*|*..*|*.)
        echo "invalid Canvas host: $CANVAS_HOST" >&2
        exit 2
        ;;
esac

SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$SRC_DIR/canvas_api_guard.py"
RULES="$SRC_DIR/codex/canvas-api-guard.rules"
SKILL="$SRC_DIR/codex/skills/canvas-api-guard/SKILL.md"
DEST_DIR=/usr/local/libexec
DEST="$DEST_DIR/canvas_api_guard.py"
CONFIG_DIR=/usr/local/etc/canvas-api-guard
CONFIG="$CONFIG_DIR/config.json"

for required in "$SCRIPT" "$RULES" "$SKILL"; do
    if [ ! -f "$required" ]; then
        echo "cannot find required source file: $required" >&2
        exit 1
    fi
done

case "$(uname -s)" in
    Darwin)
        ROOT_GROUP=wheel
        IMMUTABLE="chflags schg"
        APPEND_ONLY="chflags sappnd"
        hash_file() { shasum -a 256 "$1" | awk '{print $1}'; }
        ;;
    Linux)
        ROOT_GROUP=root
        IMMUTABLE="chattr +i"
        APPEND_ONLY="chattr +a"
        hash_file() { sha256sum "$1" | awk '{print $1}'; }
        ;;
    *)
        echo "unsupported platform $(uname -s): macOS and Linux only" >&2
        exit 1
        ;;
esac

SOURCE_SHA=$(hash_file "$SCRIPT")
RULES_SHA=$(hash_file "$RULES")
SKILL_SHA=$(hash_file "$SKILL")

USER_NAME=${SUDO_USER:-$(id -un)}
case "$(uname -s)" in
    Darwin) USER_DIR=$(id -P "$USER_NAME" | awk -F: '{print $9}') ;;
    Linux) USER_DIR=$(getent passwd "$USER_NAME" | awk -F: '{print $6}') ;;
esac
case "$USER_DIR" in
    /*) ;;
    *) echo "could not resolve an absolute home directory for $USER_NAME" >&2; exit 1 ;;
esac

LOG_DIR="$USER_DIR/.canvas-api-guard"
LOG="$LOG_DIR/audit.jsonl"
CODEX_DIR="$USER_DIR/.codex"
RULE_DEST="$CODEX_DIR/rules/canvas-api-guard.rules"
SKILL_DEST="$CODEX_DIR/skills/canvas-api-guard/SKILL.md"

SOURCE_STATE="release archive or non-git source"
if command -v git >/dev/null 2>&1 && git -C "$SRC_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    REVISION=$(git -C "$SRC_DIR" rev-parse HEAD)
    if [ -n "$(git -C "$SRC_DIR" status --porcelain --untracked-files=no)" ]; then
        SOURCE_STATE="git revision $REVISION with tracked modifications"
        if [ "$PLAN" = no ] && [ "$ALLOW_DIRTY" = no ]; then
            echo "refusing to install a modified checkout: $SOURCE_STATE" >&2
            echo "commit/revert the changes, or rerun with --allow-dirty after reviewing the hash" >&2
            exit 1
        fi
    else
        SOURCE_STATE="clean git revision $REVISION"
    fi
fi

if [ "$PLAN" = yes ]; then
    cat <<EOP
canvas-api-guard installation plan (no changes made)
  source:       $SOURCE_STATE
  guard sha:    $SOURCE_SHA
  rules sha:    $RULES_SHA
  skill sha:    $SKILL_SHA
  Canvas host:  $CANVAS_HOST
  executable:   $DEST (root:$ROOT_GROUP, 0555)
  config:       $CONFIG (root:$ROOT_GROUP, 0644; profile level-1)
  audit log:    $LOG ($USER_NAME, 0600; containing confidential education records)
  Codex rules:  $RULE_DEST ($USER_NAME, 0644)
  Codex skill:  $SKILL_DEST ($USER_NAME, 0644)

The installer performs no Canvas request and does not read or store a token.
Run the same command through sudo without --plan only after reviewing this plan.
EOP
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "installation requires root ownership: rerun with sudo after reviewing --plan" >&2
    exit 1
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
backup_if_different() {
    source_file=$1
    destination_file=$2
    if [ -f "$destination_file" ] && ! cmp -s "$source_file" "$destination_file"; then
        cp -p "$destination_file" "$destination_file.bak-$STAMP"
        echo "backed up $destination_file"
    fi
}

refuse_link() {
    if [ -L "$1" ]; then
        echo "refusing to replace a symbolic link: $1" >&2
        exit 1
    fi
}

ensure_user_dir() {
    if [ -L "$1" ]; then
        echo "refusing a symbolic-link installation directory: $1" >&2
        exit 1
    fi
    if [ -e "$1" ] && [ ! -d "$1" ]; then
        echo "installation directory path is not a directory: $1" >&2
        exit 1
    fi
    if [ ! -d "$1" ]; then
        install -d -o "$USER_NAME" -m 0700 "$1"
    fi
}

for destination in "$DEST" "$CONFIG" "$LOG" "$RULE_DEST" "$SKILL_DEST"; do
    refuse_link "$destination"
done

install -d -o root -g "$ROOT_GROUP" -m 0755 "$DEST_DIR" "$CONFIG_DIR"
backup_if_different "$SCRIPT" "$DEST"
install -o root -g "$ROOT_GROUP" -m 0555 "$SCRIPT" "$DEST"
CONFIG_TEMP="$CONFIG_DIR/config.json.tmp.$$"
printf '{"host":"%s","profile":"level-1"}\n' "$CANVAS_HOST" > "$CONFIG_TEMP"
chown root:"$ROOT_GROUP" "$CONFIG_TEMP"
chmod 0644 "$CONFIG_TEMP"
if [ -f "$CONFIG" ] && ! cmp -s "$CONFIG_TEMP" "$CONFIG"; then
    cp -p "$CONFIG" "$CONFIG.bak-$STAMP"
    echo "backed up $CONFIG"
fi
mv -f "$CONFIG_TEMP" "$CONFIG"

ensure_user_dir "$LOG_DIR"
chown "$USER_NAME" "$LOG_DIR"
chmod 0700 "$LOG_DIR"
if [ ! -f "$LOG" ]; then
    install -o "$USER_NAME" -m 0600 /dev/null "$LOG"
fi
chown "$USER_NAME" "$LOG"
chmod 0600 "$LOG"

ensure_user_dir "$CODEX_DIR"
ensure_user_dir "$CODEX_DIR/rules"
ensure_user_dir "$CODEX_DIR/skills"
ensure_user_dir "$CODEX_DIR/skills/canvas-api-guard"
backup_if_different "$RULES" "$RULE_DEST"
backup_if_different "$SKILL" "$SKILL_DEST"
install -o "$USER_NAME" -m 0644 "$RULES" "$RULE_DEST"
install -o "$USER_NAME" -m 0644 "$SKILL" "$SKILL_DEST"

INSTALLED_SHA=$(hash_file "$DEST")
INSTALLED_RULES_SHA=$(hash_file "$RULE_DEST")
INSTALLED_SKILL_SHA=$(hash_file "$SKILL_DEST")
if [ "$INSTALLED_SHA" != "$SOURCE_SHA" ]; then
    echo "installed executable hash does not match the reviewed source" >&2
    exit 1
fi
if [ "$INSTALLED_RULES_SHA" != "$RULES_SHA" ]; then
    echo "installed rules hash does not match the reviewed source" >&2
    exit 1
fi
if [ "$INSTALLED_SKILL_SHA" != "$SKILL_SHA" ]; then
    echo "installed skill hash does not match the reviewed source" >&2
    exit 1
fi

cat <<EON
installed canvas-api-guard
  source:       $SOURCE_STATE
  guard sha:    $INSTALLED_SHA
  rules sha:    $INSTALLED_RULES_SHA
  skill sha:    $INSTALLED_SKILL_SHA
  executable:   $DEST
  config:       $CONFIG
  audit log:    $LOG
  Codex rules:  $RULE_DEST
  Codex skill:  $SKILL_DEST

No Canvas request was made and no token was read or stored.
Next, as $USER_NAME, use a visible terminal to run:
  $DEST --set-token

Then merge the reviewed settings in codex/config.toml into $CODEX_DIR/config.toml.
Optional hardening (not run automatically; each needs an administrative change to undo):
  sudo $IMMUTABLE $DEST
  sudo $APPEND_ONLY $LOG
EON
