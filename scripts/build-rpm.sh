#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} != --skip-build ]]; then
    bash scripts/build-clipboard-native.sh
    npm run build --prefix apps/desktop
fi
rpm_work="$PWD/target/rpm"
payload="$rpm_work/payload"
rm -rf "$payload"
mkdir -p "$payload/usr/bin" "$payload/usr/libexec/waystroke" "$payload/usr/lib/systemd/"{system,user} "$payload/usr/share/"{applications,dbus-1/services,polkit-1/actions,icons/hicolor/64x64/apps,icons/hicolor/scalable/apps,gnome-shell/extensions/waystroke@local} "$payload/usr/lib64/girepository-1.0"
for binary in waystroke waystroke-core waystroke-inputd; do
    install -m 0755 "target/release/$binary" "$payload/usr/bin/$binary"
done
install -m 0755 packaging/authorize-input.sh "$payload/usr/libexec/waystroke/authorize-input"
install -m 0755 packaging/stop-sessions.sh "$payload/usr/libexec/waystroke/stop-sessions"
install -m 0644 packaging/systemd/waystroke-inputd.service "$payload/usr/lib/systemd/system/"
install -m 0644 packaging/systemd/waystroke-core.service "$payload/usr/lib/systemd/user/"
install -m 0644 packaging/polkit/*.policy "$payload/usr/share/polkit-1/actions/"
install -m 0644 packaging/dbus/*.service "$payload/usr/share/dbus-1/services/"
install -m 0644 packaging/applications/*.desktop "$payload/usr/share/applications/"
install -m 0644 apps/desktop/src-tauri/icons/icon.svg "$payload/usr/share/icons/hicolor/scalable/apps/io.github.waystroke.Desktop.svg"
install -m 0644 apps/desktop/src-tauri/icons/icon.png "$payload/usr/share/icons/hicolor/64x64/apps/io.github.waystroke.Desktop.png"
for resource in metadata.json extension.js clipboard.js dialogs.js system.js text.js terminal.js; do
    install -m 0644 "extension/$resource" "$payload/usr/share/gnome-shell/extensions/waystroke@local/"
done
install -m 0755 target/native/libwaystroke-clipboard.so "$payload/usr/lib64/"
install -m 0644 target/native/WayStrokeClipboard-1.0.typelib "$payload/usr/lib64/girepository-1.0/"
mkdir -p "$rpm_work/"{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS,tmp}
tar -C "$payload" -czf "$rpm_work/SOURCES/payload.tar.gz" usr
[[ ${WAYSTROKE_RPM_RELEASE:-2} =~ ^[0-9]+$ ]] || exit 1
rpmbuild -bb --define "waystroke_release ${WAYSTROKE_RPM_RELEASE:-2}" --define "_topdir $rpm_work" --define "_tmppath $rpm_work/tmp" packaging/rpm/waystroke.spec
