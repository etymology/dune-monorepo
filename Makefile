.PHONY: test lint format

test:
	uv run pytest

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
