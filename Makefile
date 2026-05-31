.PHONY: sync test test-python test-rust lint lint-python lint-rust lint-md format format-python format-rust format-md typecheck build-rust clean-rust dc-build dc-up dc-shell dc-claude

sync:
	uv sync

test: test-python test-rust

test-python:
	uv run pytest

test-rust:
	cargo test --workspace --manifest-path rust/Cargo.toml

lint: lint-python lint-rust lint-md

lint-python:
	uv run ruff check src tests

lint-rust:
	cargo clippy --workspace --manifest-path rust/Cargo.toml --all-targets

lint-md:
	npm run markdown:lint -- README.md AGENTS.md dune_tension/README.md rust/README.md

format: format-python format-rust format-md

format-python:
	uv run ruff format src tests

format-rust:
	cargo fmt --manifest-path rust/Cargo.toml --all

format-md:
	npm run markdown:fix -- README.md AGENTS.md dune_tension/README.md rust/README.md

typecheck:
	uv run ty check

build-rust:
	uv run maturin develop --manifest-path rust/crates/dune-python/Cargo.toml

clean-rust:
	cargo clean --manifest-path rust/Cargo.toml

# --- Dev container (sandboxed agentic dev) ---------------------------------
# Drive the firewalled .devcontainer from the host via the devcontainer CLI.
DEVCONTAINER ?= npx --yes @devcontainers/cli

dc-build:
	$(DEVCONTAINER) build --workspace-folder .

dc-up:
	$(DEVCONTAINER) up --workspace-folder .

dc-shell: dc-up
	$(DEVCONTAINER) exec --workspace-folder . bash

# Open Claude in bypass mode inside the sandbox.
dc-claude: dc-up
	$(DEVCONTAINER) exec --workspace-folder . claude --dangerously-skip-permissions
