#!/usr/bin/bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
unit=waystroke-input-probe.service
install_dir=/usr/local/lib/waystroke-input-probe

if [[ $EUID != 0 ]]; then
    printf '请通过 sudo 运行此安装/卸载脚本。\n' >&2
    exit 1
fi

if [[ ${1:-} == --uninstall && $# == 1 ]]; then
    systemctl disable --now "$unit"
    rm -f /etc/systemd/system/waystroke-input-probe.service /etc/waystroke-input-probe.conf
    rm -f "$install_dir/daemon.py" "$install_dir/routing.py" "$install_dir/client.py"
    rmdir "$install_dir"
    systemctl daemon-reload
    printf '验证服务已卸载；python3-evdev 包保留。\n'
    exit 0
fi

if [[ $# != 2 || $1 != --user ]]; then
    printf '用法：sudo bash %s --user 用户名\n      sudo bash %s --uninstall\n' "$0" "$0" >&2
    exit 1
fi
probe_user=$2
probe_uid=$(id -u -- "$probe_user")
if [[ $probe_uid == 0 ]]; then
    printf '请选择实际使用 GNOME 的普通用户。\n' >&2
    exit 1
fi
if [[ $(gnome-shell --version) != 'GNOME Shell 50.5' ]]; then
    printf '本轮只验证 GNOME Shell 50.5。当前版本不同，停止安装。\n' >&2
    exit 1
fi
# Use Fedora's binary package rather than installing Python packages as root via pip.
if ! /usr/bin/python3 -c 'import evdev' >/dev/null 2>&1; then
    dnf install -y --disablerepo='*' --enablerepo=fedora --enablerepo=updates python3-evdev
fi
if [[ ! -c /dev/uinput ]]; then
    modprobe uinput
fi
/usr/bin/python3 -c 'import evdev'

if systemctl is-active --quiet "$unit"; then
    systemctl stop "$unit"
fi
install -d -o root -g root -m 0755 "$install_dir"
for name in daemon.py routing.py client.py; do
    install -o root -g root -m 0644 "$source_dir/$name" "$install_dir/$name"
done
install -o root -g root -m 0644 "$source_dir/$unit" "/etc/systemd/system/$unit"
printf 'WAYSTROKE_PROBE_UID=%s\n' "$probe_uid" > /etc/waystroke-input-probe.conf
chown root:root /etc/waystroke-input-probe.conf
chmod 0600 /etc/waystroke-input-probe.conf
restorecon -RF "$install_dir" /etc/systemd/system/waystroke-input-probe.service /etc/waystroke-input-probe.conf
systemctl daemon-reload
systemctl start "$unit"
printf '已为 %s 安装验证服务。默认空闲，未接管鼠标；不会设置开机启动。\n' "$probe_user"
printf '列出鼠标：python3 %s/client.py devices\n' "$install_dir"
printf '验证示例：python3 %s/client.py watch /dev/input/eventN --seconds 60\n' "$install_dir"
printf '卸载：sudo bash %s/install.sh --uninstall\n' "$source_dir"
