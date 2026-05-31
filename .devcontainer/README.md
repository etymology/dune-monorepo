# Dev container — sandboxed agentic development

A throwaway Linux environment for running Claude Code with
`--dangerously-skip-permissions` safely. The container bounds the filesystem
blast radius, and a start-up firewall restricts outbound traffic to an
allowlist (npm / PyPI / crates.io / GitHub / Anthropic). Identical on macOS,
Linux, and Windows — only the Docker host differs.

## What's inside

- **uv** — Python env + the pinned interpreter (`PYTHON_VERSION` build arg, default 3.12)
- **Rust 1.83** (clippy + rustfmt) — builds the workspace crates into the Python env
- **Node 22** — Claude Code CLI, markdownlint, skills
- System libs for `sounddevice` (`libportaudio2`, `libsndfile1`)

The project venv (`/home/node/.dune-venv`) and Rust artifacts
(`/home/node/.cargo-target`) live **outside** the bind-mounted `/workspace`, so
they never collide with your host's `.venv` / `rust/target`. Auth, shell
history, and build caches persist in named volumes across rebuilds.

## How to run

### Option A — VS Code (or Cursor)

1. Install **Docker Desktop** (running) and the **Dev Containers** extension.
2. Open the repo folder.
3. Command Palette (`Cmd/Ctrl+Shift+P`) → **Dev Containers: Reopen in
   Container**.
4. Pick a config from the prompt: **dune-monorepo** (firewalled — use this for
   bypass mode) or **dune-monorepo (lite, no firewall)**.
5. First build runs `uv sync` + `npm install` (slow once; cached after). When
   the integrated terminal lands you inside the container:

   ```bash
   claude --dangerously-skip-permissions   # alias: ccc
   ```

### Option B — Terminal only (Make targets)

Driven by the [`devcontainer` CLI](https://github.com/devcontainers/cli) via
`npx` (no global install). From the repo root on the host:

```bash
make dc-up       # build + start the firewalled container (first run is slow)
make dc-shell    # drop into bash inside it
# then, inside the container:
ccc              # = claude --dangerously-skip-permissions
```

`make dc-claude` also exists, but for an interactive session prefer
`dc-shell` then `ccc` — `devcontainer exec` doesn't give Claude a full TTY.

### What the first run looks like

- **Auth** — Claude asks you to log in once; it's stored in the
  `dune-claude-config` volume, so later containers on this machine skip it.
- **Firewall** — every start prints `==> Configuring egress firewall...` then
  `OK: unlisted hosts blocked` / `OK: github reachable`. That's the sandbox
  locking egress to the allowlist; expected.
- You're non-root `node`, the repo is at `/workspace`, and the Python env is
  already synced.

### Gotchas

- **Don't call `python` / `pytest` directly** — the venv lives at
  `/home/node/.dune-venv` (off the bind mount). Use `uv run pytest`, `make
  test`, etc.; `uv run` finds it automatically.
- If a tool needs a host the firewall blocks, add it to `init-firewall.sh` and
  re-run `sudo /usr/local/bin/init-firewall.sh` inside the container (see
  *Adjusting the firewall* below).

## Lite (no-firewall) variant

`.devcontainer/lite/` is the same image without the egress firewall or network
capabilities — faster start, but open network. In VS Code's **Reopen in
Container**, pick the *lite* config. Only use it when you're **not** running
bypass mode, or you accept an unsandboxed network.

> A `.dockerignore` isn't needed here: the build context is `.devcontainer/`
> (not the repo root), so `node_modules` / `.venv` / `rust/target` are never
> sent to the Docker daemon.

## Per-OS notes

- **macOS / Linux** — Docker Desktop or colima/native Docker. Just works.
- **Windows** — use the **WSL2** backend and keep the repo *inside* the WSL2
  filesystem (`\\wsl$\...`), not on `C:`. Bind mounts from the Windows drive are
  slow and have permission quirks.

## Adjusting the firewall

Need another host (a new package index, an internal service)? Add it to the
`for domain in ...` list in `init-firewall.sh`, then rebuild or re-run
`sudo /usr/local/bin/init-firewall.sh`.

To disable egress filtering entirely, remove the `postStartCommand` and the
`--cap-add` args from `devcontainer.json` — but then bypass mode has open
network, which defeats much of the point.
