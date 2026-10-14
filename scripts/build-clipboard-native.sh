#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Use normal development packages, or an explicitly extracted current-version SDK.
waystroke_sdk="${WAYSTROKE_MUTTER_SDK:-}"
if [[ -z "$waystroke_sdk" && -f /tmp/waystroke-mutter-sdk/usr/include/mutter-18/meta/meta-selection-source.h ]]; then
    waystroke_sdk=/tmp/waystroke-mutter-sdk
fi
if [[ -n "$waystroke_sdk" ]]; then
    version=$(sed -n 's/^Version: //p' "$waystroke_sdk/usr/lib64/pkgconfig/libmutter-18.pc")
    [[ "$version" == 50.5 ]] || { echo "需要 GNOME Mutter 50.5 开发头文件。" >&2; exit 1; }
    include_flags=("-I$waystroke_sdk/usr/include/mutter-18" "-I$waystroke_sdk/usr/include/mutter-18/clutter" "-I$waystroke_sdk/usr/include/mutter-18/cogl" "-I$waystroke_sdk/usr/include/mutter-18/mtk" "-I$waystroke_sdk/usr/include/graphene-1.0" "-I$waystroke_sdk/usr/lib64/graphene-1.0/include")
else
    [[ "$(pkg-config --modversion libmutter-18)" == 50.5 ]] || { echo "需要 mutter-devel 50.5 和 graphene-devel。" >&2; exit 1; }
    read -r -a include_flags <<< "$(pkg-config --cflags libmutter-18 graphene-gobject-1.0)"
fi
read -r -a base_flags <<< "$(pkg-config --cflags gio-2.0 cairo atk pango)"
read -r -a link_flags <<< "$(pkg-config --libs gio-2.0)"
mkdir -p target/native
cc -shared -fPIC -Wall -Wextra -Werror -Wno-unused-parameter "${include_flags[@]}" "${base_flags[@]}" extension/native/clipboard.c -o target/native/libwaystroke-clipboard.so "${link_flags[@]}" -l:libmutter-18.so.0
gi-compile-repository extension/native/WayStrokeClipboard-1.0.gir --output=target/native/WayStrokeClipboard-1.0.typelib
