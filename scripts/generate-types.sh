#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cargo run -p waystroke-model --bin generate-model-types
cargo run -p waystroke-protocol --bin generate-protocol-types
