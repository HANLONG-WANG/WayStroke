#!/usr/bin/env bash
# Run the exact RPM payload at its installed paths in a read-only mount namespace.
# The host /usr and user GNOME configuration are never changed.
set -euo pipefail
cd "$(dirname "$0")/.."
stroke_rpm=${1:-}
if [[ -z $stroke_rpm ]]; then
    read -r version arch < <(rpmspec -q --rpms --qf '%{VERSION} %{ARCH}\n' packaging/rpm/waystroke.spec)
    dist=$(rpm -E '%{?dist}')
    stroke_rpm=$(printf '%s\n' target/rpm/RPMS/"$arch"/waystroke-"$version"-*"$dist.$arch.rpm" | sort -V | tail -1)
fi
[[ -f $stroke_rpm ]] || { echo '找不到待验证的 RPM，请先构建或指定文件。' >&2; exit 1; }
stroke_stage=$(mktemp -d /tmp/waystroke-installed-rpm-XXXXXX)
trap 'rm -rf "$stroke_stage"' EXIT
rpm2cpio "$stroke_rpm" | (cd "$stroke_stage"; cpio -idm --quiet)
bwrap --die-with-parent --unshare-user --unshare-pid \
    --ro-bind / / --bind /tmp /tmp --dev /dev --proc /proc \
    --overlay-src /usr --overlay-src "$stroke_stage/usr" --ro-overlay /usr \
    --setenv WAYSTROKE_INSTALLED_NAMESPACE 1 \
    /usr/bin/python3 scripts/check-gnome.py --devkit --release --phase-f-installed
