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
git commit --quiet -m "release: pin the bootstrap to $TARGET" install-from-github.sh
git push --quiet --force-with-lease origin release
printf 'release -> %s (main %s + pin commit)\n' "$(git rev-parse --short release)" "$(git rev-parse --short "$TARGET")"
