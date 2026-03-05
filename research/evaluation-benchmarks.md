# Agent Evaluation, Benchmarks, and Testing Frameworks: Research for Orchestra

**Date:** 2026-03-06
**Status:** COMPLETE
**Purpose:** Inform Orchestra's built-in testing framework (ScriptedLLM, SimulatedLLM, FlakyLLM) and benchmark strategy

---

## 1. LiveAgentBench (March 2026, arxiv 2603.02586)

### Overview

LiveAgentBench is a dynamically updated benchmark comprising 104 daily real-world scenarios collected from real users' questions across internet platforms and social media. The release includes 374 tasks total (125 validation, 249 testing).

### Domain Coverage

Agents must demonstrate multiple capabilities across diverse domains:
- **Browser operation** -- web navigation, form filling, information retrieval
- **File operation** -- document creation, editing, format conversion
- **Android/iOS system operation** -- mobile device interaction
- **Audio and video comprehension** -- multimodal understanding tasks

The scenarios span real user requirements sourced from social media and real-world products, ensuring they reflect actual production use cases rather than synthetic constructs.

### Social Perception-Driven Data Generation (SPDG)

SPDG is a novel process designed to ensure three properties for each benchmark question:
1. **Real-world relevance** -- questions originate from actual user needs on social platforms
2. **Task complexity** -- multi-step, multi-capability challenges requiring agent coordination
3. **Result verifiability** -- each task has an objectively verifiable answer

### Verification Method

Ground truth is established through **double-blind labelling**: two independent annotators label each answer, and a third reviewer adjudicates any disagreements. This ensures all answers are correct and confident before inclusion in the benchmark.

### Integration Potential for Orchestra

LiveAgentBench is highly relevant for Orchestra because:
- It tests **multi-agent coordination** (browser + file + system operations in single tasks)
- Its dynamic update model prevents data leakage over time
- The real-world origin of tasks validates practical utility, not just academic performance
- Orchestra could ship a benchmark adapter: `orchestra benchmark run liveagentbench` that maps LiveAgentBench scenarios to Orchestra agent workflows

**Sources:**
- [LiveAgentBench Paper](https://arxiv.org/abs/2603.02586)
- [LiveAgentBench HTML](https://arxiv.org/html/2603.02586)

---

## 2. FeatureBench (arxiv 2602.10975, ICLR 2026)

### Overview

FeatureBench evaluates agentic coding performance on end-to-end, feature-oriented software development -- a significantly harder task than bug-fixing (which SWE-bench measures).

### Benchmark Scale

- **200 challenging evaluation tasks** from **24 open-source repositories**
- **3,825 executable environments**
- Designed to be scalable and updatable over time to mitigate data leakage

### Test-Driven Task Extraction Methodology

FeatureBench introduces a scalable, automated approach to deriving tasks:
1. **Start from unit tests** in real repositories
2. **Trace along the dependency graph** to identify feature-level coding tasks
3. Tasks may span **multiple commits and PRs** scattered across the development timeline
4. The method ensures **proper functioning of other features** after task separation (no regressions)
5. Minimal human effort required -- the automated task collection toolkit handles extraction

### Execution-Based Evaluation

Tasks are evaluated by running the actual test suites against agent-generated code. This is a pure pass/fail execution check -- no subjective LLM-as-judge needed for correctness.

### Key Results

State-of-the-art models that score well on SWE-bench struggle dramatically on FeatureBench:
- Claude 4.5 Opus achieves **74.4% on SWE-bench** but only **11.0% on FeatureBench**
- This gap reveals that bug-fixing ability does not transfer to feature development ability

### Relevance for Orchestra

FeatureBench is critical for evaluating Orchestra's coding agent workflows because:
- Feature development is a **multi-step, multi-file orchestration problem** -- ideal for multi-agent systems
- The execution-based evaluation gives deterministic pass/fail -- perfect for CI integration
- Orchestra could decompose FeatureBench tasks across specialized agents (planner, coder, tester, reviewer)

**Sources:**
- [FeatureBench Paper](https://arxiv.org/abs/2602.10975)
- [FeatureBench GitHub (ICLR 2026)](https://github.com/LiberCoders/FeatureBench)

---

## 3. Galileo Agent Evaluation Framework 2026

### Metric Taxonomy

Galileo distinguishes two primary metric categories:

**Trajectory-level metrics** evaluate the complete reasoning and execution path:
- LLM Planner assessment (tool selection quality, instruction passing)
- Individual tool call correctness (errors in tool completions)
- Decision sequences and intermediate steps
- Reasoning chain coherence

**Outcome-level metrics** measure only final results:
- Overall session success (task completion rate)
- Output quality (accuracy, completeness)
- Successful agentic interaction rate

### Rubric Design

Galileo employs a hierarchical rubric structure:
- **7 primary dimensions** (comprehensiveness, accuracy, coherence, etc.)
- **25 sub-dimensions** for granular assessment
- **130 fine-grained rubric items** as operationalized, measurable criteria

### LLM-as-Judge Calibration

Galileo's approach to automated evaluation:
- Judge prompts include **explicit rubrics, few-shot examples, and structured JSON outputs** requiring evidence before scoring
- Internal consistency validated via **Cronbach's alpha** across multiple independent runs
- Calibrated against human expert evaluation, targeting **0.80+ Spearman correlation** for production deployment
- The Agent Leaderboard evaluates function calling and API invocation in real-world applications (database queries, online calculators, web services)

### Key Takeaway for Orchestra

Orchestra should adopt the trajectory-vs-outcome metric distinction. SimulatedLLM tests should capture both the reasoning path (trajectory) and the final output (outcome). The 7-dimension / 25-sub-dimension rubric hierarchy is a proven template for structured evaluation that Orchestra could adapt.

**Sources:**
- [Galileo Agent Evaluation Framework 2026](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- [Galileo Launches Agentic Evaluations](https://www.prnewswire.com/news-releases/galileo-launches-agentic-evaluations-to-empower-developers-to-build-reliable-ai-agents-302358451.html)

---

## 4. Amazon's Agent Evaluation Lessons

### The Fundamental Shift

Amazon has built thousands of agents across its organizations. Their key insight: **traditional LLM evaluation treats agent systems as black boxes**, evaluating only the final outcome. This fails to explain *why* agents fail or pinpoint root causes.

Agentic AI requires evaluation of:
- Accuracy of **tool selection decisions**
- Coherence of **multi-step reasoning processes**
- Efficiency of **memory retrieval operations**
- Overall **task completion success rates** in production

### Evaluation Dimensions

1. **Accuracy** -- Does the agent produce correct results?
2. **Reasoning (Faithfulness)** -- Logical consistency across the reasoning process; does each step follow from the previous?
3. **Groundedness (Context Score)** -- Is each step contextually grounded in available information?
4. **Hallucination Detection** -- Do outputs align with verifiable data, or include implausible/misleading elements?
5. **Efficiency** -- Resource usage, step count, latency per task
6. **Trust** -- Predictability, safety guardrails, graceful degradation

### Error Handling Evaluation

Amazon emphasizes systematic assessment of agent failure recovery:
- **Reasoning failures** -- inappropriate planning from the reasoning model
- **Tool-use failures** -- invalid tool invocations, malformed parameters, unexpected response formats, authentication failures
- **Memory failures** -- memory retrieval errors, stale context
- **Action failures** -- failed execution, partial completion

The evaluation must test how agents **detect, classify, and recover** from these failures across the entire execution lifecycle.

### Production Evaluation Patterns

- Evaluate at **each step of the agent lifecycle**, not just final output
- Combine automated metrics with targeted human review
- Monitor **drift over time** as production data distributions change
- Use A/B testing for agent changes before full deployment

### Key Takeaway for Orchestra

Amazon's dimension taxonomy (accuracy, reasoning, groundedness, efficiency, trust) should directly inform Orchestra's evaluation API. FlakyLLM should specifically test the error handling scenarios Amazon identifies: invalid tool invocations, malformed parameters, authentication failures, and memory retrieval errors.

**Sources:**
- [Evaluating AI agents: Real-world lessons from building agentic systems at Amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

---

## 5. Existing Benchmarks: What They Measure and What They Miss

### GAIA (General AI Assistant)

- **466 human-curated tasks** at three difficulty levels
- Tests real-world questions requiring **multi-step reasoning, multimodality, and tool use**
- **Level 3** (hardest): top score 61% (Writer's Action Agent, mid-2025)
- **Overall top score:** ~90% (end of 2025)
- **Measures:** General assistant capability, reasoning chains, tool orchestration
- **Misses:** Multi-agent coordination, long-running workflows, error recovery

### SWE-bench Verified

- **500 human-validated samples** from real GitHub issues
- Created in collaboration with OpenAI; professional developers screened each sample
- **Top score:** 74.4% (Claude 4.5 Opus, end of 2025)
- **Measures:** Bug-fixing ability on real codebases
- **Misses:** Feature development, multi-file changes, architectural decisions, agent collaboration

### WebArena

- Realistic websites from four categories mimicking real-world equivalents
- Tests **web navigation, form filling, e-commerce transactions**
- Progress: 14% to ~60% success rate in two years
- **Measures:** Web interaction, UI understanding, multi-step browser tasks
- **Misses:** API-level tool use, non-web domains, multi-agent delegation

### HumanEval / MBPP (Code Agents)

- **HumanEval:** 164 hand-crafted Python programming problems
- **MBPP:** ~1,000 crowd-sourced Python tasks
- **Measures:** Function-level code generation correctness
- **Misses:** Real-world software engineering (file navigation, dependency management, testing, debugging). These are code-completion benchmarks, not agent benchmarks.

### Cross-Benchmark Gap Analysis

| Capability | GAIA | SWE-bench | WebArena | HumanEval | FeatureBench | LiveAgentBench |
|---|---|---|---|---|---|---|
| Multi-step reasoning | Yes | Partial | Yes | No | Yes | Yes |
| Tool use | Yes | Yes | Yes | No | Yes | Yes |
| Multi-agent coordination | No | No | No | No | No | Partial |
| Error recovery | No | No | No | No | No | No |
| Long-running workflows | No | No | No | No | Partial | Partial |
| Real-world grounding | Yes | Yes | Yes | No | Yes | Yes |
| Production resilience | No | No | No | No | No | No |

**The critical gap:** No existing benchmark evaluates multi-agent coordination, error recovery, or production resilience. This is exactly where Orchestra's testing framework (especially FlakyLLM) fills a void.

**Sources:**
- [AI Agent Benchmark Compendium](https://github.com/philschmid/ai-agent-benchmark-compendium)
- [Best AI Agent Evaluation Benchmarks 2025](https://o-mega.ai/articles/the-best-ai-agent-evals-and-benchmarks-full-2025-guide)
- [10 AI Agent Benchmarks (Evidently AI)](https://www.evidentlyai.com/blog/ai-agent-benchmarks)

---

## 6. Human-in-the-Loop Autonomy Spectrum (Deloitte 2026)

### The Three Modes

Deloitte's 2026 prediction identifies a progressive autonomy spectrum based on task complexity, business domain, workflow design, and outcome criticality:

**Human-in-the-Loop (HITL)**
- Human **approves every significant decision** before execution
- Required for high-stakes domains (medical, financial, legal)
- Agent proposes actions; human confirms or overrides
- Evaluation focus: **proposal quality, option completeness, explanation clarity**

**Human-on-the-Loop (HOTL)**
- Agent executes autonomously; human **monitors via dashboards and telemetry**
- Relies on outcome tracing, orchestration visualization, and anomaly detection
- Human intervenes only on exceptions or threshold breaches
- Evaluation focus: **anomaly detection accuracy, escalation appropriateness, dashboard utility**
- Deloitte predicts the most advanced businesses will begin shifting to HOTL in 2026

**Human-out-of-the-Loop (HOOTL)**
- Fully autonomous execution with **continuous monitoring** (not zero oversight)
- Suitable for low-risk, high-volume, well-defined tasks
- Still requires audit trails and compliance reporting
- Evaluation focus: **end-to-end success rate, drift detection, safety boundary adherence**

### How Orchestra Should Support All Three Modes

Orchestra's architecture should provide first-class primitives for each mode:

1. **HITL Support:**
   - `@approval_required` decorator on agent nodes that pause execution and await human input
   - Approval queues with timeout and escalation policies
   - Rich context presentation (what the agent wants to do, why, alternatives considered)

2. **HOTL Support:**
   - Real-time telemetry dashboards (built on Orchestra's OTel integration)
   - Configurable alert thresholds (cost, latency, error rate, confidence)
   - Exception-based human notification with one-click override capability
   - Checkpoint-based resume after human intervention

3. **HOOTL Support:**
   - Circuit breakers and automatic rollback (Saga pattern)
   - Comprehensive audit logging (event-sourced execution)
   - Drift detection comparing current behavior to baseline metrics
   - Automated compliance reporting

### Evaluation Differs Per Mode

| Evaluation Aspect | HITL | HOTL | HOOTL |
|---|---|---|---|
| Primary metric | Proposal quality | Escalation accuracy | End-to-end success |
| Human effort | High (every decision) | Medium (exceptions only) | Low (audit only) |
| Latency tolerance | High (waiting for human) | Medium | Low |
| Error recovery | Human handles it | Agent tries, escalates | Agent must self-recover |
| Trust requirement | Low (human verifies) | Medium | High (full autonomy) |
| Testing emphasis | ScriptedLLM | SimulatedLLM | FlakyLLM |

**Sources:**
- [Deloitte: Unlocking exponential value with AI agent orchestration](https://www.deloitte.com/us/en/insights/industry/technology/technology-media-and-telecom-predictions/2026/ai-agent-orchestration.html)
- [ByteBridge: From Human-in-the-Loop to Human-on-the-Loop](https://bytebridge.medium.com/from-human-in-the-loop-to-human-on-the-loop-evolving-ai-agent-autonomy-c0ae62c3bf91)

---

## 7. Testing Framework Design for Orchestra

### 7.1 ScriptedLLM: Deterministic Testing

**Purpose:** Test deterministic behavior where exact outputs are known in advance. Zero flakiness, zero cost, instant execution.

**What ScriptedLLM should test:**

| Category | Specific Tests |
|---|---|
| **State transitions** | Graph traversal follows expected paths; state is correctly updated at each node |
| **Tool call sequences** | Agents call the right tools in the right order with the right parameters |
| **Handoff behavior** | Agent-to-agent handoffs transfer correct context; handoff conditions trigger properly |
| **Guardrail enforcement** | PII filtering, cost limits, content filters activate on scripted inputs |
| **Structured output** | Pydantic models validate correctly; malformed outputs are rejected |
| **Approval flows (HITL)** | Execution pauses at approval nodes; resumes correctly after approval/rejection |
| **Edge cases** | Empty inputs, maximum-length inputs, unicode, adversarial prompts |
| **Memory operations** | Correct read/write to short-term, long-term, entity memory stores |

**Implementation pattern:**
```python
scripted = ScriptedLLM([
    ("What tools do I need?", "I'll use the search_api and calculator tools."),
    ("search_api(query='revenue 2025')", '{"result": "$4.2B"}'),
    ("Calculate growth", "Revenue grew 15% year-over-year."),
])
agent = Agent(name="analyst", llm=scripted)
result = await agent.run("Analyze revenue growth")
assert result.tool_calls == ["search_api", "calculator"]
assert "15%" in result.output
```

### 7.2 SimulatedLLM: Quality and Reasoning Testing

**Purpose:** Test with a real (or realistic) LLM to evaluate reasoning quality, end-to-end flows, and emergent behavior. Uses actual API calls or a local model.

**What SimulatedLLM should test:**

| Category | Specific Tests | Evaluation Method |
|---|---|---|
| **Reasoning quality** | Multi-step reasoning chains are logical and grounded | Trajectory metrics (Galileo-style) |
| **End-to-end flows** | Complete workflows produce correct final outputs | Outcome metrics + execution checks |
| **Agent collaboration** | Multiple agents coordinate effectively on shared tasks | Message quality + task decomposition assessment |
| **Context utilization** | Agents use available context (memory, RAG, prior turns) appropriately | Groundedness score (Amazon-style) |
| **Planning quality** | Agents create reasonable plans before execution | Plan completeness + step relevance |
| **Escalation judgment** | Agents correctly identify when to escalate to humans (HOTL) | Precision/recall on escalation decisions |
| **Output quality** | Final outputs meet rubric criteria | LLM-as-Judge with structured rubrics |

**Evaluation approach (combining Galileo + Amazon patterns):**
```python
simulated = SimulatedLLM(model="claude-sonnet-4-20250514", evaluators=[
    TrajectoryEvaluator(metrics=["faithfulness", "groundedness", "tool_selection"]),
    OutcomeEvaluator(rubric=revenue_analysis_rubric, judge_model="claude-sonnet-4-20250514"),
    LatencyEvaluator(max_p95_ms=5000),
])
results = await benchmark.run(agent_workflow, test_suite="financial_analysis")
assert results.trajectory.faithfulness > 0.85
assert results.outcome.accuracy > 0.90
```

### 7.3 FlakyLLM: Resilience and Error Recovery Testing

**Purpose:** Test how the system handles failures, degraded performance, and unpredictable behavior. Directly addresses the gap identified in Section 5 (no existing benchmark tests resilience).

**What FlakyLLM should test:**

| Category | Failure Mode | Expected Behavior |
|---|---|---|
| **Timeout handling** | LLM takes 30+ seconds to respond | Circuit breaker activates; fallback or retry |
| **Malformed responses** | LLM returns invalid JSON, incomplete tool calls | Parser error handling; retry with corrective prompt |
| **Rate limiting** | 429 errors from LLM provider | Exponential backoff; queue management |
| **Partial failures** | 1 of 3 parallel agents fails | Other agents complete; failed agent retries or degrades gracefully |
| **Hallucination injection** | LLM invents tool names or parameters | Tool validation catches invalid calls; error logged |
| **Context overflow** | LLM receives truncated context | Summarization triggers; critical info preserved |
| **Infinite loop detection** | Agent keeps calling same tool repeatedly | Max-turns guard activates; circuit breaker trips |
| **Cascading failure** | Downstream service outage affects multiple agents | Saga rollback; partial results preserved |
| **Authentication failure** | Tool credentials expire mid-execution | Re-auth attempt; graceful degradation if impossible |
| **Memory corruption** | Stale or contradictory memory entries | Conflict resolution; freshness-based prioritization |

**Implementation pattern:**
```python
flaky = FlakyLLM(
    base_model="claude-sonnet-4-20250514",
    failure_rate=0.3,           # 30% of calls fail
    timeout_rate=0.1,           # 10% timeout
    malformed_rate=0.1,         # 10% return garbage
    latency_spike_ms=15000,     # Occasional 15s latency
)
agent = Agent(name="resilient_analyst", llm=flaky)
results = await stress_test(agent, scenarios=100)
assert results.recovery_rate > 0.95      # Recovers from 95%+ of failures
assert results.circuit_breaker_trips < 5  # Circuit breaker is not too aggressive
assert results.data_loss_events == 0      # No data lost during failures
```

### 7.4 Benchmark Runner

**Yes, Orchestra should ship a benchmark runner.** The CLI interface should support:

```bash
# Run a specific benchmark suite
orchestra benchmark run liveagentbench --agents my_workflow.py

# Run FeatureBench tasks with Orchestra's coding agents
orchestra benchmark run featurebench --tasks 50 --parallel 4

# Run custom benchmark suites
orchestra benchmark run ./my_benchmarks/ --eval-model claude-sonnet-4-20250514

# Compare two agent configurations
orchestra benchmark compare config_a.yaml config_b.yaml --suite gaia

# Generate evaluation report
orchestra benchmark report --format html --output ./reports/
```

**Architecture of the benchmark runner:**

1. **Benchmark adapters** -- plugins that translate external benchmarks (LiveAgentBench, GAIA, SWE-bench, FeatureBench) into Orchestra task format
2. **Evaluation pipeline** -- configurable chain of evaluators (execution-based, LLM-as-Judge, metric calculators)
3. **Result storage** -- SQLite-backed results with comparison across runs
4. **Report generation** -- HTML/Markdown reports with trajectory visualizations

### 7.5 LLM-as-Judge Patterns for Orchestra

Based on industry best practices (Galileo, Evidently AI, Langfuse):

**Design principles:**
1. **Explicit rubrics** -- every judge prompt includes measurable criteria, not vague "quality" assessments
2. **Evidence-before-score** -- judge must cite specific evidence from the agent output before assigning a score
3. **Structured JSON output** -- judges return structured results, not free text
4. **Few-shot calibration** -- include 2-3 labeled examples in judge prompts
5. **Multi-run consistency** -- run each judgment 3+ times; measure Cronbach's alpha; flag inconsistent evaluations

**Implementation for Orchestra:**
```python
from orchestra.eval import LLMJudge, Rubric, RubricDimension

rubric = Rubric(
    dimensions=[
        RubricDimension(
            name="accuracy",
            description="Factual correctness of the final output",
            scale=(1, 5),
            anchors={1: "Multiple factual errors", 3: "Mostly correct", 5: "Fully accurate"},
        ),
        RubricDimension(
            name="reasoning_quality",
            description="Logical coherence of the agent's reasoning chain",
            scale=(1, 5),
            anchors={1: "Incoherent steps", 3: "Generally logical", 5: "Rigorous reasoning"},
        ),
        RubricDimension(
            name="tool_efficiency",
            description="Appropriate tool selection with minimal redundant calls",
            scale=(1, 5),
            anchors={1: "Wrong tools or excessive calls", 3: "Adequate", 5: "Optimal tool use"},
        ),
    ],
)

judge = LLMJudge(
    model="claude-sonnet-4-20250514",
    rubric=rubric,
    num_runs=3,                    # Run 3 times for consistency
    min_agreement=0.8,             # Flag if Cronbach's alpha < 0.8
    require_evidence=True,         # Must cite evidence before scoring
)
```

**Known limitations to address:**
- **Position bias** -- judges favor the first or last option in comparisons; mitigate by randomizing order
- **Length bias** -- judges favor longer responses; mitigate by including length-neutral rubric anchors
- **Self-bias** -- models favor their own outputs; use a different model as judge than the agent model
- **Lexical tricks** -- surface-term matching can fool judges; require semantic evidence, not keyword matching

---

## 8. Synthesis: Recommendations for Orchestra

### Priority 1: Ship with the Testing Framework (v1.0)

- **ScriptedLLM** is table stakes -- every agent framework needs deterministic unit testing
- **FlakyLLM** is Orchestra's differentiator -- no other framework ships resilience testing
- **SimulatedLLM** with basic metric capture (latency, tool call accuracy, success rate)

### Priority 2: LLM-as-Judge Infrastructure (v1.1)

- Ship `orchestra.eval` module with `LLMJudge`, `Rubric`, and `TrajectoryEvaluator`
- Include pre-built rubrics for common patterns (RAG quality, tool use, multi-agent collaboration)
- Target 0.80+ Spearman correlation with human evaluation

### Priority 3: Benchmark Runner (v1.2)

- CLI `orchestra benchmark` command with adapter plugin system
- Ship adapters for GAIA and SWE-bench Verified first (most widely used)
- Add FeatureBench and LiveAgentBench adapters as the benchmarks mature
- Result storage and comparison across runs

### Priority 4: Autonomy-Aware Evaluation (v1.3)

- Different evaluation profiles per autonomy mode (HITL/HOTL/HOOTL)
- HITL: measure proposal quality and explanation clarity
- HOTL: measure escalation precision/recall and dashboard coverage
- HOOTL: measure self-recovery rate and drift detection accuracy

### The Orchestra Advantage

No existing framework combines all three of:
1. **Deterministic testing** (ScriptedLLM) for CI/CD
2. **Quality evaluation** (SimulatedLLM + LLM-as-Judge) for reasoning assessment
3. **Resilience testing** (FlakyLLM) for production readiness

This triad, combined with a benchmark runner and autonomy-aware evaluation profiles, gives Orchestra the most comprehensive testing story in the multi-agent ecosystem.
