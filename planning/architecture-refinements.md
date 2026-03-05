# Architecture Refinements: Incorporating New Research

**Date:** 2026-03-06
**Status:** COMPLETE
**Based on:** 4 external documents + best-elements-synthesis.md
**Constraint:** All components must be free / open-source / self-hostable

---

## Overview

This document specifies concrete architectural changes to Orchestra's design based on new findings from the four research documents. Each refinement is traceable to a source document and maps to a specific module in the architecture.

---

## Refinement 1: Enhanced Error Hierarchy with Anomaly Taxonomy

**Source:** Technical Selection Report (Section 5), 2025 State of AgentOps (Section 2)
**Module:** `src/orchestra/core/errors.py`

The existing `OrchestraError` hierarchy needs to incorporate the two-layer anomaly taxonomy discovered in the research. This is critical for Root Cause Analysis — determining whether a failure is system-centric, model-centric, or orchestration-centric.

### New Error Hierarchy

```python
class OrchestraError(Exception):
    """Base exception for all Orchestra errors."""

# === INTRA-AGENT ANOMALIES (Internal to a single agent) ===

class IntraAgentError(OrchestraError):
    """Failures within a single agent's reasoning or execution."""

class ReasoningError(IntraAgentError):
    """Hallucinations, factual inaccuracies, logical contradictions."""

class PlanningError(IntraAgentError):
    """Inconsistent tool use, impractical trajectories, incoherent plans."""

class ActionError(IntraAgentError):
    """Incorrectly formatted parameters, invalid tool calls, schema violations."""

class MemoryError(IntraAgentError):
    """RAG retrieval noise, working memory overflow, context window exhaustion."""

# === INTER-AGENT ANOMALIES (Systemic interaction failures) ===

class InterAgentError(OrchestraError):
    """Failures in the interaction between multiple agents."""

class CommunicationError(InterAgentError):
    """Message storms (redundant loops), lost messages, network partitioning."""

class MessageStormError(CommunicationError):
    """Detected: agents sending redundant requests in a loop."""
    agent_names: list[str]
    message_count: int

class TrustError(InterAgentError):
    """Agent accepted unverified/malicious data from another agent."""

class EmergentBehaviorError(InterAgentError):
    """Unexpected systemic behavior from agent interactions."""

class NeuralHowlroundError(EmergentBehaviorError):
    """Infinite self-optimization loop detected."""

class PerseverativeThinkingError(EmergentBehaviorError):
    """Unending recursive loop that stalls the system."""

class TerminationError(InterAgentError):
    """Workflow cannot terminate properly."""

class UndercommitmentError(TerminationError):
    """Endless delegation without any agent taking ownership."""

class PrematureTerminationError(TerminationError):
    """Workflow stopped before achieving its objective."""

# === ORCHESTRATION ANOMALIES ===

class OrchestrationError(OrchestraError):
    """Failures in the orchestration layer itself."""

class GraphCycleError(OrchestrationError):
    """Unguarded cycle detected that would cause infinite execution."""

class StateConflictError(OrchestrationError):
    """Concurrent state updates that cannot be resolved by reducers."""

class HandoffError(OrchestrationError):
    """Handoff target agent not found, not available, or refused the handoff."""

class BudgetExhaustedError(OrchestrationError):
    """Token or cost budget exceeded for agent or workflow."""

# === SECURITY ANOMALIES ===

class SecurityError(OrchestraError):
    """Security policy violations."""

class CapabilityViolationError(SecurityError):
    """Agent attempted an action it does not have permission for."""

class ToolPoisoningError(SecurityError):
    """Tool returned potentially malicious content."""

class PromptInjectionError(SecurityError):
    """Detected prompt injection attempt in agent communication."""
```

### Detection Mechanisms

Each error class maps to a specific detection strategy:

| Error Type | Detection Method | Trigger |
|---|---|---|
| MessageStormError | Counter on inter-agent messages per time window | >N messages between same agents in T seconds |
| NeuralHowlroundError | State diff comparison across iterations | State unchanged after K consecutive iterations |
| PerseverativeThinkingError | Recursion depth tracker | Depth exceeds max_recursion_depth |
| UndercommitmentError | Delegation chain tracker | >N consecutive handoffs without any agent executing |
| BudgetExhaustedError | Cost tracker on LLM calls | Cumulative cost exceeds budget |
| ToolPoisoningError | Output schema validation + content filter | Tool output fails validation or triggers content filter |

---

## Refinement 2: Circuit Breakers and Kill Switches

**Source:** PDF document Section 9 (Runtime Safety)
**Module:** `src/orchestra/security/circuit_breaker.py` (NEW)

### Agent-Level Kill Switch

```python
class AgentKillSwitch:
    """
    Emergency stop mechanism for individual agents.
    Operates OUTSIDE the agent's execution context.
    Backed by in-memory dict (dev) or Redis (prod) for sub-second response.
    """
    def __init__(self, backend: KillSwitchBackend = InMemoryKillSwitch()):
        self._backend = backend

    async def is_active(self, agent_name: str) -> bool:
        """Check if agent is allowed to execute. Called before every node execution."""

    async def kill(self, agent_name: str, reason: str) -> None:
        """Immediately disable an agent. Takes effect within 1 execution cycle."""

    async def revive(self, agent_name: str) -> None:
        """Re-enable a killed agent."""

class InMemoryKillSwitch:
    """Dev backend: dict-based, single process."""

class RedisKillSwitch:
    """Prod backend: Redis-based, distributed, sub-second propagation."""
```

### Action-Level Circuit Breakers

```python
class CircuitBreaker:
    """
    Limits how frequently a specific action can occur.
    Prevents retry storms and hallucination-driven recursive API calls.

    States: CLOSED (normal) -> OPEN (tripped) -> HALF_OPEN (testing recovery)
    """
    def __init__(
        self,
        failure_threshold: int = 5,       # Failures before tripping
        reset_timeout_seconds: float = 60, # Time before trying recovery
        half_open_max_calls: int = 1,      # Test calls in half-open state
    ): ...

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through the circuit breaker."""

    @property
    def state(self) -> CircuitState:
        """Current circuit state: CLOSED, OPEN, or HALF_OPEN."""
```

### Integration with Graph Engine

```python
# In CompiledGraph execution loop:
async def _execute_node(self, node_id: str, state: S, context: ExecutionContext) -> dict:
    # 1. Check kill switch
    if await self._kill_switch.is_active(node_id):
        raise AgentKilledError(f"Agent {node_id} has been killed")

    # 2. Execute through circuit breaker
    try:
        result = await self._circuit_breakers[node_id].call(
            node.execute, state, context
        )
    except CircuitOpenError:
        # Circuit is open — use fallback or skip
        result = await self._handle_circuit_open(node_id, state, context)

    return result
```

### Kill-Switch SLO

Target: ≤5 minutes to revoke an agent's access across the entire mesh.
- In-memory backend: immediate (single process)
- Redis backend: <1 second (pub/sub notification)
- NATS backend: <5 seconds (distributed pub/sub)

---

## Refinement 3: DID-Based Agent Identity

**Source:** PDF document Section 9 (Agent Identity and Decentralized Identifiers)
**Module:** `src/orchestra/security/identity.py` (ENHANCED)

### Current Design (Capability-Based)
The existing design uses simple capability grants. This refinement adds DID-based identity for cross-organizational trust.

### Enhanced Design

```python
class AgentIdentity:
    """
    Enhanced agent identity with optional DID support.

    In dev mode: simple string identity with all capabilities.
    In prod mode: capability-scoped identity.
    In federated mode: DID-based identity for cross-org trust.
    """
    agent_id: str                          # Unique within this Orchestra instance
    did: str | None = None                 # Decentralized Identifier (optional)
    owner: str = "local"                   # Organization that owns this agent
    capabilities: set[Capability] = set()  # Granted capabilities
    verifiable_credentials: list[VC] = []  # Claims about this agent (optional)
    created_at: datetime
    expires_at: datetime | None = None

class Capability(str, Enum):
    TOOL_USE = "tool:use"
    TOOL_USE_SPECIFIC = "tool:use:{tool_name}"  # Scoped to specific tool
    STATE_READ = "state:read"
    STATE_WRITE = "state:write"
    NETWORK_ACCESS = "network:access"
    CODE_EXEC = "code:exec"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    AGENT_DELEGATE = "agent:delegate"       # Can hand off to other agents
    AGENT_SPAWN = "agent:spawn"             # Can create new agents
    HUMAN_ESCALATE = "human:escalate"       # Can escalate to human
    BUDGET_UNLIMITED = "budget:unlimited"   # No cost limits
    EXTERNAL_INVOKE = "external:invoke"     # Can call external A2A agents

class DevModeIdentity(AgentIdentity):
    """All capabilities granted. No DID. For local development."""

class ProdModeIdentity(AgentIdentity):
    """Explicit capability grants. DID optional."""

class FederatedIdentity(AgentIdentity):
    """DID required. VC verification. For cross-org agent mesh."""
```

### Trust Verification Flow (Federated Mode)

```
1. External agent presents Agent Card with DID
2. Orchestra verifies DID against distributed ledger (or local cache)
3. Orchestra checks Verifiable Credentials for authorization claims
4. If verified, creates a scoped session with limited capabilities
5. All tool invocations are attributed to the external agent's DID
6. Audit log records full provenance chain
```

This is **progressive**: simple dev mode (zero config) → prod mode (explicit grants) → federated mode (DID + VC). Most users will never need federated mode.

---

## Refinement 4: SRE Filter Pattern (Scout/Sniper) for Cost Router

**Source:** 2025 State of AgentOps (Section 4: Latency-Cost Multiplier)
**Module:** `src/orchestra/providers/router.py` (ENHANCED)

The research identifies that redundant parallel agent calls can increase costs 5-6x. The SRE Filter Pattern uses a cheap "Scout" agent to determine if an expensive "Sniper" agent is needed.

### Integration into Cost Router

```python
class CostRouter:
    """
    Intelligent LLM routing with SRE Filter Pattern.

    Strategy:
    1. Analyze task complexity with a cheap model (Scout)
    2. Route to cost-appropriate model based on complexity score
    3. Enforce per-agent and per-workflow budgets
    4. Fall back to cheaper model rather than fail when budget is low
    """

    class ComplexityTier(str, Enum):
        TRIVIAL = "trivial"     # Pattern matching, simple extraction -> local/free model
        SIMPLE = "simple"       # Summarization, classification -> GPT-4o-mini / Haiku
        MODERATE = "moderate"   # Multi-step reasoning, code gen -> GPT-4o / Sonnet
        COMPLEX = "complex"     # Deep analysis, novel reasoning -> Opus / o1

    async def route(self, messages: list[Message], context: ExecutionContext) -> str:
        """
        Determine the optimal model for this task.

        SRE Filter: Uses a cheap 'Scout' call to profile complexity,
        then routes to the appropriate 'Sniper' model.
        """
        # Scout: cheap model estimates complexity (~100 tokens, ~$0.0001)
        complexity = await self._profile_complexity(messages)

        # Check budget remaining
        budget = context.get_remaining_budget()

        # Route to cost-appropriate model
        model = self._select_model(complexity, budget)

        return model

    def _select_model(self, complexity: ComplexityTier, budget: float) -> str:
        """Select model based on complexity and remaining budget."""
        # If budget is low, degrade gracefully
        if budget < self.min_budget_threshold:
            return self.cheapest_model

        return self.tier_map[complexity]
```

---

## Refinement 5: Three Orchestration Styles as First-Class Patterns

**Source:** IBM watsonx Orchestrate (React / Plan-Act / Deterministic), Technical Selection Report (Section 2)
**Module:** `src/orchestra/core/patterns.py` (NEW)

Orchestra's graph engine can express any orchestration pattern, but providing named patterns reduces boilerplate for common use cases.

```python
# Built-in orchestration pattern constructors

def react_loop(
    agent: Agent,
    tools: list[Tool],
    max_iterations: int = 10,
    exit_condition: Callable[[S], bool] | None = None,
) -> CompiledGraph:
    """
    React pattern: Agent reasons, acts (tool call), observes, repeats.
    Best for: Exploration, research, open-ended reasoning.
    Source: IBM watsonx React style + LangGraph ReAct pattern.
    """

def plan_and_execute(
    planner: Agent,
    executors: dict[str, Agent],
    max_replans: int = 3,
) -> CompiledGraph:
    """
    Plan-Act pattern: Planner creates task graph, executors carry out tasks.
    Reduces inference costs by ~45% vs. monolithic agent (from 2025 AgentOps doc).
    Best for: Structured, goal-oriented workflows.
    Source: IBM watsonx Plan-Act + LangGraph plan-and-execute template.
    """

def deterministic_pipeline(
    steps: list[FunctionNode | Agent],
) -> CompiledGraph:
    """
    Deterministic pattern: Fixed sequence of steps, no LLM routing decisions.
    Best for: High-predictability tasks, compliance-sensitive workflows.
    Source: IBM watsonx Deterministic + Haystack pipelines.
    """

def supervisor_routing(
    supervisor: Agent,
    specialists: dict[str, Agent],
    fallback: Agent | None = None,
) -> CompiledGraph:
    """
    Supervisor pattern: Central agent routes to specialists.
    Best for: Customer support, triage, query routing.
    Source: AWS Bedrock supervisor + Salesforce Atlas routing.
    """

def review_loop(
    creator: Agent,
    reviewer: Agent,
    max_revisions: int = 3,
) -> CompiledGraph:
    """
    Reviewer-Creator pattern: One agent creates, another critiques.
    Best for: Content generation, code review, policy compliance.
    Source: Salesforce Agentforce Manager-Worker pattern.
    """

def debate(
    agents: list[Agent],
    judge: Agent,
    rounds: int = 3,
) -> CompiledGraph:
    """
    Adversarial debate: Multiple agents argue, judge decides.
    Improves factual accuracy by ~23% over single-model (from Technical Selection Report).
    Best for: Research, fact-checking, decision-making.
    Source: AutoGen group chat + CAMEL role-playing.
    """
```

---

## Refinement 6: Proactive Agent Support (Event-Driven Entry Points)

**Source:** Salesforce Agentforce (Conversational vs. Proactive agents), PDF document Section 7
**Module:** `src/orchestra/core/triggers.py` (NEW)

Currently Orchestra only supports request-response workflows. Proactive agents need event-driven triggers.

```python
class WorkflowTrigger(Protocol):
    """Base protocol for workflow triggers."""
    async def start(self, callback: Callable) -> None: ...
    async def stop(self) -> None: ...

class ScheduleTrigger(WorkflowTrigger):
    """Trigger workflow on a cron schedule."""
    def __init__(self, cron: str): ...

class WebhookTrigger(WorkflowTrigger):
    """Trigger workflow from HTTP webhook."""
    def __init__(self, path: str, method: str = "POST"): ...

class DataChangeTrigger(WorkflowTrigger):
    """Trigger workflow when data changes (polling or event-based)."""
    def __init__(self, query: Callable, poll_interval: float = 60): ...

class EventBusTrigger(WorkflowTrigger):
    """Trigger workflow from NATS/internal event bus."""
    def __init__(self, subject: str): ...

# Usage:
graph = WorkflowGraph(state_schema=MyState)
graph.add_trigger(ScheduleTrigger(cron="0 */6 * * *"))  # Every 6 hours
graph.add_trigger(WebhookTrigger(path="/api/incoming"))
```

---

## Refinement 7: Memory Synthesis (Preventing Cognitive Stagnation)

**Source:** Technical Selection Report (Section 4: Memory Synthesis vs. Context)
**Module:** `src/orchestra/memory/synthesis.py` (NEW)

Raw interaction logs accumulate noise over time. Periodic synthesis into high-level facts prevents "cognitive stagnation."

```python
class MemorySynthesizer:
    """
    Periodically synthesizes raw interaction logs into high-level facts.
    Maintains long-term coherence while reducing noise.

    Process:
    1. Collect raw events from ShortTermMemory since last synthesis
    2. Use LLM to extract key facts, decisions, and outcomes
    3. Store synthesized facts in LongTermMemory
    4. Update EntityMemory with any new entity-attribute-value triples
    5. Prune raw events older than retention period
    """
    async def synthesize(
        self,
        session_id: str,
        provider: LLMProvider,
        max_events: int = 100,
    ) -> list[SynthesizedFact]: ...
```

---

## Refinement 8: Agent Card / A2A Registry

**Source:** PDF document Section 8 (A2A Protocol), Google ADK Section
**Module:** `src/orchestra/interop/a2a.py` (NEW)

```python
class AgentCard(BaseModel):
    """
    A2A v0.3 Agent Card. Digital resume advertising capabilities.
    Enables dynamic discovery without hard-coded connections.
    """
    name: str
    description: str
    version: str
    capabilities: list[str]           # What this agent can do
    input_schema: dict                # Expected input format
    output_schema: dict               # Produced output format
    security_requirements: list[str]  # Required credentials/permissions
    endpoint: str                     # How to invoke this agent
    slo: AgentSLO | None = None       # Performance guarantees

class AgentSLO(BaseModel):
    max_latency_ms: int = 30000
    availability: float = 0.99

class A2ARegistry:
    """Registry for discovering and invoking A2A agents."""
    async def register(self, card: AgentCard) -> None: ...
    async def discover(self, capability: str) -> list[AgentCard]: ...
    async def invoke(self, card: AgentCard, input: dict) -> dict: ...
```

---

## Refinement 9: Guardrails Middleware Enhancement

**Source:** AWS Bedrock Guardrails, Microsoft Responsible AI, PDF Section 9
**Module:** `src/orchestra/security/guardrails.py` (ENHANCED)

```python
# Composable guardrail chain
class GuardrailChain:
    """
    Composable pre/post execution guardrails.
    Applied as middleware on any agent node.
    All implementations are local (no cloud dependency).
    """
    pre_hooks: list[PreGuardrail]   # Run before agent execution
    post_hooks: list[PostGuardrail]  # Run after agent execution

class ContentFilter(PreGuardrail, PostGuardrail):
    """Filter harmful content in inputs and outputs. Local regex + optional local model."""

class PIIDetector(PostGuardrail):
    """Detect and redact PII in agent outputs. Regex-based + optional local NER model."""

class CostLimiter(PreGuardrail):
    """Block execution if cost budget would be exceeded."""

class SchemaValidator(PostGuardrail):
    """Validate agent output against expected Pydantic schema."""

class TaskAdherenceFilter(PostGuardrail):
    """Check that agent output is relevant to the assigned task (anti-drift)."""

class RateLimiter(PreGuardrail):
    """Limit execution frequency per agent per time window."""

class PromptShield(PreGuardrail):
    """Detect prompt injection attempts in input messages."""

# Usage:
@with_guardrails(
    pre=[PromptShield(), CostLimiter(max_cost_usd=0.50), RateLimiter(max_per_minute=10)],
    post=[ContentFilter(), PIIDetector(), SchemaValidator(output_type=Report)],
)
class ResearchAgent(BaseAgent):
    ...
```

---

## Summary of All Refinements

| # | Refinement | Source | Module | Phase |
|---|---|---|---|---|
| 1 | Enhanced error hierarchy with anomaly taxonomy | Tech Report + AgentOps doc | `core/errors.py` | Phase 1 |
| 2 | Circuit breakers and kill switches | PDF Section 9 | `security/circuit_breaker.py` | Phase 2 |
| 3 | DID-based agent identity (progressive) | PDF Section 9 | `security/identity.py` | Phase 4 |
| 4 | SRE Filter Pattern in cost router | AgentOps doc Section 4 | `providers/router.py` | Phase 3 |
| 5 | Three orchestration styles as patterns | IBM watsonx + Tech Report | `core/patterns.py` | Phase 1 |
| 6 | Proactive agent triggers | Salesforce Agentforce | `core/triggers.py` | Phase 3 |
| 7 | Memory synthesis | Tech Report Section 4 | `memory/synthesis.py` | Phase 3 |
| 8 | A2A Agent Card registry | PDF Section 8, Google ADK | `interop/a2a.py` | Phase 4 |
| 9 | Enhanced guardrails middleware | Bedrock + Microsoft + PDF | `security/guardrails.py` | Phase 2 |

All refinements maintain the principle of **progressive complexity**: they are opt-in features that add zero overhead when not configured.
