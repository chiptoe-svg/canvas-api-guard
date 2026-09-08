#!/bin/sh
# Reviewable Codex-led installer. It performs no authentication and makes no network calls.
#
#   ./install.sh --plan --host school.instructure.com
#   sudo ./install.sh --host school.instructure.com

set -eu

usage() {
    text="usage: $0 [--plan] [--allow-dirty] [--profile api-only|specialized-functions] --host school.instructure.com
  --plan compares every installed file with the reviewed source (SHA-256; owner and mode for
  root-owned files) and changes nothing.
  It exits 0 when installing would change a file and 3 when nothing needs to change."
    if [ "${1:-2}" = 1 ]; then
        echo "$text"
        exit 0
    fi
    echo "$text" >&2
    exit 2
}

PLAN=no
ALLOW_DIRTY=no
CANVAS_HOST=
PROFILE=level-1                         # stable on-disk compatibility key
PROFILE_LABEL="API Only"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) PLAN=yes ;;
        --allow-dirty) ALLOW_DIRTY=yes ;;
        --profile) shift; [ "$#" -gt 0 ] || usage; PROFILE=$1 ;;
        --host) shift; [ "$#" -gt 0 ] || usage; CANVAS_HOST=$1 ;;
        -h|--help) usage 1 ;;
        *) usage ;;
    esac
    shift
done

case "$PROFILE" in
    api-only|level-1) PROFILE=level-1; PROFILE_LABEL="API Only" ;;
    specialized-functions|level-2) PROFILE=level-2; PROFILE_LABEL="Specialized Functions" ;;
    *) echo "invalid profile: $PROFILE (expected api-only or specialized-functions)" >&2; exit 2 ;;
esac

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
LEVEL2_SCRIPT="$SRC_DIR/level2/canvas_api_operations.py"
LEVEL2_SKILL="$SRC_DIR/level2/SKILL.md"
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
if [ "$PROFILE" = level-2 ]; then
    for required in "$LEVEL2_SCRIPT" "$LEVEL2_SKILL"; do
        if [ ! -f "$required" ]; then
            echo "cannot find required Specialized Functions source file: $required" >&2
            exit 1
        fi
    done
fi

case "$(uname -s)" in
    Darwin)
        ROOT_GROUP=wheel
        IMMUTABLE="chflags schg"
        APPEND_ONLY="chflags sappnd"
        hash_file() { shasum -a 256 "$1" | awk '{print $1}'; }
        hash_stdin() { shasum -a 256 | awk '{print $1}'; }
        stat_uid() { stat -f '%u' "$1"; }
        stat_owner() { stat -f '%Su' "$1"; }
        stat_perm() { stat -f '%Sp' "$1"; }
        ;;
    Linux)
        ROOT_GROUP=root
        IMMUTABLE="chattr +i"
        APPEND_ONLY="chattr +a"
        hash_file() { sha256sum "$1" | awk '{print $1}'; }
        hash_stdin() { sha256sum | awk '{print $1}'; }
        stat_uid() { stat -c '%u' "$1"; }
        stat_owner() { stat -c '%U' "$1"; }
        stat_perm() { stat -c '%A' "$1"; }
        ;;
    *)
        echo "unsupported platform $(uname -s): macOS and Linux only" >&2
        exit 1
        ;;
esac

# Every ancestor of an installation path must be root-owned, not a symlink, and not
# writable by group or other -- otherwise the guard's own provenance check (which demands
# exactly this of its installed path) would fail closed after a successful install, with a
# confusing message. Checked before the plan is printed and before any change is made, so a
# reviewer sees the result under --plan too.
#
# A chown/chmod remedy is only offered for the destination directory itself: an ancestor
# above it (e.g. /usr/local on an Intel Homebrew Mac, owned by the console user) may be
# owned or managed by something else entirely, and "sudo chown" on it would be destructive
# advice, not a fix. For an ancestor, this refuses with an explanation instead of a remedy.
check_ancestor_ownership() {
    target=$1
    path=$1
    while :; do
        if [ -e "$path" ] || [ -L "$path" ]; then
            CHECKED=$((CHECKED + 1))
            if [ -L "$path" ]; then
                echo "refusing: $path is a symbolic link in the installation path" >&2
                echo "  remedy: replace it with a real, root-owned directory" >&2
                exit 1
            fi
            if [ "$(stat_uid "$path")" != 0 ]; then
                if [ "$path" = "$target" ]; then
                    echo "refusing: $path is not owned by root" >&2
                    echo "  remedy: sudo chown root:$ROOT_GROUP $path" >&2
                else
                    echo "refusing: $path is owned by $(stat_owner "$path"); the guard cannot be" >&2
                    echo "  installed under a prefix a non-root user can write. This may be the" >&2
                    echo "  Homebrew-on-Intel layout; installing the guard here needs a root-owned" >&2
                    echo "  prefix, which this installer does not provide." >&2
                fi
                exit 1
            fi
            case "$(stat_perm "$path")" in
                ?????w????|????????w?)
                    if [ "$path" = "$target" ]; then
                        echo "refusing: $path is writable by group or other" >&2
                        echo "  remedy: sudo chmod 755 $path" >&2
                    else
                        echo "refusing: $path is writable by group or other; the guard cannot be" >&2
                        echo "  installed under a prefix that is not exclusively root-writable, and" >&2
                        echo "  this installer does not change permissions above $target." >&2
                    fi
                    exit 1
                    ;;
            esac
        fi
        [ "$path" = / ] && break
        parent=$(dirname "$path")
        [ "$parent" = "$path" ] && break
        path=$parent
    done
}

SOURCE_SHA=$(hash_file "$SCRIPT")
RULES_SHA=$(hash_file "$RULES")
SKILL_SHA=$(hash_file "$SKILL")
LEVEL2_SCRIPT_SHA=
LEVEL2_SKILL_SHA=
if [ "$PROFILE" = level-2 ]; then
    LEVEL2_SCRIPT_SHA=$(hash_file "$LEVEL2_SCRIPT")
    LEVEL2_SKILL_SHA=$(hash_file "$LEVEL2_SKILL")
fi

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
LEVEL2_DEST="$DEST_DIR/canvas_api_operations.py"
LEVEL2_SKILL_DEST="$CODEX_DIR/skills/canvas-api-operations/SKILL.md"

root_owned_and_private() {              # what the guard's own provenance check demands
    [ "$(stat_uid "$1")" = 0 ] || return 1
    case "$(stat_perm "$1")" in ?????w????|????????w?) return 1 ;; esac
}

# Whether an installed file already matches the reviewed source: same, differs, missing, link,
# or perms. [same] compares SHA-256 and, for root-owned destinations, owner and mode too, so
# it means "installed correctly". A link is refused, not replaced, by the privileged step.
file_state() {
    if [ -L "$1" ]; then echo link
    elif [ ! -f "$1" ]; then echo missing
    elif [ "$(hash_file "$1")" != "$2" ]; then echo differs
    elif [ "$3" = root ] && ! root_owned_and_private "$1"; then echo perms
    else echo same
    fi
}

CONFIG_TEXT=$(printf '{"host":"%s","profile":"%s"}' "$CANVAS_HOST" "$PROFILE")
CONFIG_SHA=$(printf '%s\n' "$CONFIG_TEXT" | hash_stdin)
DEST_STATE=$(file_state "$DEST" "$SOURCE_SHA" root)
CONFIG_STATE=$(file_state "$CONFIG" "$CONFIG_SHA" root)
RULES_STATE=$(file_state "$RULE_DEST" "$RULES_SHA" user)
SKILL_STATE=$(file_state "$SKILL_DEST" "$SKILL_SHA" user)
STATES="$DEST_STATE $CONFIG_STATE $RULES_STATE $SKILL_STATE"
if [ "$PROFILE" = level-2 ]; then
    LEVEL2_STATE=$(file_state "$LEVEL2_DEST" "$LEVEL2_SCRIPT_SHA" root)
    LEVEL2_SKILL_STATE=$(file_state "$LEVEL2_SKILL_DEST" "$LEVEL2_SKILL_SHA" user)
    STATES="$STATES $LEVEL2_STATE $LEVEL2_SKILL_STATE"
fi
UP_TO_DATE=yes
for state in $STATES; do
    [ "$state" = same ] || UP_TO_DATE=no
done

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

CHECKED=0
check_ancestor_ownership "$DEST_DIR"
check_ancestor_ownership "$CONFIG_DIR"

if [ "$PLAN" = yes ]; then
    cat <<EOP
canvas-api-guard installation plan (no changes made)
  source:       $SOURCE_STATE
  guard sha:    $SOURCE_SHA
  rules sha:    $RULES_SHA
  skill sha:    $SKILL_SHA
  ancestor check: $CHECKED components checked; existing ancestors of $DEST_DIR and
                  $CONFIG_DIR are root-owned, not links, not group/other-writable;
                  missing components will be created root-owned
  Canvas host:  $CANVAS_HOST
  executable:   $DEST (root:$ROOT_GROUP, 0555) [$DEST_STATE]
  config:       $CONFIG (root:$ROOT_GROUP, 0644; profile $PROFILE_LABEL; compatibility key $PROFILE) [$CONFIG_STATE]
  audit log:    $LOG ($USER_NAME, 0600; containing confidential education records; kept)
  Codex rules:  $RULE_DEST ($USER_NAME, 0644) [$RULES_STATE]
  Codex skill:  $SKILL_DEST ($USER_NAME, 0644) [$SKILL_STATE]
EOP
    if [ "$PROFILE" = level-2 ]; then
        cat <<EOP
  Specialized Functions executable: $LEVEL2_DEST (root:$ROOT_GROUP, 0555) [$LEVEL2_STATE]
  Specialized Functions skill:      $LEVEL2_SKILL_DEST ($USER_NAME, 0644) [$LEVEL2_SKILL_STATE]
  Specialized Functions sha:        $LEVEL2_SCRIPT_SHA
  Specialized Functions skill sha:  $LEVEL2_SKILL_SHA
EOP
    fi
    if [ "$UP_TO_DATE" = yes ]; then
        echo
        echo "Nothing to do: every installed file already matches this source (exit status 3)."
        exit 3
    fi
    cat <<EOP

[state] compares the installed file's SHA-256 with the reviewed source, plus owner and mode for
root-owned files; only files that are not [same] will be replaced, and a [link] is refused.
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
if [ "$PROFILE" = level-2 ]; then
    refuse_link "$LEVEL2_DEST"
    refuse_link "$LEVEL2_SKILL_DEST"
fi

install -d -o root -g "$ROOT_GROUP" -m 0755 "$DEST_DIR" "$CONFIG_DIR"
backup_if_different "$SCRIPT" "$DEST"
install -o root -g "$ROOT_GROUP" -m 0555 "$SCRIPT" "$DEST"
CONFIG_TEMP="$CONFIG_DIR/config.json.tmp.$$"
printf '%s\n' "$CONFIG_TEXT" > "$CONFIG_TEMP"
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
if [ "$PROFILE" = level-2 ]; then
    ensure_user_dir "$CODEX_DIR/skills/canvas-api-operations"
    backup_if_different "$LEVEL2_SCRIPT" "$LEVEL2_DEST"
    backup_if_different "$LEVEL2_SKILL" "$LEVEL2_SKILL_DEST"
    install -o root -g "$ROOT_GROUP" -m 0555 "$LEVEL2_SCRIPT" "$LEVEL2_DEST"
    install -o "$USER_NAME" -m 0644 "$LEVEL2_SKILL" "$LEVEL2_SKILL_DEST"
fi

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
if [ "$PROFILE" = level-2 ]; then
    if [ "$(hash_file "$LEVEL2_DEST")" != "$LEVEL2_SCRIPT_SHA" ]; then
        echo "installed Specialized Functions executable hash does not match the reviewed source" >&2
        exit 1
    fi
    if [ "$(hash_file "$LEVEL2_SKILL_DEST")" != "$LEVEL2_SKILL_SHA" ]; then
        echo "installed Specialized Functions skill hash does not match the reviewed source" >&2
        exit 1
    fi
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
EON
if [ "$PROFILE" = level-2 ]; then
    cat <<EON
  Specialized Functions executable: $LEVEL2_DEST
  Specialized Functions skill:      $LEVEL2_SKILL_DEST
EON
fi
cat <<EON

No Canvas request was made and no token was read or stored.
Next, as $USER_NAME, use a visible terminal to run:
  $DEST --set-token

Then merge the reviewed settings in codex/config.toml into $CODEX_DIR/config.toml.
Optional hardening (not run automatically; each needs an administrative change to undo):
  sudo $IMMUTABLE $DEST
  sudo $APPEND_ONLY $LOG
EON
