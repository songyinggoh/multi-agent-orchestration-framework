# Phase 3.6: Cost Management - Deep Research

**Researched:** 2026-03-10
**Domain:** LLM cost tracking, budget enforcement, cost-aware routing
**Confidence:** HIGH

---

## Summary

Orchestra already captures per-call cost data (`LLMCalled` events with `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`, `model`) and has placeholder fields in `ExecutionCompleted` (`total_tokens`, `total_cost_usd` defaulting to 0). Each provider has a hardcoded `_MODEL_COSTS` dict and a `get_model_cost()` method. The `ModelCost` and `TokenUsage` types exist in `core/types.py`. What is missing is: (1) a centralized cost registry replacing scattered per-provider dicts, (2) a `CostAggregator` EventBus subscriber to wire up the `ExecutionCompleted` totals, (3) budget enforcement (soft/hard limits), (4) cost attribution breakdowns, and (5) optional OTel metrics export.

The ecosystem has converged on LiteLLM's `model_prices_and_context_window.json` as the de facto pricing database (700+ models, updated weekly by the community). For token counting, `tiktoken` remains the standard for OpenAI models; Anthropic and Google return actual token counts in API responses, making pre-call counting unnecessary for cost tracking (only needed for budget pre-checks). Budget enforcement follows a four-component pattern: usage logging, budget manager, enforcement layer, and alerting.

**Primary recommendation:** Build a `ModelCostRegistry` that loads pricing from a bundled JSON file (seeded from LiteLLM's format), a `CostAggregator` EventBus subscriber, and a `BudgetPolicy` with soft/hard limits -- all as pure Orchestra components with no new runtime dependencies.

---

## Standard Stack

### Core (Zero New Dependencies)
| Component | Purpose | Why |
|-----------|---------|-----|
| `ModelCostRegistry` | Centralized pricing table | Replaces 3 scattered `_MODEL_COSTS` dicts |
| `CostAggregator` | EventBus subscriber accumulating per-run costs | Wires `LLMCalled` -> `ExecutionCompleted.total_cost_usd` |
| `BudgetPolicy` | Soft/hard limit enforcement | Pre-check before LLM calls |

### Optional Dependencies
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tiktoken` | >=0.7 | Accurate token counting for OpenAI models | Pre-call budget checks, cost estimation |
| `opentelemetry-sdk` | >=1.40 | Export cost metrics to Prometheus/Grafana | When OTel integration (3.2) is active |

### Why NOT External Cost Libraries

| Library | Why Skip |
|---------|----------|
| `tokencost` | Adds tiktoken + litellm as transitive deps; pricing JSON last updated Jan 2024; Orchestra already has per-provider cost calculation |
| `litellm` (full SDK) | 50+ transitive dependencies; Orchestra uses direct HTTP providers, not litellm's completion API |
| `llm_cost_estimation` | Minimal maintenance, limited model coverage |

**Use LiteLLM's pricing JSON data file directly** -- it is MIT-licensed, community-maintained, and can be vendored or fetched without importing litellm itself.

---

## Architecture Patterns

### Recommended Module Structure

```
src/orchestra/
  cost/
    __init__.py          # Public API: CostAggregator, BudgetPolicy, ModelCostRegistry
    registry.py          # ModelCostRegistry - centralized pricing
    aggregator.py        # CostAggregator - EventBus subscriber
    budget.py            # BudgetPolicy, BudgetExceededError
    _default_prices.json # Bundled pricing data (subset of LiteLLM format)
```

### Pattern 1: ModelCostRegistry (Centralized Pricing)

**What:** Single source of truth for model pricing, replacing the scattered `_MODEL_COSTS` dicts in `http.py`, `anthropic.py`, and `google.py`.

**Current problem:** Each provider has its own hardcoded dict:
- `http.py` lines 75-81: OpenAI models only
- `anthropic.py` lines 40-46: Anthropic models only
- `google.py` lines 41-46: Google models only

**Design:**

```python
# src/orchestra/cost/registry.py
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class ModelPricing:
    """Pricing for a single model."""
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0
    max_input_tokens: int = 0
    max_output_tokens: int = 0

class ModelCostRegistry:
    """Centralized model pricing registry.

    Loads pricing from a bundled JSON file. Supports runtime overrides
    for custom/fine-tuned models and user-specified pricing.

    Usage:
        registry = ModelCostRegistry()  # loads bundled defaults
        registry = ModelCostRegistry.from_file("custom_prices.json")

        pricing = registry.get("gpt-4o")
        cost = pricing.input_cost_per_token * input_tokens + \
               pricing.output_cost_per_token * output_tokens
    """

    def __init__(self) -> None:
        self._prices: dict[str, ModelPricing] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load bundled pricing data."""
        default_path = Path(__file__).parent / "_default_prices.json"
        if default_path.exists():
            self._load_from_file(default_path)

    @classmethod
    def from_file(cls, path: str | Path) -> ModelCostRegistry:
        """Load pricing from a custom JSON file."""
        registry = cls.__new__(cls)
        registry._prices = {}
        registry._load_from_file(Path(path))
        return registry

    def _load_from_file(self, path: Path) -> None:
        """Parse LiteLLM-format pricing JSON."""
        data = json.loads(path.read_text())
        for model_name, info in data.items():
            if isinstance(info, dict) and "input_cost_per_token" in info:
                self._prices[model_name] = ModelPricing(
                    input_cost_per_token=info.get("input_cost_per_token", 0.0),
                    output_cost_per_token=info.get("output_cost_per_token", 0.0),
                    max_input_tokens=info.get("max_input_tokens", 0),
                    max_output_tokens=info.get("max_output_tokens", 0),
                )

    def register(self, model: str, pricing: ModelPricing) -> None:
        """Register or override pricing for a model at runtime."""
        self._prices[model] = pricing

    def get(self, model: str) -> ModelPricing:
        """Get pricing for a model. Returns zero-cost if unknown."""
        # Exact match first
        if model in self._prices:
            return self._prices[model]
        # Prefix match for versioned model names (e.g., "gpt-4o-2024-08-06")
        for key in self._prices:
            if model.startswith(key) or key.startswith(model):
                return self._prices[key]
        return ModelPricing()  # zero-cost default

    def calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost in USD for a given model and token counts."""
        pricing = self.get(model)
        return (
            pricing.input_cost_per_token * input_tokens
            + pricing.output_cost_per_token * output_tokens
        )

    @property
    def known_models(self) -> list[str]:
        """List all models with known pricing."""
        return sorted(self._prices.keys())
```

**LiteLLM JSON format (per model entry):**
```json
{
  "gpt-4o": {
    "max_tokens": 16384,
    "max_input_tokens": 128000,
    "max_output_tokens": 16384,
    "input_cost_per_token": 0.0000025,
    "output_cost_per_token": 0.00001,
    "litellm_provider": "openai",
    "mode": "chat",
    "supports_function_calling": true,
    "supports_vision": true
  }
}
```

Note: LiteLLM uses cost-per-token (not per-1K). Orchestra's current `ModelCost` uses `input_cost_per_1k`. The registry should normalize to per-token internally and expose both conventions.

### Pattern 2: CostAggregator (EventBus Subscriber)

**What:** Subscribes to `LLMCalled` events, accumulates costs per run, and populates `ExecutionCompleted.total_cost_usd` / `total_tokens`.

**Integration point:** Same subscriber pattern used by `RichTraceRenderer` and `EventStore` in `compiled.py`.

```python
# src/orchestra/cost/aggregator.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from orchestra.storage.events import EventType, LLMCalled, WorkflowEvent


@dataclass
class RunCostSummary:
    """Accumulated cost data for a single run."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_call_count: int = 0
    cost_by_model: dict[str, float] = field(default_factory=dict)
    cost_by_agent: dict[str, float] = field(default_factory=dict)
    tokens_by_model: dict[str, int] = field(default_factory=dict)
    tokens_by_agent: dict[str, int] = field(default_factory=dict)


class CostAggregator:
    """EventBus subscriber that accumulates cost metrics per run.

    Usage:
        aggregator = CostAggregator(registry=cost_registry)
        event_bus.subscribe(aggregator.on_event, [EventType.LLM_CALLED])

        # After run completes:
        summary = aggregator.get_summary(run_id)
    """

    def __init__(self, registry: Any = None) -> None:
        self._runs: dict[str, RunCostSummary] = {}
        self._registry = registry  # Optional: recalculate cost from registry

    def on_event(self, event: WorkflowEvent) -> None:
        """Handle LLMCalled events. Sync callback for EventBus."""
        if not isinstance(event, LLMCalled):
            return

        summary = self._runs.setdefault(event.run_id, RunCostSummary())

        # Use event's cost_usd (already calculated by provider)
        # Optionally recalculate from registry if available
        cost = event.cost_usd
        if self._registry and cost == 0.0 and event.model:
            cost = self._registry.calculate_cost(
                event.model, event.input_tokens, event.output_tokens
            )

        summary.total_input_tokens += event.input_tokens
        summary.total_output_tokens += event.output_tokens
        summary.total_tokens += event.input_tokens + event.output_tokens
        summary.total_cost_usd += cost
        summary.llm_call_count += 1

        # Attribution breakdowns
        if event.model:
            summary.cost_by_model[event.model] = (
                summary.cost_by_model.get(event.model, 0.0) + cost
            )
            summary.tokens_by_model[event.model] = (
                summary.tokens_by_model.get(event.model, 0)
                + event.input_tokens + event.output_tokens
            )
        if event.agent_name:
            summary.cost_by_agent[event.agent_name] = (
                summary.cost_by_agent.get(event.agent_name, 0.0) + cost
            )
            summary.tokens_by_agent[event.agent_name] = (
                summary.tokens_by_agent.get(event.agent_name, 0)
                + event.input_tokens + event.output_tokens
            )

    def get_summary(self, run_id: str) -> RunCostSummary:
        """Get accumulated cost summary for a run."""
        return self._runs.get(run_id, RunCostSummary())

    def clear(self, run_id: str) -> None:
        """Remove cost data for a completed run."""
        self._runs.pop(run_id, None)
```

**Wiring into compiled.py** (additive, ~10 lines):
```python
# In CompiledGraph._run_loop(), after EventBus creation:
cost_aggregator = CostAggregator(registry=self._cost_registry)
event_bus.subscribe(cost_aggregator.on_event, [EventType.LLM_CALLED])

# Before emitting ExecutionCompleted:
cost_summary = cost_aggregator.get_summary(effective_run_id)
await event_bus.emit(
    ExecutionCompleted(
        run_id=effective_run_id,
        sequence=event_bus.next_sequence(effective_run_id),
        final_state=final_state_dict,
        duration_ms=duration_ms,
        total_tokens=cost_summary.total_tokens,      # Was 0
        total_cost_usd=cost_summary.total_cost_usd,  # Was 0
        status="completed",
    )
)
```

### Pattern 3: BudgetPolicy (Enforcement)

**What:** Pre-call budget check with soft limits (log warning) and hard limits (raise `BudgetExceededError`).

```python
# src/orchestra/cost/budget.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from orchestra.core.errors import OrchestraError


class BudgetExceededError(OrchestraError):
    """Raised when a hard budget limit is exceeded."""
    pass


@dataclass
class BudgetPolicy:
    """Budget limits for a workflow run.

    Usage:
        policy = BudgetPolicy(
            soft_limit_usd=0.50,   # Warn at $0.50
            hard_limit_usd=1.00,   # Abort at $1.00
            soft_limit_tokens=50_000,
            hard_limit_tokens=100_000,
        )
    """
    soft_limit_usd: float | None = None
    hard_limit_usd: float | None = None
    soft_limit_tokens: int | None = None
    hard_limit_tokens: int | None = None
    on_soft_limit: Literal["warn", "downgrade"] = "warn"
    downgrade_model: str | None = None  # Model to switch to when downgrading

    def check(
        self,
        current_cost_usd: float,
        current_tokens: int,
    ) -> BudgetCheckResult:
        """Check current usage against budget limits.

        Returns a result indicating the action to take.
        """
        # Hard limits - abort
        if self.hard_limit_usd is not None and current_cost_usd >= self.hard_limit_usd:
            return BudgetCheckResult(
                action="abort",
                reason=f"Hard budget limit exceeded: ${current_cost_usd:.4f} >= ${self.hard_limit_usd:.4f}",
            )
        if self.hard_limit_tokens is not None and current_tokens >= self.hard_limit_tokens:
            return BudgetCheckResult(
                action="abort",
                reason=f"Hard token limit exceeded: {current_tokens:,} >= {self.hard_limit_tokens:,}",
            )

        # Soft limits - warn or downgrade
        if self.soft_limit_usd is not None and current_cost_usd >= self.soft_limit_usd:
            action = "downgrade" if self.on_soft_limit == "downgrade" else "warn"
            return BudgetCheckResult(
                action=action,
                reason=f"Soft budget limit reached: ${current_cost_usd:.4f} >= ${self.soft_limit_usd:.4f}",
                downgrade_model=self.downgrade_model if action == "downgrade" else None,
            )
        if self.soft_limit_tokens is not None and current_tokens >= self.soft_limit_tokens:
            action = "downgrade" if self.on_soft_limit == "downgrade" else "warn"
            return BudgetCheckResult(
                action=action,
                reason=f"Soft token limit reached: {current_tokens:,} >= {self.soft_limit_tokens:,}",
                downgrade_model=self.downgrade_model if action == "downgrade" else None,
            )

        return BudgetCheckResult(action="allow")


@dataclass
class BudgetCheckResult:
    """Result of a budget check."""
    action: Literal["allow", "warn", "downgrade", "abort"]
    reason: str = ""
    downgrade_model: str | None = None
```

**Enforcement integration point** -- in `agent.py` before the LLM call:
```python
# Before calling provider.complete():
if context.budget_policy is not None:
    summary = context.cost_aggregator.get_summary(context.run_id)
    result = context.budget_policy.check(summary.total_cost_usd, summary.total_tokens)
    if result.action == "abort":
        raise BudgetExceededError(result.reason)
    elif result.action == "warn":
        logger.warning("budget_soft_limit", reason=result.reason, run_id=context.run_id)
    elif result.action == "downgrade" and result.downgrade_model:
        use_model = result.downgrade_model  # Override the model for this call
```

### Pattern 4: Cost Attribution in Parallel Execution

**What:** When agents run in parallel via `_execute_parallel`, each `LLMCalled` event carries `agent_name` and `node_id` already. The `CostAggregator` naturally handles this because:
1. All parallel tasks share the same `context.run_id`
2. Each task has a distinct `context.node_id` (set in `_execute_node`)
3. `LLMCalled` events carry `agent_name` from the agent instance

No special handling needed. The `cost_by_agent` and `cost_by_model` dicts in `RunCostSummary` accumulate correctly regardless of execution order.

### Anti-Patterns to Avoid

- **Anti-pattern: Counting tokens client-side for cost.** Providers return actual token counts in responses. Use those for billing/cost. Only use client-side counting (tiktoken) for pre-call budget estimation.
- **Anti-pattern: Importing litellm just for pricing.** The litellm package has 50+ transitive dependencies. Vendor the JSON pricing file instead.
- **Anti-pattern: Blocking on budget checks in the hot path.** Budget checks should be O(1) dict lookups, not async calls. The `CostAggregator.get_summary()` is synchronous by design.
- **Anti-pattern: Storing cost data separately from events.** Cost data already lives in `LLMCalled` events. The aggregator is a view, not a second source of truth.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model pricing data | Custom scraper or hardcoded dicts | LiteLLM's `model_prices_and_context_window.json` (vendored) | 700+ models, community-maintained, MIT license, updated weekly |
| OpenAI token counting | Character-based heuristic (current `len(content) // 4`) | `tiktoken` library | Exact BPE tokenizer, handles message overhead, ~100x more accurate |
| Rate limiting algorithms | Custom token bucket | `asyncio.Semaphore` + simple counter | Asyncio-native, no external deps; real rate limiting is the API provider's job |
| OTel metric definitions | Custom metric names | OpenTelemetry `gen_ai.*` semantic conventions | Emerging standard, compatible with OTel dashboards |

**Key insight:** The hardest part of cost management is not the code -- it is keeping pricing data current. LiteLLM's JSON file solves this; everything else is straightforward aggregation.

---

## Token Counting Strategy

### Provider-Returned Counts (Primary -- Use for Billing)

All four Orchestra providers already extract token counts from API responses:

| Provider | Response Field | Status |
|----------|---------------|--------|
| HttpProvider (OpenAI) | `usage.prompt_tokens`, `usage.completion_tokens` | Working |
| AnthropicProvider | `usage.input_tokens`, `usage.output_tokens` | Working |
| GoogleProvider | `usageMetadata.promptTokenCount`, `usageMetadata.candidatesTokenCount` | Working |
| OllamaProvider | `usage.prompt_tokens`, `usage.completion_tokens` | Working (cost=0) |

These are the authoritative counts for cost calculation. No external library needed.

### Pre-Call Estimation (Secondary -- Use for Budget Pre-Checks)

For budget enforcement, you need to estimate tokens BEFORE making the call:

| Approach | Accuracy | Speed | When to Use |
|----------|----------|-------|-------------|
| `tiktoken` (OpenAI models) | Exact | Fast (Rust-based) | Pre-call budget check for OpenAI/compatible models |
| `len(text) // 4` heuristic | ~75% accurate | Instant | Quick estimate, fallback for unknown models |
| Anthropic `messages.countTokens` API | Exact | Requires API call | Only when precision matters and latency is acceptable |

**Recommendation:** Use `tiktoken` as an optional dependency for pre-call estimation. Fall back to `len // 4` if not installed. Post-call, always use provider-returned counts.

### tiktoken Integration

```python
# Optional import pattern matching Orchestra conventions
def estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    """Estimate token count. Uses tiktoken if available, else heuristic."""
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except (ImportError, KeyError):
        # Fallback: ~4 chars per token + message overhead
        return len(text) // 4 + 4
```

---

## Budget Enforcement Patterns

### Architecture (Four Components)

Based on Portkey and LiteLLM patterns:

```
1. Usage Logger     -- CostAggregator (EventBus subscriber)
2. Budget Manager   -- BudgetPolicy (dataclass with check())
3. Enforcement      -- Pre-call check in agent.py
4. Alerting         -- structlog warnings + optional OTel metrics
```

### Per-Run Budget (Phase 3 Scope)

```python
# Pass budget via ExecutionContext config
context = ExecutionContext(
    run_id="...",
    config={
        "budget": {
            "soft_limit_usd": 0.50,
            "hard_limit_usd": 1.00,
        }
    }
)
```

### Per-Tenant Budget (Phase 4 Scope -- Design Now, Implement Later)

Multi-tenant budgets require persistent storage:

```python
# Future: TenantBudgetManager (Phase 4)
class TenantBudgetManager:
    """Track cumulative spend per tenant across multiple runs."""

    async def check_tenant_budget(self, tenant_id: str) -> BudgetCheckResult:
        """Check tenant's remaining budget from persistent storage."""
        ...

    async def record_spend(self, tenant_id: str, amount_usd: float) -> None:
        """Record spend after run completion."""
        ...
```

Design the `BudgetPolicy` interface now so it can be extended for tenant budgets in Phase 4 without breaking changes.

### Cost-Aware Model Downgrade

When soft limit is hit, automatically switch to a cheaper model:

```python
# Downgrade chains (configure per use case)
DOWNGRADE_CHAIN = {
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4-6": "claude-haiku-4-5-20251001",
    "gpt-4o": "gpt-4o-mini",
    "gemini-2.5-pro-preview-06-05": "gemini-2.0-flash",
}
```

This is optional behavior, disabled by default, enabled via `BudgetPolicy(on_soft_limit="downgrade", downgrade_model="gpt-4o-mini")`.

---

## OTel Metrics for Cost (Integration with Task 3.2)

### Metric Definitions (OpenTelemetry gen_ai Semantic Conventions)

```python
from opentelemetry import metrics

meter = metrics.get_meter("orchestra.cost")

# Counters
llm_token_counter = meter.create_counter(
    "gen_ai.client.token.usage",
    unit="token",
    description="Number of tokens used by LLM calls",
)

llm_cost_counter = meter.create_counter(
    "gen_ai.client.cost",
    unit="usd",
    description="Estimated cost of LLM calls in USD",
)

# Histograms
run_cost_histogram = meter.create_histogram(
    "orchestra.run.cost",
    unit="usd",
    description="Cost distribution per workflow run",
)

run_token_histogram = meter.create_histogram(
    "orchestra.run.tokens",
    unit="token",
    description="Token usage distribution per workflow run",
)
```

### Attributes (Labels)

```python
# Per LLM call
llm_token_counter.add(
    input_tokens + output_tokens,
    attributes={
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.token.type": "input",  # or "output"
        "orchestra.agent.name": "researcher",
        "orchestra.run.id": run_id,
    },
)

# Per run completion
run_cost_histogram.record(
    total_cost_usd,
    attributes={
        "orchestra.workflow.name": "research_pipeline",
        "orchestra.run.status": "completed",
    },
)
```

### Implementation Note

OTel metrics export is additive -- it goes into the CostAggregator or a separate OTel subscriber. It should be gated on whether `opentelemetry-sdk` is installed (same optional dependency pattern as the OTel tracing task 3.2).

---

## Cost-Aware Routing (Future -- Phase 4)

Document the pattern now so the registry design supports it, but do not implement in Phase 3.

**Core idea:** Route simple tasks to cheap models, complex tasks to expensive ones.

```python
# Phase 4 concept
class CostAwareRouter:
    """Select model based on task complexity and remaining budget."""

    def select_model(
        self,
        task_complexity: Literal["simple", "moderate", "complex"],
        remaining_budget_usd: float,
        preferred_model: str,
    ) -> str:
        # If budget is low, always use cheapest available
        if remaining_budget_usd < 0.01:
            return self._cheapest_model()
        # Route based on complexity
        if task_complexity == "simple":
            return "gpt-4o-mini"  # ~$0.15/1M input tokens
        return preferred_model
```

**Phase 3 preparation:** Ensure `ModelCostRegistry` exposes `get()` so a future router can compare costs across models.

---

## Common Pitfalls

### Pitfall 1: Stale Pricing Data
**What goes wrong:** Hardcoded prices become wrong when providers update pricing (happens 2-4x per year per provider).
**Why it happens:** Orchestra currently has prices hardcoded in 3 separate provider files.
**How to avoid:** Centralize in `ModelCostRegistry` with a single JSON file. Document update process. Consider a CLI command `orchestra update-prices` that fetches latest from LiteLLM's repo.
**Warning signs:** Cost reports showing $0.00 for known paid models.

### Pitfall 2: Missing Cost for Unknown Models
**What goes wrong:** User configures a model not in the registry; all costs report as $0.00.
**Why it happens:** `get()` returns zero-cost default for unknown models.
**How to avoid:** Log a warning when a model is not found in the registry. Return the zero-cost `ModelPricing` but emit a structlog warning so users know their costs are not being tracked.

### Pitfall 3: Double-Counting in Parallel Execution
**What goes wrong:** If the aggregator is not idempotent, replayed events could double-count.
**Why it happens:** EventBus replays during time-travel debugging.
**How to avoid:** The `CostAggregator` should only count events with `replay_mode=False` (matching the existing pattern in `agent.py` line 114: `if context.event_bus is not None and not _replay`). Events emitted during replay already skip LLM calls.

### Pitfall 4: Budget Check Race Condition in Parallel
**What goes wrong:** Two parallel agents check budget, both pass, both call LLM, total exceeds limit.
**Why it happens:** Budget check and LLM call are not atomic.
**How to avoid:** Accept this as a known limitation for Phase 3. In parallel execution, the hard limit may be exceeded by up to `N * max_single_call_cost` where N is parallelism. Document this. For strict enforcement, require serial execution.

### Pitfall 5: Streaming Responses and Cost
**What goes wrong:** Streaming responses do not include token counts until the final chunk.
**Why it happens:** Providers send usage in the final SSE event, not in each chunk.
**How to avoid:** Cost aggregation happens via `LLMCalled` events, which are emitted after the full response is received. Streaming does not affect cost tracking. However, budget pre-checks cannot account for output tokens during streaming.

---

## Bundled Pricing Data

### Format (_default_prices.json)

Use a subset of LiteLLM's format, covering models Orchestra providers support:

```json
{
  "gpt-4o": {
    "input_cost_per_token": 0.0000025,
    "output_cost_per_token": 0.00001,
    "max_input_tokens": 128000,
    "max_output_tokens": 16384,
    "litellm_provider": "openai"
  },
  "gpt-4o-mini": {
    "input_cost_per_token": 0.00000015,
    "output_cost_per_token": 0.0000006,
    "max_input_tokens": 128000,
    "max_output_tokens": 16384,
    "litellm_provider": "openai"
  },
  "claude-opus-4-6": {
    "input_cost_per_token": 0.000015,
    "output_cost_per_token": 0.000075,
    "max_input_tokens": 200000,
    "max_output_tokens": 32000,
    "litellm_provider": "anthropic"
  },
  "claude-sonnet-4-6": {
    "input_cost_per_token": 0.000003,
    "output_cost_per_token": 0.000015,
    "max_input_tokens": 200000,
    "max_output_tokens": 64000,
    "litellm_provider": "anthropic"
  },
  "gemini-2.0-flash": {
    "input_cost_per_token": 0.0000001,
    "output_cost_per_token": 0.0000004,
    "max_input_tokens": 1048576,
    "max_output_tokens": 8192,
    "litellm_provider": "google"
  }
}
```

### Update Process

1. Fetch latest from `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`
2. Filter to models Orchestra supports (or all, file is ~200KB)
3. Commit updated `_default_prices.json`
4. Optionally: CLI command `orchestra update-prices` for users

---

## Migration Path: Provider _MODEL_COSTS Dicts

### Current State (Scattered)

```python
# http.py
_MODEL_COSTS = {"gpt-4o": (0.0025, 0.01), ...}  # per 1K tokens

# anthropic.py
_MODEL_COSTS = {"claude-opus-4-6": (0.015, 0.075), ...}  # per 1K tokens

# google.py
_MODEL_COSTS = {"gemini-2.0-flash": (0.0001, 0.0004), ...}  # per 1K tokens
```

### Migration Plan

1. Create `ModelCostRegistry` with bundled JSON
2. Modify each provider's `get_model_cost()` to delegate to registry:
   ```python
   def get_model_cost(self, model: str | None = None) -> ModelCost:
       m = model or self._default_model
       pricing = _GLOBAL_REGISTRY.get(m)
       return ModelCost(
           input_cost_per_1k=pricing.input_cost_per_token * 1000,
           output_cost_per_1k=pricing.output_cost_per_token * 1000,
       )
   ```
3. Remove per-provider `_MODEL_COSTS` dicts
4. Keep `ModelCost` type for backward compatibility

---

## Existing Implementations Reference

### How Observability Platforms Track Costs

| Platform | Architecture | Cost Tracking Method |
|----------|-------------|---------------------|
| **Helicone** | Proxy-based (sits between app and LLM API) | Intercepts requests/responses, calculates cost from response usage + pricing DB |
| **Portkey** | Gateway + SDK | Request logging with cost calculation, per-key/team budget enforcement |
| **LangSmith** | SDK instrumentation | Callback-based, traces carry token counts, cost calculated from model registry |
| **Langfuse** | SDK + API | Event-based ingestion, cost calculated server-side from pricing tables |

**Orchestra's approach aligns with LangSmith/Langfuse:** event-based (EventBus subscribers), cost calculated from provider responses + registry, no proxy layer needed.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded per-provider pricing | Centralized JSON registry (LiteLLM format) | 2024 | Single update point, 700+ models |
| tiktoken for all providers | Provider-returned counts + tiktoken for estimation | 2024 | More accurate billing |
| Manual cost spreadsheets | OTel metrics + dashboards | 2025 | Real-time visibility |
| Flat budget caps | Tiered soft/hard limits with model downgrade | 2025 | Graceful degradation |
| Per-model pricing only | Per-token-type pricing (reasoning tokens, audio, etc.) | 2025 | Accurate for o1/o3 reasoning models |

**Note on reasoning tokens:** Models like o1 and o3 have separate `output_cost_per_reasoning_token` pricing. Orchestra does not currently track reasoning vs. output tokens separately. This is a future consideration but not blocking for Phase 3.

---

## Open Questions

1. **Should `ModelCostRegistry` be a singleton or instance?**
   - Recommendation: Module-level default instance (`_GLOBAL_REGISTRY`) with option to pass custom registry to `CostAggregator`. Matches how structlog loggers work.

2. **How often should bundled pricing be updated?**
   - Recommendation: Update `_default_prices.json` quarterly or when adding new provider support. Not a runtime concern.

3. **Should budget policy live on ExecutionContext or CompiledGraph?**
   - Recommendation: `ExecutionContext.config["budget"]` -- per-run, set by caller. Not on the graph itself (different runs of the same graph may have different budgets).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/test_cost.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| COST-01 | ModelCostRegistry loads JSON and returns pricing | unit | `pytest tests/unit/test_cost.py::test_registry_load -x` |
| COST-02 | CostAggregator accumulates LLMCalled events | unit | `pytest tests/unit/test_cost.py::test_aggregator_accumulates -x` |
| COST-03 | ExecutionCompleted gets populated total_cost_usd | unit | `pytest tests/unit/test_cost.py::test_completed_event_has_cost -x` |
| COST-04 | BudgetPolicy soft limit triggers warning | unit | `pytest tests/unit/test_cost.py::test_soft_limit_warn -x` |
| COST-05 | BudgetPolicy hard limit raises BudgetExceededError | unit | `pytest tests/unit/test_cost.py::test_hard_limit_abort -x` |
| COST-06 | Unknown model returns zero cost with warning | unit | `pytest tests/unit/test_cost.py::test_unknown_model_warning -x` |
| COST-07 | Parallel execution cost attribution is correct | unit | `pytest tests/unit/test_cost.py::test_parallel_attribution -x` |
| COST-08 | Provider get_model_cost delegates to registry | unit | `pytest tests/unit/test_cost.py::test_provider_delegates -x` |

### Wave 0 Gaps
- [ ] `tests/unit/test_cost.py` -- all cost management tests (new file)
- [ ] `src/orchestra/cost/` -- entire module is new

---

## Sources

### Primary (HIGH confidence)
- Orchestra codebase: `src/orchestra/providers/*.py`, `src/orchestra/storage/events.py`, `src/orchestra/core/types.py` -- direct source analysis
- Orchestra codebase: `src/orchestra/core/agent.py` lines 107-136 -- LLMCalled event emission
- Orchestra codebase: `src/orchestra/storage/store.py` -- EventBus subscriber pattern
- Orchestra codebase: `src/orchestra/core/compiled.py` -- ExecutionCompleted emission

### Secondary (MEDIUM-HIGH confidence)
- [LiteLLM model_prices_and_context_window.json](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) -- pricing data format and schema
- [LiteLLM Token Usage & Cost docs](https://docs.litellm.ai/docs/completion/token_usage) -- cost calculation patterns
- [LiteLLM Add Model Pricing docs](https://docs.litellm.ai/docs/provider_registration/add_model_pricing) -- registry pattern
- [OpenTelemetry Gen_AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/) -- metric naming
- [tiktoken GitHub](https://github.com/openai/tiktoken) -- token counting
- [Portkey Budget Limits Blog](https://portkey.ai/blog/budget-limits-and-alerts-in-llm-apps/) -- four-component budget architecture
- [Token Counting Guide 2025](https://www.propelcode.ai/blog/token-counting-tiktoken-anthropic-gemini-guide-2025) -- cross-provider counting

### Tertiary (MEDIUM confidence)
- [tokencost PyPI](https://pypi.org/project/tokencost/) -- evaluated and rejected (stale pricing, extra deps)
- [Helicone vs Competitors Guide](https://www.helicone.ai/blog/the-complete-guide-to-LLM-observability-platforms) -- observability platform comparison
- [RouteLLM cost-aware routing](https://zilliz.com/learn/routellm-open-source-framework-for-navigate-cost-quality-trade-offs-in-llm-deployment) -- routing patterns (Phase 4)
- [OTel LLM Observability Blog](https://opentelemetry.io/blog/2024/llm-observability/) -- OTel integration patterns

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new runtime dependencies, builds on existing EventBus pattern
- Architecture: HIGH -- all integration points verified against source code
- Pricing registry: HIGH -- LiteLLM format is industry standard with 700+ models
- Budget enforcement: HIGH -- straightforward pre-call check pattern
- OTel metrics: MEDIUM-HIGH -- depends on Task 3.2 (OTel integration) being implemented first
- Cost-aware routing: MEDIUM -- Phase 4 material, design only

**Research date:** 2026-03-10
**Valid until:** 2026-06-10 (pricing data may change, architecture patterns are stable)
