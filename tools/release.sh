#!/bin/sh
# Release: point the release branch at main plus one commit that pins the bootstrap to
# main's head. Faculty fetch install-from-github.sh from the release branch, so that copy
# knows which reviewed commit to download without a --ref on the command line.
#
#   tools/release.sh            # release origin/main
#   tools/release.sh COMMIT     # release a specific commit that is on origin/main

set -eu
cd "$(dirname "$0")/.."

die() { printf 'release: %s\n' "$1" >&2; exit 1; }

[ -z "$(git status --porcelain --untracked-files=no)" ] || die "commit or stash tracked changes first"
git fetch --quiet origin
TARGET=$(git rev-parse --verify "${1:-origin/main}^{commit}") || die "no such commit: ${1:-origin/main}"
git merge-base --is-ancestor "$TARGET" origin/main || die "$TARGET is not on origin/main"
grep -q '^RELEASE_REF=' install-from-github.sh || die "install-from-github.sh has no RELEASE_REF line"

START=$(git rev-parse --abbrev-ref HEAD)
# Whatever fails below (a stale lease, a rejected push), come back to the starting branch;
# the local release branch is tool-made and is recreated from scratch on the next run.
trap 'git checkout --quiet "$START" 2>/dev/null || true' EXIT
git checkout --quiet -B release "$TARGET"
sed "s|^RELEASE_REF=.*|RELEASE_REF=$TARGET   # pinned by tools/release.sh|" install-from-github.sh > install-from-github.sh.pin
cat install-from-github.sh.pin > install-from-github.sh
rm -f install-from-github.sh.pin
sh -n install-from-github.sh
# RELEASE.md rides in the pin commit: what is released and what changed since the previous
# release, at a fixed public address Codex can read to tell a person an update is waiting.
PREVIOUS=$(git rev-parse --quiet --verify "origin/release~1^{commit}" 2>/dev/null || true)
{
    printf '# canvas-api-guard release\n\nCommit: %s\nDate: %s\n\nInstall or update: paste into Terminal\n\n' \
        "$TARGET" "$(date -u +%Y-%m-%d)"
    printf '    curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/release/install-from-github.sh | sh\n\n'
    printf '## Changes since the previous release\n\n'
    if [ -n "$PREVIOUS" ]; then git log --format='- %s' "$PREVIOUS..$TARGET"; else echo "- first release"; fi
} > RELEASE.md
git add RELEASE.md
git commit --quiet -m "release: pin the bootstrap to $TARGET" install-from-github.sh RELEASE.md
git push --quiet --force-with-lease origin release
printf 'release -> %s (main %s + pin commit)\n' "$(git rev-parse --short release)" "$(git rev-parse --short "$TARGET")"
