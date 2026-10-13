#!/usr/bin/bash
# Development installation only. No boot enablement and no input-group access.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $EUID != 0 ]]; then
    printf '请使用 sudo 运行开发安装脚本。\n' >&2
    exit 1
fi
if [[ $# == 1 && $1 == --uninstall ]]; then
    systemctl disable --now waystroke-inputd.service
    rm -f /etc/systemd/system/waystroke-inputd.service /etc/waystroke/inputd.conf /usr/local/libexec/waystroke-inputd
    systemctl daemon-reload
    printf '开发鼠标服务已卸载，用户配置保留。\n'
    exit 0
fi
if [[ $# != 2 || $1 != --user ]]; then
    printf '用法：sudo bash %s --user 用户名\n      sudo bash %s --uninstall\n' "$0" "$0" >&2
    exit 1
fi
stroke_uid=$(id -u -- "$2")
if [[ $stroke_uid == 0 ]]; then
    printf '必须指定普通桌面用户。\n' >&2
    exit 1
fi
if [[ $(gnome-shell --version) != 'GNOME Shell 50.5' ]]; then
    printf '当前开发版本仅适配 GNOME Shell 50.5。\n' >&2
    exit 1
fi
if [[ ! -x "$repo/target/debug/waystroke-inputd" ]]; then
    printf '请先以普通用户运行 cargo build -p waystroke-inputd。\n' >&2
    exit 1
fi
command -v udevadm >/dev/null
if [[ ! -c /dev/uinput ]]; then modprobe uinput; fi
if systemctl cat waystroke-inputd.service >/dev/null 2>&1; then
    systemctl stop waystroke-inputd.service
fi
install -d -o root -g root -m 0755 /usr/local/libexec /etc/waystroke
install -o root -g root -m 0755 "$repo/target/debug/waystroke-inputd" /usr/local/libexec/waystroke-inputd
install -o root -g root -m 0644 "$repo/packaging/systemd/waystroke-inputd.service" /etc/systemd/system/waystroke-inputd.service
printf 'WAYSTROKE_INPUT_UID=%s\n' "$stroke_uid" > /etc/waystroke/inputd.conf
chown root:root /etc/waystroke/inputd.conf
chmod 0600 /etc/waystroke/inputd.conf
restorecon /usr/local/libexec/waystroke-inputd /etc/waystroke/inputd.conf /etc/systemd/system/waystroke-inputd.service
systemctl daemon-reload
systemctl start waystroke-inputd.service
printf '已安装空闲开发服务；未接管鼠标，未设置开机启动，未修改 input 组。\n'
