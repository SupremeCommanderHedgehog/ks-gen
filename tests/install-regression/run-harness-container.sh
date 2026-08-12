#!/usr/bin/env bash
# Launcher: run the install-regression harness against the container-users
# fixture (validates the fix/rootless-linger-chroot %post linger fix).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$HERE"
export FIXTURE_TEMPLATE="$HERE/fixtures/container-users.host.yaml.tmpl"
# 600s default is too tight — the silent oscap/AIDE %post + idle-at-login
# tripped a false "anaconda hung" abort before the smoke-check ran.
export STAGNATION_BUDGET=1800
echo "=== FIXTURE_TEMPLATE=$FIXTURE_TEMPLATE ==="
ls -l "$FIXTURE_TEMPLATE" || { echo "fixture missing"; exit 1; }
echo "=== fix present in embedded script? ==="
grep -c 'if ! loginctl enable-linger' "$REPO/src/ks_gen/assets/create-rootless-user.sh"
echo "=== launching run.sh ==="
exec bash "$HERE/run.sh"
