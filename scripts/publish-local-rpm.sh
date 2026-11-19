#!/usr/bin/env bash
set -euo pipefail
repo_template="$(dirname "$0")/../packaging/rpm/waystroke-local.repo"
repo_root=/var/lib/waystroke-rpms
repo_config=/etc/yum.repos.d/waystroke-local.repo
enable=false
if [[ ${1:-} == --enable ]]; then enable=true; shift; fi
if [[ $EUID != 0 || $# == 0 ]]; then
    echo '用法：sudo bash scripts/publish-local-rpm.sh [--enable] WayStroke.rpm ...' >&2
    exit 1
fi
command -v createrepo_c >/dev/null || { echo '请先运行 sudo dnf install createrepo_c。' >&2; exit 1; }
if [[ $enable == false && ! -f $repo_config ]]; then
    echo '本地仓库尚未启用，请先使用 --enable。' >&2
    exit 1
fi
install -d -m 0755 "$repo_root"
exec 9>"$repo_root/.publish.lock"
flock 9
for package in "$@"; do
    header=$(rpm -qp --qf '%{NAME} %{VERSION} %{RELEASE} %{ARCH}' "$package")
    read -r name version release arch <<< "$header"
    if [[ $name != waystroke || $arch != x86_64 || ! $release =~ ^[0-9]+\.fc([0-9]+)$ ]]; then
        echo "无法发布此 RPM：$header" >&2
        exit 1
    fi
    dir="$repo_root/${BASH_REMATCH[1]}/$arch"
    dest="$dir/$name-$version-$release.$arch.rpm"
    install -d -m 0755 "$dir"
    if [[ -f $dest ]]; then
        cmp -s -- "$package" "$dest" || { echo "同一版本已发布不同内容：$dest" >&2; exit 1; }
    else
        install -m 0644 -- "$package" "$dest.tmp"
        mv -fT -- "$dest.tmp" "$dest"
    fi
    createrepo_c --quiet --update "$dir"
    echo "已发布 $dest"
done
if [[ $enable == true ]]; then
    install -m 0644 "$repo_template" "$repo_config"
    echo "已启用 $repo_config"
fi
