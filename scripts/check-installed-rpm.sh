#!/usr/bin/env bash
# Run the exact RPM payload at its installed paths in a read-only mount namespace.
# The host /usr and user GNOME configuration are never changed.
set -euo pipefail
cd "$(dirname "$0")/.."
stroke_rpm=${1:-target/rpm/RPMS/x86_64/waystroke-0.1.0-2.fc44.x86_64.rpm}
stroke_stage=$(mktemp -d /tmp/waystroke-installed-rpm-XXXXXX)
trap 'rm -rf "$stroke_stage"' EXIT
rpm2cpio "$stroke_rpm" | (cd "$stroke_stage"; cpio -idm --quiet)
bwrap --die-with-parent --unshare-user --unshare-pid \
    --ro-bind / / --bind /tmp /tmp --dev /dev --proc /proc \
    --overlay-src "$stroke_stage/usr" --overlay-src /usr --ro-overlay /usr \
    --setenv WAYSTROKE_INSTALLED_NAMESPACE 1 \
    /usr/bin/python3 scripts/check-gnome.py --devkit --release --phase-f-installed
