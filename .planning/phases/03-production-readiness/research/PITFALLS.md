# Domain Pitfalls — Phase 3: Production Readiness

**Domain:** Agent orchestration framework — production serving, observability, caching, safety
**Researched:** 2026-03-10

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or major production incidents.

### Pitfall 1: Coupling HTTP Request Lifecycle to Graph Execution

**What goes wrong:** FastAPI route handlers directly `await graph.run()`, tying graph execution to the HTTP connection. When a client disconnects, the run is cancelled mid-execution. With HITL workflows, an interrupted run might need to wait hours for human approval — no HTTP connection can be held open that long.

**Why it happens:** It is the simplest implementation: receive request, run graph, return result. Works fine in demos.

**Consequences:** Lost runs on client disconnect. Impossible HITL over HTTP. Server restart kills all active runs. No way to query run status from a different request.

**Prevention:** Implement a RunManager that decouples run lifecycle from request lifecycle. Runs execute as background asyncio tasks. HTTP endpoints create runs (returns run_id), query status, subscribe to events (SSE), and resume interrupted runs. The RunManager persists run state to the EventStore, so server restarts can recover in-progress runs.

**Detection:** If you find yourself storing `asyncio.Task` references inside route handler closures, you have this problem.

### Pitfall 2: OTel Span Attribute Drift from Semantic Conventions

**What goes wrong:** Instrumenting LLM calls with custom attribute names (e.g., `llm.model`, `llm.tokens.prompt`) instead of the official OTel GenAI semantic conventions (`gen_ai.request.model`, `gen_ai.usage.input_tokens`). When users connect Datadog, Langfuse, or Arize Phoenix, the dashboards show nothing because the attribute names do not match.

**Why it happens:** The GenAI semconv is still marked "Development" status, and older blog posts/tutorials use non-standard names. Also, v1.38.0 deprecated `gen_ai.prompt` and `gen_ai.completion` in favor of structured events — easy to implement the wrong version.

**Consequences:** Vendor dashboards do not recognize Orchestra traces. Users must write custom queries. Orchestra appears "not compatible" with the OTel ecosystem.

**Prevention:** Import attribute names from `opentelemetry-semantic-conventions` package (>=0.50) rather than hardcoding strings. Target v1.37+ conventions. Use span events (not attributes) for prompt/completion content per v1.38.0. Write a test that asserts span attribute names match the semconv constants.

**Detection:** If any `span.set_attribute()` call uses a hardcoded string starting with `llm.` or `ai.`, it is non-standard. All GenAI attributes start with `gen_ai.`.

### Pitfall 3: Caching Non-Deterministic LLM Calls

**What goes wrong:** All LLM responses get cached regardless of temperature setting. A creative writing agent with temperature=0.9 returns the exact same story on every subsequent call. Or worse, a call that includes dynamic context (current date, user profile) gets cached and returns stale/wrong context to a different user.

**Why it happens:** The caching layer is implemented as a global decorator without considering which calls are safe to cache.

**Consequences:** Users see identical "creative" outputs. Context-dependent responses leak across users. Debugging becomes impossible because cache hits silently return stale data.

**Prevention:** Only cache calls where temperature=0 (or a configurable threshold like <=0.1). Include ALL parameters in the cache key: model, messages, tools, system prompt, temperature, top_p. Provide an explicit `cacheable=False` override. Log cache hits with the original cache timestamp so stale data is detectable.

**Detection:** If your cache key is just `hash(prompt)`, it is wrong. It must include model + full message list + all generation parameters.

### Pitfall 4: Silent Guardrail Failures in Production

**What goes wrong:** A guardrail detects a violation (PII in output, off-topic response, malformed JSON) and silently returns a fallback value. No metric, no log, no alert. The system appears to work but is actually masking a systematic prompt engineering problem.

**Why it happens:** "Fail gracefully" is interpreted as "fail silently." The developer adds a try/except around the guardrail and returns a default.

**Consequences:** Undetected quality degradation. A guardrail firing on 40% of responses indicates a broken prompt, but nobody knows because the fallback looks normal. In regulated environments, silent PII leaks create compliance violations.

**Prevention:** Every guardrail violation must emit an OTel metric (`orchestra.guardrail.violations` with attributes for validator name, node name, action taken). Provide configurable violation strategies: `raise` (fail the node), `retry` (re-prompt the LLM with the violation as feedback), `fallback` (use default but always log), `warn` (continue, emit metric). Default should be `raise` in development, `fallback` in production.

**Detection:** If there is no `guardrail.violations` metric in your OTel output, guardrails are either not firing (unlikely) or silently swallowing violations.

## Moderate Pitfalls

### Pitfall 5: Token Count Mismatch Across Providers

**What goes wrong:** Using tiktoken to count tokens for Anthropic (Claude) or Google (Gemini) models. tiktoken implements OpenAI's BPE tokenizer — other providers use different tokenizers with different token counts.

**Prevention:** Use provider response headers as the authoritative token count source. Every major LLM API returns `usage.prompt_tokens` and `usage.completion_tokens` in the response. tiktoken is for pre-flight estimation of OpenAI models only. For Anthropic, use the `usage` field in the API response. For Google, use `countTokens` endpoint or response metadata. Do not build a "universal tokenizer."

### Pitfall 6: Redis as Single Point of Failure

**What goes wrong:** Adding Redis as a required dependency for caching and memory. Redis goes down, the entire serving layer crashes because cache lookups throw connection errors.

**Prevention:** Cache operations must be fail-open. If Redis is unavailable, the LLM call proceeds without caching. Wrap every Redis call in a try/except that logs the error and falls through. Use connection pooling with health checks. Make Redis an optional dependency — Orchestra must be deployable without Redis (just slower).

### Pitfall 7: SSE Connection Leaks

**What goes wrong:** SSE connections are opened but never properly closed. The async generator that yields events does not handle client disconnect, leading to orphaned generators that hold memory and prevent garbage collection.

**Prevention:** Use `sse-starlette`'s EventSourceResponse which detects client disconnects. In the async generator, use `try/finally` to clean up resources. Set a maximum SSE connection duration (e.g., 30 minutes) with automatic reconnect. Implement a heartbeat (`:ping` every 15-30 seconds) to detect dead connections through proxies.

### Pitfall 8: Budget Enforcement Race Conditions

**What goes wrong:** Cost tracking uses a check-then-act pattern: read current spend, compare to budget, allow/deny. Under concurrent requests, multiple calls pass the budget check simultaneously, each spending tokens, and the aggregate exceeds the budget.

**Prevention:** Use Redis atomic operations (INCRBYFLOAT) for spend tracking. The increment and check must be a single atomic operation. Alternatively, use optimistic concurrency with a CAS (compare-and-swap) pattern. For soft budgets, a race condition causing 5% overspend is acceptable — document this trade-off. Hard budgets require atomic enforcement.

## Minor Pitfalls

### Pitfall 9: OTel Trace Context Lost in Parallel Execution

**What goes wrong:** Orchestra's ParallelEdge runs multiple nodes concurrently via asyncio.gather(). If the OTel context is not explicitly copied to each coroutine, child spans attach to the wrong parent or become root spans.

**Prevention:** Use `opentelemetry.context.attach()` and `Context.copy()` when spawning parallel tasks. Or use `tracer.start_as_current_span()` as a context manager inside each parallel coroutine with explicit parent context.

### Pitfall 10: Overly Aggressive Cache TTLs

**What goes wrong:** Setting short TTLs (e.g., 5 minutes) to "stay fresh" negates the caching benefit. Setting long TTLs (e.g., 24 hours) causes stale responses when model behavior changes after fine-tuning or model updates.

**Prevention:** Use 1-hour default TTL for exact-match cache. Provide per-model TTL configuration. Include model version in cache key if the provider exposes it. Allow manual cache invalidation via an admin API endpoint.

### Pitfall 11: Load Testing with Mocked LLMs Only

**What goes wrong:** Load tests use mocked LLM providers (instant responses, zero latency). Tests pass at 1000 RPS. In production, actual LLM latency is 1-10 seconds, and the system cannot handle 50 concurrent users because all asyncio tasks are waiting on LLM responses and filling memory.

**Prevention:** Load tests must include a "simulated latency" mode where mocked providers add realistic delays (1-5 seconds, normally distributed). Also run a subset of load tests against actual LLM providers to validate real-world behavior. Measure time-to-first-token, not just throughput.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| 3.1 FastAPI Server | Pitfall 1 (lifecycle coupling) | Implement RunManager from day one, not as a refactor |
| 3.1 FastAPI SSE | Pitfall 7 (connection leaks) | Use sse-starlette, not raw StreamingResponse; add heartbeat |
| 3.2 OpenTelemetry | Pitfall 2 (attribute drift) | Import from semconv package; test attribute names |
| 3.2 OTel + Parallel | Pitfall 9 (context loss) | Explicit context propagation in parallel execution |
| 3.3 Redis Cache | Pitfall 3 (caching non-deterministic calls) | Temperature-aware caching policy |
| 3.3 Redis Cache | Pitfall 6 (SPOF) | Fail-open cache; Redis is optional |
| 3.4 Multi-Tier Memory | N/A (scope risk) | Scope down to interface + hot/cold tiering; defer vector retrieval |
| 3.5 Guardrails | Pitfall 4 (silent failures) | Metrics on every violation; configurable strategies |
| 3.6 Cost Tracking | Pitfall 5 (token mismatch) | Use provider response counts, not tiktoken for non-OpenAI |
| 3.6 Budget Enforcement | Pitfall 8 (race conditions) | Redis INCRBYFLOAT for atomic spend tracking |
| 3.7 Load Testing | Pitfall 11 (mocked-only testing) | Add simulated latency mode; test against real providers |

## Sources

- [FastAPI background tasks and SSE](https://dev.to/zachary62/build-an-llm-web-app-in-python-from-scratch-part-4-fastapi-background-tasks-sse-21g4)
- [OTel GenAI semconv deprecation in v1.38.0](https://github.com/traceloop/openllmetry/issues/3515)
- [Redis semantic caching threshold tuning](https://redis.io/blog/what-is-semantic-caching/)
- [Traceloop: token usage and cost per user](https://www.traceloop.com/blog/from-bills-to-budgets-how-to-track-llm-token-usage-and-cost-per-user)
- [LLM Locust benchmarking](https://www.truefoundry.com/blog/llm-locust-a-tool-for-benchmarking-llm-performance)
- [Multi-agent AI testing guide 2025](https://zyrix.ai/blogs/multi-agent-ai-testing-guide-2025/)
- [Guardrails AI docs](https://www.guardrailsai.com/docs/getting_started/quickstart)
- [LLM cost management patterns](https://oneuptime.com/blog/post/2026-01-30-llmops-cost-management/view)
