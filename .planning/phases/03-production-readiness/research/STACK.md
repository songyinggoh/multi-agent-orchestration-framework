# Technology Stack — Phase 3: Production Readiness

**Project:** Orchestra
**Researched:** 2026-03-10

## Recommended Stack

### Wave 1: Serving and Observability

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | >=0.115 | HTTP server for agent orchestration | Async-native, Pydantic v2 integration, first-class SSE support, dominant Python API framework |
| sse-starlette | >=2.0 | Server-Sent Events streaming | Production-grade EventSourceResponse; handles client disconnects, heartbeat pings, and backpressure correctly. FastAPI's built-in StreamingResponse lacks these. |
| uvicorn | >=0.30 | ASGI production server | Standard ASGI server; supports graceful shutdown, HTTP/2, and worker process management |
| opentelemetry-sdk | >=1.29 | Distributed tracing core | Industry standard; vendor-neutral; consumed by Jaeger, Tempo, Datadog, Langfuse |
| opentelemetry-instrumentation-fastapi | >=0.50 | Auto-instrument HTTP layer | Automatic span creation for all HTTP requests with zero code changes |
| opentelemetry-exporter-otlp | >=1.29 | Trace/metric export | OTLP protocol works with Jaeger, Grafana Tempo, Datadog, and all major backends |
| opentelemetry-semantic-conventions | >=0.50 | GenAI span attributes | Provides `gen_ai.*` attribute names per v1.37+ spec. Use this, not hardcoded strings. |

### Wave 2: Performance and Memory

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| redis[hiredis] | >=5.0 | Redis async client | hiredis C parser for 10x throughput; native async/await support; connection pooling built-in |
| redisvl | >=0.4 | LLM cache (exact + semantic) | Maintained by Redis Inc; provides both `SemanticCache` and exact-match `LLMCache`; built-in TTL and vector search |

### Wave 3: Governance and Operations

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| guardrails-ai | >=0.5 | I/O validation and safety | Pydantic-native; Hub of 100+ pre-built validators (PII, toxicity, topic adherence); supports async; integrates with existing Pydantic models |
| tokencost | >=0.2 | Cost calculation per LLM call | Auto-updated pricing for 400+ models across OpenAI, Anthropic, Google, Mistral, etc. Single function call: `calculate_cost(prompt, completion, model)` |
| tiktoken | >=0.8 | Token count estimation (pre-flight) | Accurate BPE tokenizer for OpenAI models. For Anthropic/Google, use their API response token counts instead. |

### Wave 4: Reliability and Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| locust | >=2.30 | Load testing | Python-native; custom user behaviors can import Orchestra classes directly; web UI for real-time monitoring; supports distributed load generation |
| pytest-asyncio | >=0.24 | Async test infrastructure | Already in use; needed for chaos/fault-injection test scenarios |

### Infrastructure (Docker Compose for local dev)

| Technology | Purpose | Why |
|------------|---------|-----|
| Jaeger (all-in-one) | Trace visualization | Zero-config local tracing; receives OTLP directly; provides query UI |
| Redis 7+ | Cache backend | Required for redisvl; supports vector search via RediSearch module |
| PostgreSQL 16 | Event store (already supported) | Already have asyncpg adapter; used for cold-tier memory storage |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Streaming | SSE via sse-starlette | WebSocket | SSE is simpler, sufficient for server-to-client streaming, has built-in browser reconnect. WebSocket adds bidirectional complexity Orchestra does not need. |
| SSE library | sse-starlette | FastAPI StreamingResponse | StreamingResponse lacks disconnect detection, heartbeat, and proper SSE event formatting. sse-starlette handles all of these. |
| Observability | OpenTelemetry SDK | Langfuse SDK / OpenLLMetry | OTel is vendor-neutral. Langfuse and OpenLLMetry consume OTel traces — no need to couple to their proprietary SDKs. Ship OTel, users choose their backend. |
| Trace backend | Jaeger (local dev) | Grafana Tempo | Jaeger is simpler for local dev (single binary). Tempo is better for production (S3 storage). Both consume OTLP — the choice is the user's, not Orchestra's. |
| Redis cache | redisvl | GPTCache | GPTCache maintenance has stalled (last significant release mid-2024). redisvl is actively maintained by Redis Inc. |
| Redis cache | redisvl | LangChain cache | LangChain cache adds an unnecessary LangChain dependency. Orchestra should not couple to LangChain. |
| Guardrails | Guardrails AI | NeMo Guardrails | NeMo Guardrails uses Colang DSL and is optimized for conversational dialog management — heavier than needed. Orchestra needs programmatic pre/post validators on nodes, which Guardrails AI handles better with Pydantic. |
| Guardrails | Guardrails AI | LMQL | LMQL uses constrained decoding (logit masking) — requires control over the inference server. Orchestra uses external LLM APIs, so LMQL's core value proposition does not apply. |
| Cost tracking | tokencost | LiteLLM | LiteLLM is a full LLM proxy/router (800+ models). Too much scope when Orchestra only needs cost calculation. tokencost is focused: one function, auto-updated prices. |
| Load testing | Locust | k6 | Locust is Python-native. Test scenarios can directly import and instantiate Orchestra graphs, providers, and agents. k6 requires JavaScript, creating a language boundary that makes agent-level testing impossible. |
| Token counting | tiktoken + provider APIs | Universal tokenizer | No universal tokenizer exists across providers. Use provider response headers as the source of truth; tiktoken only for pre-flight estimation of OpenAI token counts. |
| Memory framework | Custom tiered (Redis + SQLite/Postgres) | Mem0 / Letta | Mem0 and Letta are full agent frameworks with their own runtimes. Importing them would conflict with Orchestra's CompiledGraph. Adopt their tiered-memory pattern, not their code. |

## Installation

```bash
# Wave 1: Serving & Observability
pip install \
  "fastapi>=0.115" \
  "sse-starlette>=2.0" \
  "uvicorn[standard]>=0.30" \
  "opentelemetry-sdk>=1.29" \
  "opentelemetry-instrumentation-fastapi>=0.50" \
  "opentelemetry-exporter-otlp>=1.29" \
  "opentelemetry-semantic-conventions>=0.50"

# Wave 2: Performance & Memory
pip install \
  "redis[hiredis]>=5.0" \
  "redisvl>=0.4"

# Wave 3: Governance & Operations
pip install \
  "guardrails-ai>=0.5" \
  "tokencost>=0.2" \
  "tiktoken>=0.8"

# Wave 4: Testing (dev dependencies only)
pip install --group dev \
  "locust>=2.30"
```

## Sources

- [FastAPI SSE streaming patterns (Medium, Dec 2025)](https://medium.com/@2nick2patel2/fastapi-server-sent-events-for-llm-streaming-smooth-tokens-low-latency-1b211c94cff5)
- [sse-starlette PyPI](https://pypi.org/project/sse-starlette/)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OTel GenAI agent span conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [Datadog OTel GenAI semconv support](https://www.datadoghq.com/blog/llm-otel-semantic-convention/)
- [RedisVL LLM caching docs](https://redis.io/docs/latest/develop/ai/redisvl/user_guide/llmcache/)
- [Redis semantic caching blog](https://redis.io/blog/what-is-semantic-caching/)
- [Guardrails AI GitHub](https://github.com/guardrails-ai/guardrails)
- [Guardrails AI + NeMo integration](https://guardrailsai.com/blog/nemoguardrails-integration)
- [tokencost GitHub (AgentOps)](https://github.com/AgentOps-AI/tokencost)
- [Langfuse cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
- [LLM Locust benchmarking](https://www.truefoundry.com/blog/llm-locust-a-tool-for-benchmarking-llm-performance)
- [Locust for chaos engineering (Harness)](https://www.harness.io/blog/load-testing-at-scale-understanding-locust-loadgen-in-harness-chaos-engineering)
- [Mem0 paper (arXiv 2504.19413)](https://arxiv.org/abs/2504.19413)
- [Multi-agent AI testing guide 2025 (Zyrix)](https://zyrix.ai/blogs/multi-agent-ai-testing-guide-2025/)
