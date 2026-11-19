#!/usr/bin/env bash
set -eu
version=${1:-$(rpm -q --qf '%{VERSION}' mutter)}
case ${version%%.*} in
    50) echo 18 ;;
    51) echo 51 ;;
    *) echo "不支持的 Mutter 版本：$version" >&2; exit 1 ;;
esac
