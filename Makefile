.PHONY: test lint format typecheck ci

test:
	uv run pytest

lint:
	uv run ruff check

format:
	uv run ruff format

typecheck:
	uv run mypy pyworkon/

ci: lint typecheck test
