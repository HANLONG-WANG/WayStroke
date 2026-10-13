#!/usr/bin/bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $EUID != 0 || $# != 2 || $1 != --user ]]; then
    printf '用法：sudo bash %s --user 用户名\n' "$0" >&2
    exit 1
fi
if [[ $(gnome-shell --version) != 'GNOME Shell 50.5' ]]; then
    printf '本轮只验证 GNOME Shell 50.5。\n' >&2
    exit 1
fi
id -u -- "$2" >/dev/null
if [[ ! -x /usr/libexec/mutter-devkit ]]; then
    dnf install -y --disablerepo='*' --enablerepo=fedora --enablerepo=updates mutter-devkit
fi
bash "$source_dir/../input/install.sh" --user "$2"
printf '起点窗口联动工具已准备好。服务空闲；解锁后以普通用户运行 binding.py。\n'
