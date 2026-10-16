Name:           waystroke
Version:        0.1.0
Release:        %{?waystroke_release}%{!?waystroke_release:2}%{?dist}
Summary:        Native Wayland mouse gestures and text expansion
License:        MIT
Source0:        payload.tar.gz
Requires:       gnome-shell = 50.5
Requires:       polkit
Requires:       systemd
Requires:       bash
Requires:       kmod
Requires:       policycoreutils
Requires:       udev
Requires:       python3-gobject
Requires:       xdg-utils
Requires:       webkit2gtk4.1 >= 2.46
# Rust and WebKit are built before packaging; do not mutate the verified payload.
%global debug_package %{nil}
%global __brp_strip %{nil}
%global __brp_strip_comment_note %{nil}

%description
WayStroke settings, session core, GNOME 50.5 extension and idle privileged
mouse transport. Installation does not enable login startup or capture devices.

%prep
%setup -q -c

%build

%install
mkdir -p %{buildroot}
cp -a usr %{buildroot}/

%pre
# Stop only WayStroke components, including an older development transport.
if [ "$1" -gt 1 ]; then
    /usr/libexec/waystroke/stop-sessions || :
    systemctl stop waystroke-inputd.service >/dev/null 2>&1 || :
fi

%post
# Migrate the documented development unit so it cannot shadow the RPM unit.
if [ -f /etc/systemd/system/waystroke-inputd.service ] && grep -q '^ExecStart=/usr/local/libexec/waystroke-inputd ' /etc/systemd/system/waystroke-inputd.service; then
    systemctl stop waystroke-inputd.service >/dev/null 2>&1 || :
    rm -f /etc/systemd/system/waystroke-inputd.service /usr/local/libexec/waystroke-inputd
fi
systemctl daemon-reload >/dev/null 2>&1 || :
# An existing authorized installation resumes idle; first installation stays stopped.
if [ "$1" -gt 1 ] && [ -f /etc/waystroke/inputd.conf ]; then
    systemctl enable --now waystroke-inputd.service >/dev/null 2>&1 || :
fi

%preun
if [ "$1" -eq 0 ]; then
    /usr/libexec/waystroke/stop-sessions --uninstall || :
    systemctl disable --now waystroke-inputd.service >/dev/null 2>&1 || :
    rm -f /etc/waystroke/inputd.conf
    rmdir /etc/waystroke >/dev/null 2>&1 || :
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || :

%files
/usr/bin/waystroke
/usr/bin/waystroke-core
/usr/bin/waystroke-inputd
/usr/libexec/waystroke
/usr/lib/systemd/system/waystroke-inputd.service
/usr/lib/systemd/user/waystroke-core.service
/usr/share/dbus-1/services/io.github.waystroke.Core.service
/usr/share/polkit-1/actions/io.github.waystroke.configure-input.policy
/usr/share/applications/io.github.waystroke.Desktop.desktop
/usr/share/icons/hicolor/64x64/apps/io.github.waystroke.Desktop.png
/usr/share/icons/hicolor/scalable/apps/io.github.waystroke.Desktop.svg
/usr/share/gnome-shell/extensions/waystroke@local
/usr/lib64/libwaystroke-clipboard.so
/usr/lib64/girepository-1.0/WayStrokeClipboard-1.0.typelib

%changelog
* Fri Oct 16 2026 WayStroke developers - 0.1.0-2
- Preserve the authorized idle input service across system restarts.
* Thu Oct 15 2026 WayStroke developers - 0.1.0-1
- Initial Fedora 44 / GNOME 50.5 release packaging.
