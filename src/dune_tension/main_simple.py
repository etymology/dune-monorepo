"""Entry point for the simplified tensiometer GUI."""

from __future__ import annotations

from dune_tension.gui import run_simple_app


def main() -> None:
    run_simple_app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
