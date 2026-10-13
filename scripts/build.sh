#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/generate-types.sh
npm run check --prefix apps/desktop
npm run web:build --prefix apps/desktop
cargo build --workspace --features waystroke-desktop/custom-protocol
