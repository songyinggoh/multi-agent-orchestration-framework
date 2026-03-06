.PHONY: install lint type-check test test-cov fmt clean

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/

fmt:
	ruff format src/ tests/
	ruff check --fix src/ tests/

type-check:
	mypy src/orchestra/

test:
	pytest tests/ -x -q

test-cov:
	pytest tests/ --cov=orchestra --cov-report=term-missing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	rm -rf dist/ build/ *.egg-info
