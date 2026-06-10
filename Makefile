.PHONY: sync test test-python lint lint-python lint-md format format-python format-md typecheck

sync:
	uv sync

test: test-python

test-python:
	uv run pytest

lint: lint-python lint-md

lint-python:
	uv run ruff check src tests

lint-md:
	npm run markdown:lint -- README.md AGENTS.md tension/README.md

format: format-python format-md

format-python:
	uv run ruff format src tests

format-md:
	npm run markdown:fix -- README.md AGENTS.md tension/README.md

typecheck:
	uv run ty check
