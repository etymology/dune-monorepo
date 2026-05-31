#!/usr/bin/env bash
# Runs once when the container is first created.
set -euo pipefail

echo "==> uv sync (builds the local Rust crates via maturin/setuptools; first run is slow)"
uv sync

echo "==> npm install (markdownlint + skills tooling)"
npm install

cat <<'EOF'

==> Dev container ready.

    Agentic dev with bypass permissions:
        claude --dangerously-skip-permissions      (alias: ccc)

    Egress is firewalled to an allowlist (npm/PyPI/crates/GitHub/Anthropic),
    so bypass mode runs with a contained blast radius. Edit
    .devcontainer/init-firewall.sh to allow more domains.

    Common tasks:
        make test          # pytest + cargo test
        make lint          # ruff + clippy + markdownlint
        make typecheck     # ty

EOF
