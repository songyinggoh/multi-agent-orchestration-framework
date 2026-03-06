# Contributing to Orchestra

Thank you for your interest in contributing to Orchestra! This document provides guidelines for contributing.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/orchestra-agents/orchestra.git
cd orchestra

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest tests/ -x -q

# Run with coverage
pytest tests/ --cov=orchestra --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_state.py -v
```

## Code Quality

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/orchestra/
```

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass and coverage remains above 80%
4. Ensure `ruff check` and `mypy` pass with no errors
5. Submit a pull request with a clear description of the changes

## Code Style

- Follow PEP 8 with a line length of 100 characters
- Use type annotations for all public functions
- Use `async/await` for all I/O operations
- Prefer Protocol classes over ABC for interfaces

## Reporting Issues

- Use GitHub Issues to report bugs
- Include a minimal reproducible example
- Include Python version and OS information

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
