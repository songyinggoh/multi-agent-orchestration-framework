# External Integrations

**Analysis Date:** 2026-03-07

## APIs & External Services

**LLM Providers (Current):**
- OpenAI-compatible endpoints - Primary LLM integration for agent reasoning
  - SDK/Client: `httpx.AsyncClient` via `src/orchestra/providers/http.py`
  - Auth: `OPENAI_API_KEY` env var (fallback when no `api_key` param)
  - Protocol: OpenAI Chat Completions API format (`/chat/completions`)
  - Default base URL: `https://api.openai.com/v1`
  - Supports: OpenAI, Ollama, vLLM, LiteLLM, Azure OpenAI, any OpenAI-compatible endpoint
  - Features: Completion, streaming (SSE), tool/function calling, structured output (json_schema response_format)
  - Retry: Exponential backoff with max 3 retries for rate limits and server errors
  - Models with cost tracking: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1`, `o3-mini`

**LLM Providers (Planned, not implemented):**
- Anthropic (Claude) - Optional extra `[anthropic]`, uses `anthropic>=0.20` SDK
  - Planned location: `src/orchestra/providers/anthropic.py` (does not exist yet)
- Google (Gemini) - Optional extra `[google]`, uses `google-generativeai>=0.5` SDK
  - Planned location: `src/orchestra/providers/google.py` (does not exist yet)
- Ollama (local models) - Supported through `HttpProvider` with custom `base_url`
  - Example: `HttpProvider(base_url="http://localhost:11434/v1", default_model="llama3")`
  - Planned dedicated adapter: `src/orchestra/providers/ollama.py` (does not exist yet)

**MCP (Model Context Protocol):**
- Planned for Phase 2, not yet implemented
- Design calls for `MCPClient` at `src/orchestra/tools/mcp.py` (does not exist yet)
- Will allow connecting to MCP tool servers

## Data Storage

**Databases:**
- None currently integrated
- Planned (Phase 2-3):
  - SQLite - Dev/local storage backend at `src/orchestra/storage/sqlite.py` (does not exist yet)
  - PostgreSQL - Production storage at `src/orchestra/storage/postgres.py` (does not exist yet)
  - pgvector extension - Semantic search for long-term memory at `src/orchestra/memory/long_term.py` (does not exist yet)

**File Storage:**
- Local filesystem only (CLI `init` command creates project directories)
- No cloud storage integration

**Caching:**
- None currently
- Planned (Phase 3): Redis 7+ for hot state cache at `src/orchestra/storage/redis.py` (does not exist yet)

**State Persistence:**
- Currently: In-memory only. State is a Pydantic model (`WorkflowState`) held in process memory during execution.
- Planned (Phase 2): Event-sourced persistence via `src/orchestra/storage/events.py` (does not exist yet)

## Authentication & Identity

**Auth Provider:**
- No user authentication system
- LLM auth: API key passed via constructor or `OPENAI_API_KEY` env var
  - Implementation: `src/orchestra/providers/http.py` line 99 (`os.environ.get("OPENAI_API_KEY", "")`)
  - Sent as `Authorization: Bearer {api_key}` header

**Agent Security (Planned, Phase 4):**
- Planned at `src/orchestra/security/identity.py` (does not exist yet)
- Capability-based agent identity with scoped permissions
- Tool-level ACLs via `ToolRegistry`

## Monitoring & Observability

**Error Tracking:**
- No external error tracking service (no Sentry, Datadog, etc.)
- Comprehensive error hierarchy in `src/orchestra/core/errors.py` (24 exception classes)
- Errors include contextual information: what happened, where, how to fix

**Logs:**
- structlog with two output modes configured in `src/orchestra/observability/logging.py`:
  - Dev: `structlog.dev.ConsoleRenderer(colors=True)` - Human-readable colored output
  - Production: `structlog.processors.JSONRenderer()` - Machine-parseable JSON
- Log features: ISO timestamps, log level, logger name, context variables, stack info
- Used in: `src/orchestra/core/compiled.py` for node execution logging (`logger.debug("executing_node", ...)`)

**Tracing:**
- No OpenTelemetry integration yet (planned Phase 3)
- Planned location: `src/orchestra/observability/tracing.py` (does not exist yet)
- Planned Rich terminal trace tree at `src/orchestra/observability/console.py` (does not exist yet)

**Metrics:**
- Token usage tracked in `TokenUsage` model (`src/orchestra/core/types.py`)
- Cost estimation built into `HttpProvider._parse_response()` using `_MODEL_COSTS` lookup table
- `RunResult` includes `duration_ms`, `total_tokens`, `total_cost_usd` fields
- No external metrics export (Prometheus, StatsD, etc.)

## CI/CD & Deployment

**Hosting:**
- No deployment target configured
- No Dockerfile, `docker-compose.yml`, or Kubernetes manifests
- Planned (Phase 3): FastAPI server at `src/orchestra/api/app.py` (does not exist yet)

**CI Pipeline:**
- No CI configuration detected (no `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, etc.)
- Local quality checks via Makefile: `make lint`, `make type-check`, `make test`

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` - Required for `HttpProvider` when no `api_key` constructor arg. The provider will operate with an empty string if neither is provided, but API calls will fail with `AuthenticationError`.

**Optional env vars:**
- None currently configured beyond `OPENAI_API_KEY`
- Future provider SDKs will likely require: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`

**Secrets management:**
- No secrets management system
- `.env` and `.env.local` are gitignored
- No dotenv loading library in dependencies (no `python-dotenv`)
- API keys passed via environment variables or constructor parameters

## Webhooks & Callbacks

**Incoming:**
- None. No HTTP server or webhook endpoints exist yet.
- Planned (Phase 3): FastAPI REST API with routes at `src/orchestra/api/routes/`
- Planned (Phase 3): WebSocket endpoint for human-in-the-loop at `src/orchestra/api/websocket.py`

**Outgoing:**
- None. The framework makes outgoing HTTP calls only to LLM provider APIs via `HttpProvider`.

## Integration Architecture

**Provider Protocol:**
All LLM integrations are abstracted behind the `LLMProvider` protocol defined in `src/orchestra/core/protocols.py`:

```python
@runtime_checkable
class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...
    @property
    def default_model(self) -> str: ...
    async def complete(self, messages: list[Message], ...) -> LLMResponse: ...
    async def stream(self, messages: list[Message], ...) -> AsyncIterator[StreamChunk]: ...
    def count_tokens(self, messages: list[Message], model: str | None = None) -> int: ...
    def get_model_cost(self, model: str | None = None) -> ModelCost: ...
```

**Current implementations:**
- `HttpProvider` at `src/orchestra/providers/http.py` - Generic OpenAI-compatible HTTP client
- `ScriptedLLM` at `src/orchestra/testing/scripted.py` - Deterministic mock for testing

**Tool Protocol:**
Tool integrations are abstracted behind the `Tool` protocol in `src/orchestra/core/protocols.py`:

```python
@runtime_checkable
class Tool(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters_schema(self) -> dict[str, Any]: ...
    async def execute(self, arguments: dict[str, Any], *, context: ExecutionContext | None = None) -> ToolResult: ...
```

**Current implementations:**
- `ToolWrapper` at `src/orchestra/tools/base.py` - Wraps async Python functions as tools via `@tool` decorator
- `ToolRegistry` at `src/orchestra/tools/registry.py` - Central tool registry with OpenAI function-calling schema generation

## Integration Points Summary

| Integration | Status | File | Protocol |
|---|---|---|---|
| OpenAI API | Implemented | `src/orchestra/providers/http.py` | HTTP (OpenAI Chat Completions) |
| Any OpenAI-compat endpoint | Implemented | `src/orchestra/providers/http.py` | HTTP (configurable base_url) |
| Anthropic SDK | Dependency declared, code not written | - | - |
| Google Gemini SDK | Dependency declared, code not written | - | - |
| MCP Tool Servers | Planned (Phase 2) | - | - |
| SQLite | Planned (Phase 2) | - | - |
| PostgreSQL | Planned (Phase 3) | - | - |
| Redis | Planned (Phase 3) | - | - |
| OpenTelemetry | Planned (Phase 3) | - | - |
| FastAPI Server | Planned (Phase 3) | - | - |
| NATS JetStream | Planned (Phase 4) | - | - |
| Ray Distributed | Planned (Phase 4) | - | - |

---

*Integration audit: 2026-03-07*
