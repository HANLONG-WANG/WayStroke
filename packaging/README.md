# Fedora 44 / GNOME 50.5

Build with `bash scripts/build-rpm.sh`. The release binaries and native clipboard
library are built first; the RPM contains these same verified artifacts. Output:
`target/rpm/RPMS/x86_64/waystroke-0.1.0-2.fc44.x86_64.rpm`.

Install using `sudo dnf install ./target/rpm/RPMS/x86_64/waystroke-0.1.0-2.fc44.x86_64.rpm`.
Open WayStroke from Applications. Installation does not enable login startup,
start the mouse service, grant input-group membership or select a mouse.
The setup wizard enables the GNOME extension and requests administrator
permission only for the fixed mouse-service authorization helper. Cancellation
can be retried. Configuration editing works without either connection.

First GNOME discovery of the extension, or an extension/native library upgrade,
needs a new GNOME session because GNOME caches imported modules. Save other work
before logging out. Development checks use a separate mutter-devkit session.
If a development copy exists in `~/.local/share/gnome-shell/extensions/waystroke@local`,
remove it with `scripts/install-dev-extension.sh --uninstall` before starting the
new session so it does not shadow the packaged extension.

The session bus activates `waystroke-core.service` on demand. The login-startup
preference writes an XDG autostart entry only after setup is completed; disabling
it removes that entry. Closing settings leaves core running. “退出 WayStroke”
stops core and releases its inputs. After explicit mouse authorization, the system service starts idle at boot so
login startup also works after a system restart. It captures no device without
an authorized core selecting it. Closing or quitting settings leaves this service idle.
A production input service conflicts with the old `waystroke-input-probe.service`;
authorization stops and disables that probe before starting production input.
The known development inputd unit is migrated when installing the RPM.

Save settings drafts before upgrading or uninstalling. RPM lifecycle hooks stop
the packaged settings/core and mouse service. Upgrade preserves mouse authorization
and starts the authorized service idle. Uninstall disables the extension and
removes package files and mouse authorization, while retaining user configuration,
backups and login preference. The retained login entry has `TryExec`, so it does
not launch after removal; reinstall can restore the saved preference.

Development builds retain their existing `scripts/install-dev-*.sh` entry points.
Do not run the probe and production input transport together. None of the formal
executables depend on the probe installation.
