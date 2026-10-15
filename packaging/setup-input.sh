#!/usr/bin/bash
# Invoked by the desktop via pkexec. Never accepts a caller-selected UID or command.
set -euo pipefail
payload=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
stroke_uid=${PKEXEC_UID:-}
[[ $stroke_uid =~ ^[0-9]+$ && $stroke_uid != 0 ]] || { echo '缺少管理员授权的桌面用户身份。' >&2; exit 1; }
getent passwd "$stroke_uid" >/dev/null || { echo '授权用户不存在或无法读取用户账户。' >&2; exit 1; }
stage=''
if [[ $EUID != 0 ]]; then
    # Unprivileged integration fixture: root execution cannot redirect system paths.
    [[ $stroke_uid == "$EUID" && ${WAYSTROKE_SETUP_TEST_ROOT:-} == /* ]] || { echo '需要管理员授权。' >&2; exit 1; }
    stage=$WAYSTROKE_SETUP_TEST_ROOT
elif [[ -n ${WAYSTROKE_SETUP_TEST_ROOT:-} ]]; then
    echo '管理员安装不接受测试目录。' >&2; exit 1
fi
[[ -x "$payload/waystroke-inputd" && -s "$payload/waystroke-inputd.service" ]] || { echo '鼠标服务安装资源不完整。' >&2; exit 1; }
if [[ -z $stage ]]; then
    export PATH=/usr/sbin:/usr/bin:/sbin:/bin
    [[ $(gnome-shell --version) == 'GNOME Shell 50.5' ]] || { echo '仅支持 GNOME Shell 50.5。' >&2; exit 1; }
    command -v restorecon >/dev/null
    command -v udevadm >/dev/null
    if [[ ! -c /dev/uinput ]]; then modprobe uinput; fi
    if systemctl cat waystroke-inputd.service >/dev/null 2>&1; then systemctl stop waystroke-inputd.service; fi
fi
install -d -m 0755 "$stage/usr/local/libexec" "$stage/etc/waystroke" "$stage/etc/systemd/system"
install -m 0755 "$payload/waystroke-inputd" "$stage/usr/local/libexec/waystroke-inputd"
install -m 0644 "$payload/waystroke-inputd.service" "$stage/etc/systemd/system/waystroke-inputd.service"
printf 'WAYSTROKE_INPUT_UID=%s\n' "$stroke_uid" > "$stage/etc/waystroke/inputd.conf"
chmod 0600 "$stage/etc/waystroke/inputd.conf"
if [[ -z $stage ]]; then
    chown root:root /usr/local/libexec/waystroke-inputd /etc/waystroke/inputd.conf /etc/systemd/system/waystroke-inputd.service
    restorecon /usr/local/libexec/waystroke-inputd /etc/waystroke/inputd.conf /etc/systemd/system/waystroke-inputd.service
    systemctl daemon-reload
    systemctl start waystroke-inputd.service
fi
printf '鼠标服务已安装并授权；服务保持空闲，不设置开机启动，不接管未选择的设备。\n'
