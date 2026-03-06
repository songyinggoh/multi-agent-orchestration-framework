# Technology Stack

**Analysis Date:** 2026-03-07

## Languages

**Primary:**
- Python 3.11+ (target versions: 3.11, 3.12, 3.13) - All source code, tests, examples, CLI

**Secondary:**
- None detected

## Runtime

**Environment:**
- Python 3.11+ (CPython, compiled `__pycache__` files show cpython-313)
- asyncio as the default async runtime (Phase 1)
- Ray as optional distributed executor (planned, not yet implemented)

**Package Manager:**
- pip (with hatchling build backend)
- Lockfile: Not present (no `requirements.lock`, `poetry.lock`, or `pip-tools` output)

## Frameworks

**Core:**
- Pydantic v2 (>=2.5) - Data validation, state models, type-safe configuration. Used throughout for `BaseModel`, `Field`, `model_validate`, `model_dump`, `model_json_schema`. Rust-backed performance.
- httpx (>=0.26) - Async HTTP client for LLM provider communication. Used in `src/orchestra/providers/http.py` for OpenAI-compatible API calls.
- anyio (>=4.0) - Async compatibility layer (supports asyncio and trio)
- structlog (>=24.0) - Structured logging with JSON/console output modes
- Rich (>=13.0) - Terminal output formatting (CLI console, future trace rendering)
- Typer (>=0.12) - CLI framework for the `orchestra` command

**Testing:**
- pytest (>=8.0) - Test runner
- pytest-asyncio (>=0.23) - Async test support (configured with `asyncio_mode = "auto"`)
- pytest-cov (>=4.1) - Coverage reporting

**Build/Dev:**
- hatchling - PEP 517 build backend (`pyproject.toml` build system)
- ruff (>=0.3) - Linting and formatting (replaces black, isort, flake8)
- mypy (>=1.8) - Static type checking (strict mode enabled, pydantic plugin)
- pre-commit (>=3.6) - Git hook management

**Docs (optional):**
- mkdocs (>=1.5) - Documentation site generator
- mkdocs-material (>=9.5) - Material theme for mkdocs
- mkdocstrings[python] (>=0.24) - Auto-generated API docs from docstrings

## Key Dependencies

**Critical (required):**
- `pydantic>=2.5` - Foundation of the type system. `WorkflowState`, `Message`, `AgentResult`, `LLMResponse`, `TokenUsage`, all core types inherit `BaseModel`. Used for `Annotated` reducer extraction via `get_type_hints`. Removing Pydantic would require rewriting the entire core layer.
- `httpx>=0.26` - The only HTTP client used. `HttpProvider` in `src/orchestra/providers/http.py` uses `httpx.AsyncClient` for all LLM API communication including streaming (SSE).
- `structlog>=24.0` - Structured logging used in execution engine (`src/orchestra/core/compiled.py`) and configurable via `src/orchestra/observability/logging.py`.
- `anyio>=4.0` - Async runtime abstraction layer (supports both asyncio and trio)

**CLI/DX:**
- `typer>=0.12` - Powers the `orchestra` CLI (`src/orchestra/cli/main.py`). Commands: `version`, `init`, `run`.
- `rich>=13.0` - Terminal console output in CLI. Also used by structlog for colored dev console output.

**Optional Provider SDKs:**
- `anthropic>=0.20` - Anthropic Claude API (install: `pip install orchestra-agents[anthropic]`)
- `google-generativeai>=0.5` - Google Gemini API (install: `pip install orchestra-agents[google]`)
- `orchestra-agents[all-providers]` - All LLM provider SDKs

**Infrastructure:**
- No database drivers currently in dependencies (SQLite, PostgreSQL, Redis planned for Phase 2-3)
- No messaging libraries (NATS planned for Phase 3-4)
- No OpenTelemetry SDK yet (planned for Phase 3)

## Configuration

**Environment:**
- `OPENAI_API_KEY` - Read by `HttpProvider` from `os.environ` as fallback when no `api_key` parameter provided (`src/orchestra/providers/http.py:99`)
- `.env` and `.env.local` files are gitignored but no dotenv loading library is present in dependencies
- No configuration file system (no YAML/TOML config loading) beyond `pyproject.toml` for tool settings

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, dependencies, tool configs
  - Build system: hatchling
  - Package source: `src/orchestra/` (wheel target: `packages = ["src/orchestra"]`)
  - Entry point: `orchestra = "orchestra.cli.main:app"` (console script)
- `Makefile` - Developer task runner with targets: `install`, `lint`, `fmt`, `type-check`, `test`, `test-cov`, `clean`

**Type Checking:**
- mypy strict mode (`strict = true` in `pyproject.toml`)
- Pydantic mypy plugin enabled (`plugins = ["pydantic.mypy"]`)
- PEP 561 `py.typed` marker present at `src/orchestra/py.typed`
- Target: Python 3.11

**Linting:**
- ruff with `target-version = "py311"`, `line-length = 100`
- Rules enabled: pycodestyle (E, W), pyflakes (F), isort (I), pyupgrade (UP), bugbear (B), simplify (SIM), ruff-specific (RUF)
- Ignored: `UP042` (str enum pattern for 3.11 compat), `SIM105` (contextlib.suppress)
- Per-file ignores: tests (`RUF012`, `B017`, `S101`), examples (`RUF012`)

**Test Config:**
- Test paths: `tests/`
- asyncio_mode: `auto` (no need for `@pytest.mark.asyncio` on every test in most cases, though it is still used explicitly)
- Custom markers: `slow`, `integration`
- Coverage source: `orchestra`, omit: `tests/*`, fail_under: 80%

## Platform Requirements

**Development:**
- Python 3.11 or higher
- pip with editable install support (`pip install -e ".[dev]"`)
- No OS-specific dependencies detected (cross-platform Python)
- No Docker or container configuration present

**Production:**
- Same Python 3.11+ requirement
- No deployment configuration present (Dockerfile, Kubernetes manifests, etc.)
- No CI/CD pipeline configuration detected (no `.github/workflows/`, no `.gitlab-ci.yml`)
- Package distributable as a wheel via hatchling

## Package Distribution

**Package Name:** `orchestra-agents`
**Version:** 0.1.0
**License:** Apache-2.0
**Status:** Alpha (Development Status :: 3 - Alpha)
**Install:** `pip install orchestra-agents` (not yet published to PyPI)
**Extras:**
- `[anthropic]` - Anthropic Claude SDK
- `[google]` - Google Gemini SDK
- `[all-providers]` - All provider SDKs
- `[dev]` - Development tools (pytest, ruff, mypy, pre-commit)
- `[docs]` - Documentation tools (mkdocs, mkdocs-material)

---

*Stack analysis: 2026-03-07*
