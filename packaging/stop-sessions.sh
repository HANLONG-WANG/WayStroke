#!/usr/bin/bash
# RPM lifecycle helper. User configuration and backups are never removed.
set -u
for stroke_runtime in /run/user/[0-9]*; do
    [[ -d $stroke_runtime ]] || continue
    stroke_uid=${stroke_runtime##*/}
    stroke_user=$(getent passwd "$stroke_uid" | cut -d: -f1)
    [[ -n $stroke_user ]] || continue
    stroke_env=(/usr/sbin/runuser -u "$stroke_user" -- /usr/bin/env "XDG_RUNTIME_DIR=$stroke_runtime" "DBUS_SESSION_BUS_ADDRESS=unix:path=$stroke_runtime/bus")
    "${stroke_env[@]}" busctl --user --auto-start=no call io.github.waystroke.Core /io/github/waystroke/Core io.github.waystroke.Core1 Quit >/dev/null 2>&1 || :
    "${stroke_env[@]}" systemctl --user stop waystroke-core.service >/dev/null 2>&1 || :
    if [[ ${1:-} == --uninstall ]]; then
        "${stroke_env[@]}" gnome-extensions disable waystroke@local >/dev/null 2>&1 || :
    fi
    "${stroke_env[@]}" systemctl --user daemon-reload >/dev/null 2>&1 || :
done
# Stop only the packaged settings executable, never unrelated development instances.
python3 - <<'PYTHON'
import os, signal
from pathlib import Path
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        if os.readlink(entry/'exe') in ('/usr/bin/waystroke', '/usr/bin/waystroke (deleted)'):
            os.kill(int(entry.name), signal.SIGTERM)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
PYTHON
