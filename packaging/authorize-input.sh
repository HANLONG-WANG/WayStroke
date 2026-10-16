#!/usr/bin/bash
# Installed root-owned helper; no caller-selected paths, commands or identity.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID == 0 && $# == 0 && ${PKEXEC_UID:-} =~ ^[0-9]+$ && ${PKEXEC_UID} != 0 ]] || exit 1
getent passwd "$PKEXEC_UID" >/dev/null
[[ $(gnome-shell --version) == 'GNOME Shell 50.5' ]] || { echo '仅支持 GNOME Shell 50.5。' >&2; exit 1; }
[[ -x /usr/bin/waystroke-inputd ]] || exit 1
if [[ ! -c /dev/uinput ]]; then modprobe uinput; fi
# Stop the old probe before enabling the production transport.
if systemctl cat waystroke-input-probe.service >/dev/null 2>&1; then
    systemctl disable --now waystroke-input-probe.service
fi
systemctl stop waystroke-inputd.service
install -d -m 0755 -o root -g root /etc/waystroke
stroke_config=$(mktemp /etc/waystroke/.inputd.XXXXXX)
trap 'rm -f "$stroke_config"' EXIT
printf 'WAYSTROKE_INPUT_UID=%s\n' "$PKEXEC_UID" > "$stroke_config"
chmod 0600 "$stroke_config"
chown root:root "$stroke_config"
mv -f "$stroke_config" /etc/waystroke/inputd.conf
restorecon /etc/waystroke/inputd.conf
systemctl enable --now waystroke-inputd.service
printf '鼠标服务已授权，重启后会自动恢复；未选择设备时保持空闲。\n'
