# Feature Landscape — Phase 3: Production Readiness

**Domain:** Agent orchestration framework — production serving, observability, safety
**Researched:** 2026-03-10

## Table Stakes

Features users expect from a production-grade agent framework. Missing = not production-ready.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| HTTP API for agent execution | Agents must be callable from other services | Medium | POST /runs, GET /runs/{id}, POST /runs/{id}/resume |
| Streaming token delivery | Users expect real-time feedback during LLM generation | Medium | SSE with EventSourceResponse, async generators |
| Distributed tracing | Ops teams need to debug production issues without reading logs | Medium | OTel spans for graph/node/LLM layers |
| Token usage reporting | Every run must report prompt + completion tokens consumed | Low | Provider responses already include counts — surface them |
| Structured error responses | API consumers need machine-readable errors, not stack traces | Low | Pydantic error models with error codes and request IDs |
| Health check endpoint | Load balancers and Kubernetes need liveness/readiness probes | Low | GET /health with Redis, DB dependency checks |
| Graceful shutdown | In-flight runs must complete on server restart, not be killed | Medium | Uvicorn shutdown hooks + run tracking registry |
| Request-level timeout | Must prevent runaway agent executions from consuming resources forever | Low | FastAPI middleware + asyncio.wait_for on graph.run() |

## Differentiators

Features that set Orchestra apart from LangGraph Cloud, CrewAI Enterprise, AutoGen.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Event-sourced run replay via API | No other framework exposes time-travel debugging over HTTP. Orchestra already has the event store — just expose it. | Medium | GET /runs/{id}/events, POST /runs/{id}/fork |
| HITL resume via API | Existing interrupt/resume is CLI-only; exposing it as REST makes it usable in real applications | Low | POST /runs/{id}/resume with approval payload. Already implemented in CompiledGraph. |
| Cache-through LLM provider | Transparent caching at the provider layer — zero code changes for users | Medium | Decorator on LLMProvider.chat() that checks Redis before calling the API |
| Per-node guardrails | Attach validators to specific nodes, not just graph input/output. More granular than any competing framework. | Medium | Extends existing ContractRegistry + BoundaryContract pattern |
| OTel-native cost metrics | Cost as OTel metrics (not just log lines). Enables Grafana dashboards, alerting, and budget monitoring out of the box. | Low | Custom gen_ai.usage.cost metric emitted alongside spans |
| Cost-aware model routing | Automatically downgrade models (e.g., GPT-4o to GPT-4o-mini) when budget thresholds are hit | High | Unique differentiator for cost-conscious production deployments |
| Checkpoint-aware caching | Cache invalidation tied to event-sourced checkpoints — ensures cache consistency when replaying/forking runs | High | Novel pattern. Ensures time-travel + caching do not conflict. |

## Anti-Features

Features to explicitly NOT build in Phase 3.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Full LLM proxy (LiteLLM-style) | Orchestra already has multi-provider adapters. A proxy layer adds latency and operational complexity without value. | Keep provider adapters direct. Add cost tracking as a cross-cutting concern within them. |
| Agent marketplace / registry | Enterprise feature, out of scope for production-readiness. | Defer to Phase 4. |
| Built-in vector database | Massive dependency; users have their own vector stores (Pinecone, Weaviate, pgvector). | Provide an interface for plugging in external vector stores for semantic cache embeddings. |
| WebSocket streaming | SSE is sufficient for unidirectional server-to-client streaming. WebSocket adds complexity for bidirectional comms Orchestra does not need today. | Use SSE. If bidirectional interaction is needed later (e.g., collaborative editing), add WebSocket as a separate transport in Phase 4. |
| Custom dashboard UI | Building frontend is out of scope. OTel exporters already feed Grafana and Jaeger. | Provide docker-compose with Jaeger for local dev. Document Grafana dashboard JSON templates. |
| Full Mem0/Letta integration | Importing entire memory frameworks conflicts with Orchestra's own runtime and adds heavy dependencies. | Adopt the tiered memory pattern (hot/cold promotion/demotion), not the framework. |
| Prompt versioning system | Important but orthogonal. Can use git, external config management, or prompt registries. | Document how to version prompts externally. Do not build a versioning system. |
| LMQL constrained decoding | Requires control over the inference server's logit outputs. Orchestra uses external LLM APIs (OpenAI, Anthropic, Google) where logit-level control is unavailable. | Use Guardrails AI for output validation (post-generation), not constrained decoding (during-generation). |

## Feature Dependencies

```
FastAPI Server (3.1) --> Streaming SSE (3.1)
FastAPI Server (3.1) --> Health Check (3.1)
FastAPI Server (3.1) --> HITL Resume via API (3.1)
FastAPI Server (3.1) --> Load Testing (3.7)

OTel Instrumentation (3.2) --> Cost Tracking as OTel Metrics (3.6)
OTel Instrumentation (3.2) --> Trace Visualization (3.2 docker-compose)

Redis Client (3.3) --> LLM Response Cache (3.3)
Redis Client (3.3) --> Multi-Tier Memory Hot Tier (3.4)
Redis Client (3.3) --> Semantic Cache [stretch] (3.3)

Existing ContractRegistry --> Guardrail Protocol (3.5)
Guardrail Protocol (3.5) --> Pre/Post-computation Hooks (3.5)

Token Counting (3.6) --> Cost Calculation (3.6)
Token Counting (3.6) --> Cost-Aware Model Routing [stretch] (3.6)
Cost Calculation (3.6) --> Budget Enforcement (3.6)
```

## MVP Recommendation

Prioritize (in order):
1. **FastAPI server with SSE streaming** — without this, nothing else is accessible over HTTP
2. **OTel instrumentation for graph/node/LLM spans** — without this, cannot measure anything built after
3. **Redis exact-match LLM response cache** — immediate cost savings, simple to implement
4. **Token usage reporting + cost calculation** — table stakes for any production deployment
5. **Input/output guardrails (extending ContractRegistry)** — safety baseline before real users hit the API

Defer to later in Phase 3 or Phase 4:
- **Semantic caching**: Requires embedding model setup, similarity threshold tuning. Exact-match caching covers 80% of the value.
- **Full multi-tier memory with vector retrieval**: Build the MemoryManager interface and hot/cold tiering, but defer vector-based retrieval to Phase 4.
- **Cost-aware model routing**: High complexity. Requires cost tracking to be stable first. Good Phase 4 candidate.
- **Checkpoint-aware caching**: Novel but complex. Get basic caching working first, then layer checkpoint awareness.

## Sources

- [FastAPI SSE patterns](https://medium.com/@2nick2patel2/fastapi-server-sent-events-for-llm-streaming-smooth-tokens-low-latency-1b211c94cff5)
- [OpenTelemetry GenAI span conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [RedisVL LLM caching](https://redis.io/docs/latest/develop/ai/redisvl/user_guide/llmcache/)
- [Guardrails AI quickstart](https://www.guardrailsai.com/docs/getting_started/quickstart)
- [tokencost PyPI](https://pypi.org/project/tokencost/)
- [Langfuse cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
- [Traceloop: bills to budgets](https://www.traceloop.com/blog/from-bills-to-budgets-how-to-track-llm-token-usage-and-cost-per-user)
