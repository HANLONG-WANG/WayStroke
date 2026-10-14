#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
extension_id=waystroke@local
extension_dir="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$extension_id"
if [[ "$(id -u)" == 0 ]]; then
  echo '请使用桌面用户运行此脚本，不要使用 sudo。' >&2
  exit 1
fi
if [[ "${1:-}" == --uninstall ]]; then
  gnome-extensions disable "$extension_id" 2>/dev/null || true
  python3 - <<'PYTHON'
from gi.repository import Gio
settings=Gio.Settings.new('org.gnome.shell')
settings.set_strv('enabled-extensions',[uuid for uuid in settings.get_strv('enabled-extensions') if uuid!='waystroke@local'])
Gio.Settings.sync()
PYTHON
  rm -f "$extension_dir/extension.js" "$extension_dir/metadata.json" "$extension_dir/clipboard.js" "$extension_dir/dialogs.js" "$extension_dir/system.js" "$extension_dir/text.js" "$extension_dir/terminal.js"
  rmdir "$extension_dir" 2>/dev/null || true
  echo '已移除 WayStroke 开发扩展；用户配置保留。'
  exit 0
fi
if [[ $# != 0 ]]; then echo '用法：install-dev-extension.sh [--uninstall]' >&2; exit 1; fi
[[ "$(gnome-shell --version)" == 'GNOME Shell 50.5' ]] || { echo '仅适配 GNOME Shell 50.5。' >&2; exit 1; }
mkdir -p "$extension_dir"
install -m 644 "$repo_dir/extension/metadata.json" "$repo_dir/extension/extension.js" "$repo_dir/extension/clipboard.js" "$repo_dir/extension/dialogs.js" "$repo_dir/extension/system.js" "$repo_dir/extension/text.js" "$repo_dir/extension/terminal.js" "$extension_dir/"
python3 - <<'PY'
from gi.repository import Gio
settings=Gio.Settings.new('org.gnome.shell')
extensions=list(settings.get_strv('enabled-extensions'))
if 'waystroke@local' not in extensions:
    settings.set_strv('enabled-extensions',extensions+['waystroke@local'])
Gio.Settings.sync()
if settings.get_boolean('disable-user-extensions'):
    print('当前全局禁用了用户扩展，请在扩展应用中开启用户扩展。')
PY
if gnome-extensions info "$extension_id" >/dev/null 2>&1; then
  gnome-extensions disable "$extension_id"
  gnome-extensions enable "$extension_id"
  echo '文件已更新并重新开启 WayStroke 开发扩展。当前 GNOME 会缓存已导入代码；代码更新需要新桌面会话才会载入。'
else
  echo '已安装 WayStroke 开发扩展；请在扩展应用中开启。若 GNOME 尚未发现首次安装的扩展，再重新登录。'
fi
printf '扩展本身不会接管鼠标；仍需在 WayStroke 中选择设备并完成接入。\n'
