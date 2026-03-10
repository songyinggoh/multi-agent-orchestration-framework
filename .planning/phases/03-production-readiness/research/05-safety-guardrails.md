# Safety & Guardrails - Research

**Researched:** 2026-03-10
**Domain:** LLM safety, input/output guardrails, rate limiting, circuit breakers, content filtering
**Confidence:** HIGH

## Summary

Orchestra already has strong foundational security: `ToolACL` for tool authorization, `PromptInjectionAgent` with Rebuff for prompt injection detection (4-layer: heuristics, LLM, VectorDB, canary tokens), `SelfCheckAgent` / `FactScorerAgent` for hallucination detection, and event-based audit trails via `SecurityViolation` events. The gap is a **composable guardrail pipeline** that chains multiple validators (input sanitization, output validation, content filtering, PII redaction) with configurable fail-safe strategies (retry, fallback, block), plus **operational safety** (rate limiting, circuit breakers, token budgets).

The recommended approach is to build a lightweight, Orchestra-native guardrail framework inspired by the OpenAI Agents SDK pattern (decorator-based `@input_guardrail` / `@output_guardrail` with tripwire semantics) rather than taking a heavy dependency on Guardrails AI or NeMo Guardrails. For content filtering, integrate Microsoft Presidio (PII) as an optional dependency. For circuit breakers, use `tenacity` (already well-known in the Python ecosystem) with a simple custom circuit breaker. For rate limiting, build a token-bucket implementation in-process, with `slowapi` reserved for the FastAPI layer.

**Primary recommendation:** Build a composable `GuardrailChain` that wraps validators with `OnFail` strategies (BLOCK, FIX, RETRY, LOG), integrate Presidio for PII, and add per-agent token budgets and circuit breakers to the provider layer.

## Existing Orchestra Infrastructure

Before designing new features, here is what already exists:

### Security Module (`orchestra.security`)
| Component | What It Does | Integration Point |
|-----------|-------------|-------------------|
| `ToolACL` | Pattern-matching allow/deny lists for tool access | `BaseAgent._execute_tool()` |
| `PromptInjectionAgent` | Rebuff 4-layer injection detection | BaseAgent subclass, wraps `run()` |
| `InjectionAuditorAgent` | Standalone injection checker node | Graph node, reads state |
| `make_injection_guard_node()` | Factory for injection guard nodes | Graph node function |
| `rebuff_tool()` | Inline injection checking tool | Agent tool |

### Reliability Module (`orchestra.reliability`)
| Component | What It Does | Integration Point |
|-----------|-------------|-------------------|
| `SelfChecker` / `SelfCheckAgent` | SelfCheckGPT hallucination detection (NLI, BERTScore, N-gram, LLM) | BaseAgent subclass or graph node |
| `FactScoreChecker` / `FactScorerAgent` | Retrieval-augmented factual grounding | BaseAgent subclass or graph node |
| `make_selfcheck_node()` / `make_factscore_node()` | Graph node factories | Graph node functions |
| `selfcheck_tool()` / `factscore_tool()` | Inline checking tools | Agent tools |

### Events
| Event | Purpose |
|-------|---------|
| `SecurityViolation` | Emitted when ACL blocks a tool call |
| `OutputRejected` | Emitted when output fails validation |

### Key Pattern: Three Integration Surfaces
Orchestra reliability/security modules consistently expose:
1. **BaseAgent subclass** -- wraps `run()` for automatic checking
2. **Standalone graph node** -- wire into workflow for explicit checking
3. **Tool** -- agent can call during reasoning loop

New guardrail features MUST follow this same triple-surface pattern.

---

## Standard Stack

### Core (Already Dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | >=2.5 | Schema validation, structured output | Already core dependency |
| `structlog` | >=24.0 | Structured logging for security events | Already core dependency |
| `tenacity` | >=8.2 | Retry with exponential backoff, stop conditions | De facto Python retry library, 10K+ GitHub stars |

### Supporting (New Optional Dependencies)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `presidio-analyzer` | >=2.2 | PII entity detection (NER + regex + context) | When PII redaction is needed |
| `presidio-anonymizer` | >=2.2 | PII anonymization (redact, mask, hash, encrypt) | Paired with analyzer |
| `slowapi` | >=0.1.9 | HTTP-level rate limiting for FastAPI | Phase 3.1 FastAPI server only |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom guardrail chain | Guardrails AI (v0.7.2) | Guardrails AI is feature-rich but heavyweight (~50 transitive deps), has its own Hub ecosystem, and its `Guard.parse()` / reask flow assumes direct LLM control. Orchestra already has its own provider layer. Too much overlap, too much weight. |
| Custom guardrail chain | NeMo Guardrails | Colang DSL is powerful for conversational systems but opinionated about LLM routing. Requires config files, its own server mode. Poor fit for Orchestra's graph-based execution model. |
| Custom circuit breaker | `pybreaker` / `aiobreaker` | pybreaker lacks native asyncio. aiobreaker works but is a small library with limited maintenance. A simple 50-line circuit breaker integrated with tenacity is more maintainable. |
| Presidio for PII | Guardrails AI `DetectPII` validator | Guardrails' PII validator wraps Presidio anyway. Direct Presidio integration avoids the Guardrails AI dependency. |

**Installation (new optional deps):**
```bash
pip install tenacity                         # retry + backoff
pip install presidio-analyzer presidio-anonymizer  # PII detection
pip install slowapi                           # FastAPI rate limiting (Phase 3.1 only)
```

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
guardrails = ["tenacity>=8.2"]
pii = ["presidio-analyzer>=2.2", "presidio-anonymizer>=2.2"]
```

---

## Architecture Patterns

### Recommended Project Structure
```
src/orchestra/
  security/
    __init__.py
    acl.py              # existing -- ToolACL
    rebuff.py           # existing -- prompt injection (Rebuff)
    guardrails.py       # NEW -- GuardrailChain, @input_guardrail, @output_guardrail
    validators.py       # NEW -- built-in validators (PII, toxicity, length, regex)
    pii.py              # NEW -- Presidio wrapper (optional dep)
    rate_limit.py       # NEW -- TokenBucket, per-agent rate limiter
    circuit_breaker.py  # NEW -- async circuit breaker for LLM providers
  reliability/
    ...                 # existing -- selfcheck, factscore (hallucination detection)
```

### Pattern 1: Composable Guardrail Chain

**What:** A chain of validators that run sequentially on input or output, each returning PASS or FAIL with an `OnFail` action.

**When to use:** Any agent that needs multi-layer validation (PII + injection + length + custom).

**Design (inspired by OpenAI Agents SDK tripwire pattern + Guardrails AI OnFailAction):**

```python
from enum import Enum
from typing import Any, Protocol
from pydantic import BaseModel


class OnFail(str, Enum):
    """Action to take when a guardrail fails."""
    BLOCK = "block"       # Stop execution, return error
    FIX = "fix"           # Apply fix_value and continue
    LOG = "log"           # Log warning and continue (NOOP)
    RETRY = "retry"       # Re-prompt the LLM with error feedback
    EXCEPTION = "exception"  # Raise GuardrailViolation


class GuardrailResult(BaseModel):
    """Result from a single guardrail check."""
    passed: bool
    validator_name: str
    message: str = ""
    fix_value: str | None = None  # Used when on_fail=FIX
    metadata: dict[str, Any] = {}


class Guardrail(Protocol):
    """Protocol for guardrail validators."""
    name: str
    on_fail: OnFail

    async def validate(self, text: str, context: dict[str, Any] | None = None) -> GuardrailResult:
        ...


class GuardrailChain:
    """Compose multiple guardrails into a sequential validation pipeline."""

    def __init__(self, guardrails: list[Guardrail]):
        self._guardrails = guardrails

    async def run(self, text: str, context: dict[str, Any] | None = None) -> tuple[str, list[GuardrailResult]]:
        """Run all guardrails. Returns (possibly_fixed_text, results).

        Raises GuardrailViolation if any guardrail with on_fail=BLOCK or EXCEPTION fails.
        """
        results: list[GuardrailResult] = []
        current_text = text

        for guard in self._guardrails:
            result = await guard.validate(current_text, context)
            results.append(result)

            if not result.passed:
                match guard.on_fail:
                    case OnFail.BLOCK:
                        raise GuardrailViolation(result)
                    case OnFail.EXCEPTION:
                        raise GuardrailViolation(result)
                    case OnFail.FIX:
                        if result.fix_value is not None:
                            current_text = result.fix_value
                    case OnFail.LOG:
                        pass  # Continue, logged by structlog
                    case OnFail.RETRY:
                        raise RetryRequested(result)

        return current_text, results
```

### Pattern 2: Guardrail-Aware Agent (BaseAgent Subclass)

**What:** A BaseAgent subclass that runs input guardrails before LLM call and output guardrails after.

**When to use:** Drop-in replacement for any agent needing safety.

```python
class GuardedAgent(BaseAgent):
    """Agent with configurable input and output guardrail chains."""

    input_guardrails: list[Guardrail] = []
    output_guardrails: list[Guardrail] = []
    max_retries: int = 2

    async def run(self, input: str | list[Message], context: ExecutionContext) -> AgentResult:
        # 1. Run input guardrails
        user_text = self._extract_user_text(input)
        input_chain = GuardrailChain(self.input_guardrails)
        sanitized, input_results = await input_chain.run(user_text)

        # 2. Run base agent with sanitized input
        result = await super().run(sanitized, context)

        # 3. Run output guardrails with retry
        output_chain = GuardrailChain(self.output_guardrails)
        for attempt in range(self.max_retries + 1):
            try:
                validated_output, output_results = await output_chain.run(result.output)
                result.output = validated_output
                break
            except RetryRequested as e:
                if attempt < self.max_retries:
                    # Re-prompt with error feedback
                    result = await super().run(
                        f"Your previous response failed validation: {e.result.message}. "
                        f"Please try again.",
                        context,
                    )
                else:
                    raise GuardrailViolation(e.result)

        # 4. Annotate result with guardrail metadata
        result.state_updates["guardrails"] = {
            "input": [r.model_dump() for r in input_results],
            "output": [r.model_dump() for r in output_results],
        }
        return result
```

### Pattern 3: Decorator-Based Guardrails (OpenAI Agents SDK Style)

**What:** Function decorators that register guardrails on agents.

**When to use:** Rapid prototyping, simple one-off checks.

```python
from functools import wraps

def input_guardrail(func):
    """Decorator to register an async function as an input guardrail."""
    func._is_input_guardrail = True
    return func

def output_guardrail(func):
    """Decorator to register an async function as an output guardrail."""
    func._is_output_guardrail = True
    return func

# Usage:
@input_guardrail
async def check_length(text: str, context: dict) -> GuardrailResult:
    if len(text) > 10000:
        return GuardrailResult(passed=False, validator_name="length_check",
                                message="Input exceeds 10K characters")
    return GuardrailResult(passed=True, validator_name="length_check")
```

### Pattern 4: Circuit Breaker for LLM Providers

**What:** Async circuit breaker wrapping provider `complete()` calls with three states: CLOSED (normal), OPEN (failing, fast-fail), HALF-OPEN (probing).

**When to use:** Multi-provider setups where one provider may go down.

```python
import asyncio
import time
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class AsyncCircuitBreaker:
    """Lightweight async circuit breaker for LLM providers."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,  # seconds
        half_open_max_calls: int = 1,
    ):
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._half_open_max = half_open_max_calls
        self._half_open_calls = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    async def call(self, coro):
        """Execute coroutine through circuit breaker."""
        async with self._lock:
            current = self.state
            if current == CircuitState.OPEN:
                raise CircuitOpenError(f"Circuit open, retry after {self._reset_timeout}s")
            if current == CircuitState.HALF_OPEN and self._half_open_calls >= self._half_open_max:
                raise CircuitOpenError("Circuit half-open, max probe calls reached")
            if current == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            result = await coro
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self):
        async with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    async def _on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
```

### Pattern 5: Token Budget / Rate Limiter

**What:** Per-agent or per-user token budget tracking with token-bucket rate limiting.

**When to use:** Cost control, preventing runaway agents.

```python
import asyncio
import time

class TokenBudget:
    """Track and enforce token budgets per agent/user/run."""

    def __init__(self, max_tokens: int, window_seconds: float = 3600.0):
        self._max_tokens = max_tokens
        self._window = window_seconds
        self._usage: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int) -> None:
        """Record token usage. Raises BudgetExceededError if over limit."""
        async with self._lock:
            now = time.monotonic()
            # Prune expired entries
            self._usage = [(t, n) for t, n in self._usage if now - t < self._window]
            total = sum(n for _, n in self._usage)
            if total + tokens > self._max_tokens:
                raise BudgetExceededError(
                    f"Token budget exceeded: {total + tokens}/{self._max_tokens} "
                    f"in {self._window}s window"
                )
            self._usage.append((now, tokens))

    @property
    def remaining(self) -> int:
        now = time.monotonic()
        used = sum(n for t, n in self._usage if now - t < self._window)
        return max(0, self._max_tokens - used)
```

### Anti-Patterns to Avoid

- **Monolithic guardrail agent:** Do NOT create a single "SafeAgent" that bundles all checks. Use composable chains so users pick what they need.
- **Synchronous Presidio calls on event loop:** Presidio NER models are CPU-bound. ALWAYS use `asyncio.to_thread()` (already the pattern in `rebuff.py`).
- **Guardrails that silently modify output:** FIX actions MUST be logged. Users must be able to audit what was changed.
- **Circuit breaker without fallback:** An open circuit with no fallback model just fails. Always pair with a fallback strategy.
- **Hardcoded thresholds:** All guardrail thresholds (toxicity scores, PII confidence, token limits) MUST be configurable with sensible defaults.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PII entity detection | Custom regex for SSN/email/phone | `presidio-analyzer` | 50+ entity types, multi-language, NER + regex + context. Custom regex misses edge cases (international phone formats, name detection). |
| Retry with backoff | Custom sleep loops | `tenacity` | Handles jitter, exponential backoff, stop conditions, retry callbacks. Battle-tested at scale. |
| HTTP rate limiting | Custom middleware | `slowapi` (for FastAPI server) | Built on `limits` library, supports Redis/memory backends, standard rate limit headers. |
| JSON schema validation | Custom JSON parsers | `pydantic` (already a dep) | Orchestra already uses `output_type: type[BaseModel]` in `BaseAgent`. Extend, don't replace. |

**Key insight:** Orchestra's existing `output_type` validation via Pydantic is already the right approach for structured output. The guardrail layer adds *semantic* validation (is the content safe/appropriate?) on top of *structural* validation (is the JSON valid?).

---

## Common Pitfalls

### Pitfall 1: Guardrail Ordering Matters
**What goes wrong:** PII redaction runs AFTER injection detection, so injected text with PII leaks during the injection check's LLM call.
**Why it happens:** Guardrails are treated as unordered.
**How to avoid:** Define a canonical ordering: (1) input length/format checks, (2) injection detection, (3) PII redaction, (4) topic adherence. Document the ordering contract.
**Warning signs:** PII appearing in logs from injection detection calls.

### Pitfall 2: Retry Loops with Output Guardrails
**What goes wrong:** Output guardrail fails, agent retries, new output also fails, infinite loop.
**Why it happens:** No max retry limit, or the retry prompt doesn't include enough context about what went wrong.
**How to avoid:** Hard cap retries (default 2). Include the specific validation error in the retry prompt. After max retries, fall back to a safe default response.
**Warning signs:** Token usage spikes, latency spikes on guardrailed agents.

### Pitfall 3: Presidio Model Loading Latency
**What goes wrong:** First PII check takes 3-5 seconds because spaCy NER model loads on first call.
**Why it happens:** Lazy loading of ML models.
**How to avoid:** Pre-load Presidio analyzer at application startup (in FastAPI `lifespan` or graph compilation). Cache the analyzer instance.
**Warning signs:** First request to a PII-guarded agent is much slower than subsequent requests.

### Pitfall 4: Circuit Breaker State Sharing
**What goes wrong:** Each agent instance has its own circuit breaker, so provider failures aren't detected until every agent independently hits the threshold.
**Why it happens:** Circuit breaker instantiated per-agent instead of per-provider.
**How to avoid:** Circuit breakers MUST be scoped to the provider, not the agent. Use a registry: `_breakers: dict[str, AsyncCircuitBreaker]`.
**Warning signs:** Some agents fail while others still send requests to a down provider.

### Pitfall 5: Guardrails Blocking Legitimate Content
**What goes wrong:** Overly aggressive toxicity/injection detection blocks valid user queries.
**Why it happens:** Default thresholds too strict, no way to tune per-use-case.
**How to avoid:** All thresholds configurable. Provide a `LOG` (NOOP) mode for testing guardrails before enforcing. Include a bypass mechanism for trusted internal agents.
**Warning signs:** High false-positive rate in guardrail logs.

### Pitfall 6: Double-Counting Token Usage
**What goes wrong:** Guardrail LLM calls (injection detection, toxicity classification) not tracked separately from agent LLM calls.
**Why it happens:** Guardrail LLM calls go through the same provider without separate tracking.
**How to avoid:** Tag guardrail LLM calls with metadata (`purpose: "guardrail"`) in the event system. Track guardrail token cost separately in `AgentResult`.
**Warning signs:** Token budgets depleted faster than expected, cost attribution is wrong.

---

## Code Examples

### Built-in Validators

```python
# PII Redaction Validator (wraps Presidio)
class PIIRedactionGuardrail:
    """Detect and redact PII using Microsoft Presidio."""

    name: str = "pii_redaction"
    on_fail: OnFail = OnFail.FIX  # Auto-redact by default

    def __init__(
        self,
        entities: list[str] | None = None,  # e.g. ["PHONE_NUMBER", "EMAIL_ADDRESS"]
        language: str = "en",
        score_threshold: float = 0.5,
        on_fail: OnFail = OnFail.FIX,
    ):
        self.on_fail = on_fail
        self._entities = entities
        self._language = language
        self._threshold = score_threshold
        self._analyzer = None
        self._anonymizer = None

    def _ensure_loaded(self):
        if self._analyzer is None:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()

    async def validate(self, text: str, context: dict | None = None) -> GuardrailResult:
        self._ensure_loaded()

        # CPU-bound NER -- run in thread pool
        results = await asyncio.to_thread(
            self._analyzer.analyze,
            text=text,
            entities=self._entities,
            language=self._language,
            score_threshold=self._threshold,
        )

        if not results:
            return GuardrailResult(passed=True, validator_name=self.name)

        # Anonymize for fix_value
        anonymized = await asyncio.to_thread(
            self._anonymizer.anonymize,
            text=text,
            analyzer_results=results,
        )

        detected = [{"type": r.entity_type, "score": r.score} for r in results]
        return GuardrailResult(
            passed=False,
            validator_name=self.name,
            message=f"PII detected: {[d['type'] for d in detected]}",
            fix_value=anonymized.text,
            metadata={"entities": detected},
        )


# Length/Token Limit Validator
class MaxLengthGuardrail:
    """Reject or truncate text exceeding a character/token limit."""

    name: str = "max_length"

    def __init__(self, max_chars: int = 50000, on_fail: OnFail = OnFail.BLOCK):
        self.on_fail = on_fail
        self._max_chars = max_chars

    async def validate(self, text: str, context: dict | None = None) -> GuardrailResult:
        if len(text) <= self._max_chars:
            return GuardrailResult(passed=True, validator_name=self.name)
        return GuardrailResult(
            passed=False,
            validator_name=self.name,
            message=f"Text length {len(text)} exceeds max {self._max_chars}",
            fix_value=text[:self._max_chars] if self.on_fail == OnFail.FIX else None,
        )


# Regex Pattern Validator
class RegexGuardrail:
    """Validate text matches (or doesn't match) a regex pattern."""

    name: str = "regex_check"

    def __init__(self, pattern: str, must_match: bool = True, on_fail: OnFail = OnFail.BLOCK):
        import re
        self.on_fail = on_fail
        self._pattern = re.compile(pattern)
        self._must_match = must_match

    async def validate(self, text: str, context: dict | None = None) -> GuardrailResult:
        matches = bool(self._pattern.search(text))
        passed = matches if self._must_match else not matches
        if passed:
            return GuardrailResult(passed=True, validator_name=self.name)
        return GuardrailResult(
            passed=False,
            validator_name=self.name,
            message=f"Regex {'did not match' if self._must_match else 'matched forbidden pattern'}",
        )
```

### Integrating Circuit Breaker with Provider

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class ResilientProvider:
    """Wraps an LLM provider with circuit breaker and retry logic."""

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ):
        self._primary = primary
        self._fallback = fallback
        self._breaker = breaker or AsyncCircuitBreaker()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )
    async def complete(self, **kwargs) -> LLMResponse:
        try:
            return await self._breaker.call(
                self._primary.complete(**kwargs)
            )
        except CircuitOpenError:
            if self._fallback:
                return await self._fallback.complete(**kwargs)
            raise
```

### Wiring Guardrails in a Workflow

```python
from orchestra.security.guardrails import GuardrailChain, GuardedAgent
from orchestra.security.validators import PIIRedactionGuardrail, MaxLengthGuardrail
from orchestra.security.rebuff import PromptInjectionAgent

# Option 1: GuardedAgent (drop-in)
agent = GuardedAgent(
    name="customer_support",
    model="gpt-4o-mini",
    system_prompt="You are a customer support agent.",
    input_guardrails=[
        MaxLengthGuardrail(max_chars=10000, on_fail=OnFail.BLOCK),
        # Injection detection could be a guardrail too
    ],
    output_guardrails=[
        PIIRedactionGuardrail(on_fail=OnFail.FIX),
    ],
)

# Option 2: Graph node factory (like existing make_selfcheck_node)
pii_guard = make_guardrail_node(
    guardrails=[PIIRedactionGuardrail()],
    input_key="agent_output",
    result_key="guardrail_results",
)
graph.add_node("pii_check", pii_guard)
graph.add_edge("researcher", "pii_check")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Regex-only injection detection | Multi-layer (heuristic + LLM + vector + canary) | 2023-2024 | Orchestra already has this via Rebuff |
| Manual PII regex | NER-based detection (Presidio, Comprehend) | 2022-2023 | 50+ entity types vs ~5 regex patterns |
| Global rate limits | Per-agent token budgets | 2024-2025 | Granular cost control for multi-agent systems |
| Single LLM provider | Circuit breaker + failover | 2024-2025 | Required for production multi-provider setups |
| Post-hoc output review | Inline guardrail chains with retry | 2024-2025 | Guardrails AI, OpenAI Agents SDK, NeMo all converged on this |

**Deprecated/outdated:**
- **LMQL/Guidance constrained decoding:** Interesting research but requires model-level integration. Not practical for API-based LLM providers (which is Orchestra's model). Skip.
- **Rebuff as sole injection defense:** Rebuff requires Pinecone + OpenAI API keys. Provide a lightweight regex/heuristic fallback for users who don't want external dependencies.

---

## External Library Deep Dives

### Guardrails AI (v0.7.2)
- **Architecture:** `Guard().use(Validator(..., on_fail=...))` chain. Validators installed from Hub via CLI (`guardrails hub install hub://guardrails/...`).
- **OnFailAction options:** NOOP (log only), FIX (replace with fix_value), FILTER (drop field), REFRAIN (return nothing), REASK (re-prompt LLM), EXCEPTION (raise).
- **Fit for Orchestra:** POOR. Guardrails AI wants to own the LLM call (`guard(model=..., messages=...)`). Orchestra already owns this via `LLMProvider.complete()`. The validator concept is good but the framework is too opinionated. **Recommendation:** Adopt the *concept* (validator chain + OnFail actions) but build Orchestra-native implementation.
- **Confidence:** HIGH (verified via PyPI, GitHub, official docs)

### NeMo Guardrails (NVIDIA)
- **Architecture:** Config-driven (YAML + Colang files). Colang is a Python-like DSL for dialog flows. Supports input rails, output rails, dialog rails, retrieval rails.
- **Features:** Topical rails (keep conversation on-topic), fact-checking rails (SelfCheckGPT-based, similar to Orchestra's existing `SelfChecker`), jailbreak detection, content safety.
- **Fit for Orchestra:** POOR. NeMo wants to be the conversation orchestrator itself. It has its own server mode, its own LLM routing. Overlaps heavily with Orchestra's core graph engine. Integrating it as a component would require fighting its architecture.
- **Confidence:** HIGH (verified via NVIDIA docs, PyPI, GitHub)

### Microsoft Presidio
- **Architecture:** `AnalyzerEngine` detects entities, `AnonymizerEngine` transforms them. Pluggable NLP backends (spaCy, Stanza, transformers). 50+ built-in entity recognizers.
- **Fit for Orchestra:** EXCELLENT. Pure library, no framework opinions. Wraps cleanly as a guardrail validator. CPU-bound (needs `asyncio.to_thread()`), but this is the established pattern in Orchestra (see `rebuff.py`).
- **Entities:** PERSON, PHONE_NUMBER, EMAIL_ADDRESS, CREDIT_CARD, IBAN, US_SSN, IP_ADDRESS, LOCATION, DATE_TIME, NRP (nationality/religion/political), MEDICAL_LICENSE, URL, and many more.
- **Confidence:** HIGH (Microsoft-maintained, 3K+ GitHub stars, active development)

### Tenacity
- **Architecture:** Decorator-based retry with composable stop/wait/retry conditions.
- **Key features:** `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=60), retry=retry_if_exception_type(RateLimitError))`.
- **Fit for Orchestra:** EXCELLENT. No framework opinions. Wraps any async function. Standard choice for Python retry logic.
- **Confidence:** HIGH (de facto standard, 6K+ GitHub stars)

---

## Open Questions

1. **Should injection detection be a guardrail validator or stay as a separate module?**
   - What we know: `PromptInjectionAgent` already works well as a BaseAgent subclass. Making it also available as a `Guardrail` validator would unify the API.
   - Recommendation: Create a `RebuffGuardrail` adapter that wraps `RebuffChecker` as a `Guardrail`, keeping the existing `PromptInjectionAgent` as-is for backward compatibility.

2. **Toxicity detection library?**
   - What we know: No single lightweight Python library dominates. Options: `detoxify` (PyTorch-based, heavy), Guardrails AI's `ToxicLanguage` validator (wraps their own model), OpenAI moderation API (external call).
   - Recommendation: Provide a `ToxicityGuardrail` base class that users can implement with their preferred backend. Ship a simple keyword-based one as default, with an OpenAI moderation adapter as optional.

3. **Rate limiting scope: per-agent, per-user, or per-run?**
   - What we know: Multi-agent systems need all three scopes. Per-agent prevents a single agent from monopolizing resources. Per-user prevents abuse. Per-run prevents runaway workflows.
   - Recommendation: `TokenBudget` class supports scoping by key (agent name, user ID, run ID). The `ExecutionContext` already carries `run_id` and could carry a `user_id`.

---

## Sources

### Primary (HIGH confidence)
- Orchestra codebase: `src/orchestra/security/acl.py`, `src/orchestra/security/rebuff.py`, `src/orchestra/reliability/` -- existing patterns
- [Guardrails AI GitHub](https://github.com/guardrails-ai/guardrails) -- v0.7.2, validator chain architecture
- [Guardrails AI OnFailAction docs](https://www.guardrailsai.com/docs/concepts/validator_on_fail_actions) -- NOOP, FIX, FILTER, REFRAIN, REASK, EXCEPTION
- [Microsoft Presidio GitHub](https://github.com/microsoft/presidio) -- PII detection/anonymization
- [NeMo Guardrails GitHub](https://github.com/NVIDIA-NeMo/Guardrails) -- Colang DSL, rail types
- [OpenAI Agents SDK Guardrails](https://openai.github.io/openai-agents-python/guardrails/) -- input/output guardrail pattern, tripwire mechanism
- [Tenacity docs](https://tenacity.readthedocs.io/) -- retry with backoff
- [pybreaker](https://pypi.org/project/pybreaker/) / [aiobreaker](https://pypi.org/project/aiobreaker/) -- circuit breaker implementations
- [SlowAPI GitHub](https://github.com/laurentS/slowapi) -- FastAPI rate limiting

### Secondary (MEDIUM confidence)
- [Portkey blog: Retries, fallbacks, circuit breakers](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/) -- LLM reliability patterns
- [Vigil LLM](https://github.com/deadbits/vigil-llm) -- alternative injection detection with YARA rules
- [Pytector](https://github.com/MaxMLang/pytector) -- lightweight injection detection

### Tertiary (LOW confidence)
- Community blog posts on token budget implementations -- patterns vary, no canonical library

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- verified via PyPI, GitHub, official docs for all recommended libraries
- Architecture: HIGH -- patterns derived from existing Orchestra code (`rebuff.py`, `selfcheck.py`) and verified external frameworks (OpenAI Agents SDK, Guardrails AI)
- Pitfalls: HIGH -- derived from documented issues in Guardrails AI GitHub, known Presidio loading behavior, and general distributed systems patterns
- Circuit breaker / rate limiting: MEDIUM -- patterns are standard but specific implementation choices (custom vs library) are a judgment call

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable domain, 30-day validity)
