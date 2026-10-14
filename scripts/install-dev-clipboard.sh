#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$(id -u)" != 0 ]]; then echo '请用 sudo 运行此脚本，安装 GNOME 剪贴板原生组件。' >&2; exit 1; fi
if [[ "${1:-}" == --uninstall ]]; then
    rm -f /usr/lib64/libwaystroke-clipboard.so /usr/lib64/girepository-1.0/WayStrokeClipboard-1.0.typelib
    echo '已移除 WayStroke 剪贴板原生组件；用户配置保留。';exit 0
fi
[[ $# == 0 ]] || { echo '用法：install-dev-clipboard.sh [--uninstall]' >&2; exit 1; }
[[ "$(gnome-shell --version)" == 'GNOME Shell 50.5' ]] || { echo '仅适配 GNOME Shell 50.5。' >&2; exit 1; }
[[ -f "$repo_dir/target/native/libwaystroke-clipboard.so" && -f "$repo_dir/target/native/WayStrokeClipboard-1.0.typelib" ]] || { echo '请先运行 scripts/build-clipboard-native.sh。' >&2; exit 1; }
install -m 755 "$repo_dir/target/native/libwaystroke-clipboard.so" /usr/lib64/libwaystroke-clipboard.so
install -m 644 "$repo_dir/target/native/WayStrokeClipboard-1.0.typelib" /usr/lib64/girepository-1.0/WayStrokeClipboard-1.0.typelib
if command -v restorecon >/dev/null; then restorecon -F /usr/lib64/libwaystroke-clipboard.so /usr/lib64/girepository-1.0/WayStrokeClipboard-1.0.typelib; fi
echo '已安装 WayStroke 多格式剪贴板组件。首次安装可按需加载；组件代码更新需新 GNOME 会话。'
