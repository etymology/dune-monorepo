.PHONY: test lint format check

test:
	uv run pytest

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

check: lint test
