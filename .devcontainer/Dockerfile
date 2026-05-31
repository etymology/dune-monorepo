ARG PYTHON_VERSION=3.12
# Node base gives us node/npm (Claude Code + markdownlint/skills) out of the box.
FROM node:22-bookworm

ARG PYTHON_VERSION
ARG TZ=UTC
ENV TZ="$TZ"
ENV DEBIAN_FRONTEND=noninteractive

# System packages:
#   build-essential / pkg-config / libssl-dev -> compiling the Rust crates
#   libportaudio2 / libsndfile1               -> sounddevice (audio deps)
#   iptables / ipset / iproute2 / dnsutils / aggregate -> egress firewall
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git less procps sudo zsh jq nano vim \
      build-essential pkg-config libssl-dev \
      libportaudio2 libsndfile1 \
      iptables ipset iproute2 dnsutils aggregate \
    && rm -rf /var/lib/apt/lists/*

# Dirs backed by named volumes. Pre-creating them with the right owner means the
# (initially empty) volumes inherit `node` ownership instead of defaulting to root.
RUN mkdir -p /commandhistory \
    && chown -R node:node /commandhistory

# Passwordless sudo ONLY for the firewall init script (run at container start).
RUN echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall \
    && chmod 0440 /etc/sudoers.d/node-firewall

# Claude Code CLI.
RUN npm install -g @anthropic-ai/claude-code

COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /usr/local/bin/init-firewall.sh

USER node
ENV SHELL=/bin/bash

# Keep the project venv and Rust artifacts OUT of the bind-mounted /workspace so
# we never collide with the host's mac/Windows .venv and rust/target.
ENV UV_PROJECT_ENVIRONMENT=/home/node/.dune-venv \
    CARGO_TARGET_DIR=/home/node/.cargo-target \
    UV_PYTHON=${PYTHON_VERSION} \
    UV_LINK_MODE=copy

# uv (Python package + interpreter manager).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/node/.local/bin:${PATH}"

# Rust toolchain pinned to the workspace's rust-version (rust/Cargo.toml).
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --default-toolchain 1.83.0 --profile minimal --component clippy rustfmt
ENV PATH="/home/node/.cargo/bin:${PATH}"

# Volume mount points (node-owned so the empty volumes inherit perms) + shell QoL.
RUN mkdir -p /home/node/.claude /home/node/.dune-venv /home/node/.cargo-target \
      /home/node/.cache/uv /home/node/.cargo/registry \
    && echo 'export PROMPT_COMMAND="history -a"' >> /home/node/.bashrc \
    && echo 'export HISTFILE=/commandhistory/.bash_history' >> /home/node/.bashrc \
    && echo 'alias ccc="claude --dangerously-skip-permissions"' >> /home/node/.bashrc

WORKDIR /workspace
