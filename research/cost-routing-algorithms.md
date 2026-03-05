# Cost Routing Algorithms: Research for Orchestra Framework

> Research date: 2026-03-06
> Scope: LLM cost routing, intelligent model selection, complexity profiling, and concrete design recommendations for Orchestra's CostRouter.

---

## Table of Contents

1. [RouteLLM (ICLR 2025)](#1-routellm-iclr-2025)
2. [IBM Research LLM Routers](#2-ibm-research-llm-routers)
3. [Three Router Architectures](#3-three-router-architectures)
4. [Complexity Profiling Techniques](#4-complexity-profiling-techniques)
5. [Cost Optimization Benchmarks](#5-cost-optimization-benchmarks)
6. [Concrete Design for Orchestra's CostRouter](#6-concrete-design-for-orchestras-costrouter)

---

## 1. RouteLLM (ICLR 2025)

### Overview

RouteLLM is an open-source framework from LMSYS (the Chatbot Arena team) for serving and evaluating LLM routers. It was published as a conference paper at ICLR 2025. The framework dynamically routes queries between a **strong model** (e.g., GPT-4) and a **weak model** (e.g., Mixtral-8x7B) based on query complexity, trained on human preference data from Chatbot Arena.

- **Repository**: https://github.com/lm-sys/RouteLLM
- **Paper**: https://arxiv.org/abs/2406.18665
- **Website**: https://routellm.dev/
- **License**: Apache 2.0 (standard for LMSYS projects)

### Routing Strategies Implemented

RouteLLM ships four trained router models out of the box:

| Router | Technique | Description |
|--------|-----------|-------------|
| **Matrix Factorization (MF)** | Collaborative filtering | Learns a scoring function for how well a model can answer a prompt. Decomposes the model-prompt interaction into latent factors. Best overall performer. |
| **BERT Classifier** | Supervised classification | Fine-tuned BERT model trained on preference data to classify whether a query needs the strong or weak model. |
| **Causal LLM Classifier** | LLM-based classification | Uses a causal language model as the classifier backbone, leveraging the LLM's own understanding of query difficulty. |
| **Similarity-Weighted (SW) Ranking** | Weighted Elo scoring | Computes weighted Elo ratings where each historical vote is weighted by its similarity to the current prompt (using embeddings). |

All four routers are trained on the `gpt-4-1106-preview` and `mixtral-8x7b-instruct-v0.1` model pair by default.

### Cost Savings Achieved

- **MT Bench**: Up to **85% cost reduction** while maintaining 95% of GPT-4 performance
- **MMLU**: **45% cost reduction** at 95% quality threshold
- **GSM8K**: **35% cost reduction** at 95% quality threshold
- Matrix factorization router achieves 95% of GPT-4 performance using only **26% GPT-4 calls** (~48% cheaper than random baseline)
- With data augmentation from an LLM judge, routers achieved 95% quality with only **14% strong model calls** (75% cost reduction)
- Cost multipliers: 3.66x savings at 50% premium-call threshold; 2.49x at 80% threshold

### Generalization

A critical finding: routers trained on one strong/weak model pair **generalize to other model pairs without retraining**. This means a router trained on GPT-4 vs. Mixtral can be used for Claude vs. Llama without fine-tuning.

### Integration Assessment for Orchestra

**Option A: Use as a dependency (RECOMMENDED for MVP)**
- Pros: Production-tested, four pre-trained routers, OpenAI-compatible API server, pip-installable
- Pros: Apache 2.0 license is fully compatible with any open-source license
- Pros: Augments OpenAI client transparently; minimal integration code
- Cons: Only supports binary routing (strong vs. weak), not multi-tier
- Cons: Requires PyTorch dependency for BERT/MF routers

**Option B: Adopt techniques (RECOMMENDED for v2)**
- Extract the matrix factorization and similarity-weighted approaches
- Extend to multi-tier routing (Orchestra needs 4+ tiers, not just 2)
- Build a lighter-weight router that doesn't require PyTorch

**Recommendation**: Start with RouteLLM as an optional dependency for binary strong/weak routing, then implement Orchestra's own multi-tier router using the MF and SW techniques.

---

## 2. IBM Research LLM Routers

### How IBM's Predictive Routers Work

IBM Research developed a **benchmark-data-driven** routing approach that leverages the vast amount of publicly available LLM evaluation data:

1. **Collect benchmark data**: Gather performance scores for many LLMs across diverse benchmarks (MMLU, GSM8K, HumanEval, etc.)
2. **Profile model strengths**: Build a capability matrix mapping each model to its performance on different task types (math, history, coding, reasoning, etc.)
3. **Classify incoming queries**: Analyze the incoming prompt to determine its task type and complexity
4. **Route to optimal model**: Select the model with the best predicted accuracy-to-cost ratio for that specific query type

### The 85% Cost Reduction Methodology

IBM's claimed 85% cost reduction comes from the observation that:

- **60-70% of production queries are simple** enough for cheap/small models
- By routing queries through a **library of 11 models**, the router outperforms any single model while maintaining cost efficiency
- The router uses **historical benchmark performance** as a proxy for future performance on similar tasks
- Key insight: "knowing how an LLM did on a similar task in the past gives a good idea of how it will do in the future"

### Algorithms for Complexity Profiling

IBM uses several approaches:

- **Task-type classification**: Categorize queries into domains (math, coding, creative writing, factual QA, reasoning)
- **Benchmark similarity matching**: Match incoming queries to the most similar benchmark tasks using embedding similarity
- **Predictive accuracy modeling**: Train regressors that predict each model's accuracy on a query given its features
- **Causal LLM Routing** (NeurIPS 2025): End-to-end regret minimization from observational data -- treats routing as a causal inference problem
- **MESS+** (NeurIPS 2025): Dynamically learned inference-time routing in model zoos with service level guarantees

### Key Takeaway for Orchestra

IBM's approach is attractive because it requires **no inference-time overhead** beyond a lightweight classifier -- the routing decision is made entirely from the prompt, before any LLM call.

---

## 3. Three Router Architectures

### 3.1 Predictive Routers

**Concept**: Classify query complexity BEFORE inference; route to the appropriate model tier without calling any LLM first.

**How it works**:
```
User Query --> [Complexity Classifier] --> Model Tier Selection --> [Selected LLM] --> Response
```

**Advantages**:
- Zero additional LLM inference cost for routing
- Lowest latency (single LLM call)
- Deterministic and predictable

**Disadvantages**:
- Requires pre-trained classifier (training data needed)
- Cannot recover from misclassification without retry logic
- Classification accuracy bounded by feature quality

**Algorithms used**:
- BERT/DistilBERT classifiers on prompt text
- Matrix factorization on prompt embeddings
- Gradient-boosted trees on hand-crafted features (query length, keyword presence, domain markers)
- Embedding similarity to benchmark queries with known difficulty

**Best for**: High-throughput production systems where latency matters.

### 3.2 Cascading Routers

**Concept**: Try the cheapest model first; escalate to more expensive models only if quality is insufficient.

**How it works**:
```
User Query --> [Cheapest Model] --> [Quality Judge] --pass--> Response
                                         |
                                       fail
                                         |
                                    [Next Model] --> [Quality Judge] --pass--> Response
                                                          |
                                                        fail
                                                          |
                                                     [Premium Model] --> Response
```

**Advantages**:
- No pre-training required for the router itself
- Self-correcting: always has the premium model as fallback
- Works well when most queries are genuinely simple

**Disadvantages**:
- Higher latency on complex queries (multiple sequential LLM calls)
- Requires a reliable quality judge (critical bottleneck)
- Total cost can exceed single-model cost if judge is poor
- 60-70% of queries resolve at cheapest tier in practice

**Quality judge approaches**:
- LLM-as-judge (another small model evaluates the response)
- Confidence scoring (perplexity/logprobs from the generating model)
- Self-consistency checks (generate multiple responses, check agreement)
- Rule-based heuristics (response length, refusal detection, hedging language)

**Best for**: Systems where quality guarantees are paramount and some latency is acceptable.

### 3.3 Consensus/Ensemble Routers

**Concept**: Send the query to multiple models simultaneously; aggregate or select the best response.

**How it works**:
```
User Query --> [Model A] --\
          --> [Model B] ----> [Aggregator/Selector] --> Best Response
          --> [Model C] --/
```

**Advantages**:
- Highest quality ceiling (picks the best from multiple responses)
- No risk of under-serving complex queries
- Can detect model hallucinations via disagreement

**Disadvantages**:
- Highest cost (pays for all models on every query)
- Latency bounded by slowest model (unless using streaming)
- Only saves cost if used selectively for high-stakes queries

**Aggregation strategies**:
- Majority voting (for factual/classification tasks)
- LLM-as-judge selection (pick the best response)
- Confidence-weighted selection
- Response merging (synthesize best parts of each)

**Best for**: High-stakes queries where correctness is critical (medical, legal, financial).

### Architecture Comparison

| Property | Predictive | Cascading | Consensus |
|----------|-----------|-----------|-----------|
| Latency | Low (1 call) | Medium-High (1-N calls) | High (N parallel calls) |
| Cost (simple query) | Low | Low | High |
| Cost (complex query) | Medium | High | High |
| Quality guarantee | Medium | High | Highest |
| Implementation complexity | Medium | Medium | Low |
| Requires training data | Yes | No (but needs judge) | No |

---

## 4. Complexity Profiling Techniques

### Estimating Task Complexity from the Prompt (~100 tokens of analysis)

The goal is to classify a prompt's difficulty using only the prompt text, before any LLM inference. Research identifies several feature categories:

### 4.1 Surface-Level Features (cheapest to compute)

| Feature | Signal | Computation |
|---------|--------|-------------|
| **Query length** (tokens) | Longer queries tend to be more complex | Tokenizer count |
| **Sentence count** | Multi-part questions are harder | Sentence splitting |
| **Question mark count** | Multiple questions = higher complexity | Regex |
| **Vocabulary richness** | Rare/technical words signal domain depth | Type-token ratio |
| **Average word length** | Longer words correlate with technical content | Simple arithmetic |

### 4.2 Structural/Linguistic Features (moderate cost)

| Feature | Signal | Computation |
|---------|--------|-------------|
| **Reasoning markers** | Words like "why", "explain", "compare", "analyze", "prove" | Keyword matching |
| **Instruction complexity** | Multi-step instructions ("first... then... finally") | Pattern matching |
| **Domain keywords** | Technical terms from math, code, science, law | Domain-specific dictionaries |
| **Code presence** | Code blocks, function names, variable patterns | Regex detection |
| **Negation/constraint density** | "not", "without", "except", "must not" | Keyword counting |
| **Conditional logic** | "if... then", "assuming that", "given that" | Pattern matching |

### 4.3 Semantic Features (higher cost, higher accuracy)

| Feature | Signal | Computation |
|---------|--------|-------------|
| **Embedding similarity to benchmarks** | Compare prompt embedding to embeddings of known-difficulty benchmark prompts | Cosine similarity with pre-computed index |
| **Task-type classification** | Classify into categories: QA, math, coding, creative, summarization, reasoning | Small classifier on embeddings |
| **Perplexity estimation** | How "surprising" is the prompt to a small LM | Forward pass through small model |

### 4.4 Existing Classifiers and Embeddings for Routing

- **RouteLLM's Matrix Factorization**: Learns latent representations of prompts and models; cosine similarity in latent space determines routing
- **RouteLLM's BERT Classifier**: Fine-tuned `bert-base-uncased` on ~80K preference pairs from Chatbot Arena
- **Anyscale's LLM Router**: Uses a causal LLM to generate embeddings, then trains a binary classifier
- **LLMRank**: Understands LLM strengths through benchmark decomposition; routes based on per-capability scores
- **Embedding models for similarity**: `all-MiniLM-L6-v2` (fast, 384-dim), `text-embedding-3-small` (OpenAI), or `nomic-embed-text` (open-source, good quality/speed)

### 4.5 Training Data for Router Models

| Data Source | Size | Type | Access |
|-------------|------|------|--------|
| **Chatbot Arena preference data** | ~1M+ comparisons | Human pairwise preferences | Public (LMSYS) |
| **LMSYS-Chat-1M** | 1M conversations | Real user queries with model responses | Public (HuggingFace) |
| **Benchmark datasets** (MMLU, GSM8K, HumanEval, etc.) | Varies | Task-specific with known difficulty | Public |
| **Synthetic preference data** | Unlimited | Generated by LLM-as-judge comparing model outputs | Self-generated |
| **Production query logs** | Org-specific | Real queries with quality labels | Private |

**Key finding from RouteLLM paper**: Data augmentation using an LLM judge (GPT-4 judging model outputs) improved router quality significantly. Training on benchmark data that closely resembles the target task distribution produces the best routers.

---

## 5. Cost Optimization Benchmarks

### Verified Savings from Research and Deployments

| Source | Methodology | Savings | Quality Retention |
|--------|-------------|---------|-------------------|
| **RouteLLM (MT Bench)** | MF router, GPT-4 vs Mixtral | **85%** | 95% of GPT-4 |
| **RouteLLM (MMLU)** | MF router, GPT-4 vs Mixtral | **45%** | 95% of GPT-4 |
| **RouteLLM (GSM8K)** | MF router, GPT-4 vs Mixtral | **35%** | 95% of GPT-4 |
| **IBM Research** | 11-model library, benchmark-trained | **Up to 85%** | Outperforms best single model |
| **Real production deployments** | Various routing strategies | **30-50%** | No measurable degradation |
| **Cascading (open-source benchmark)** | Cheapest-first escalation | **Up to 92%** | Depends on judge quality |
| **Conservative enterprise estimates** | Strategic model selection + caching | **~30%** | Maintained |

### Quality Degradation Analysis

- At **95% quality threshold**: Typical savings of 45-85% depending on benchmark and task distribution
- At **90% quality threshold**: Savings can exceed 85% but with measurable quality loss on hard queries
- **Critical finding**: Strong synthetic benchmark performance can **degrade sharply** under real-world prompts. Models appearing cost-efficient can cause 2-3x overspend when traffic patterns differ from benchmarks.
- **Recommendation**: Always evaluate routers on production-representative query distributions, not just standard benchmarks.

### Routing Overhead

| Component | Latency | Cost |
|-----------|---------|------|
| **Keyword/regex classifier** | <1ms | Zero |
| **Embedding + similarity search** | 5-20ms | ~$0.00001/query |
| **BERT classifier** | 10-50ms | ~$0.00005/query (self-hosted) |
| **RouteLLM MF router** | 10-30ms | ~$0.00003/query (self-hosted) |
| **Small LLM judge** | 200-500ms | ~$0.001-0.01/query |

**Key finding**: The most expensive RouteLLM router adds **no more than 0.4% extra cost** compared to GPT-4 generation. Router overhead is negligible relative to LLM inference costs.

---

## 6. Concrete Design for Orchestra's CostRouter

### Recommended Architecture: Hybrid Predictive + Cascading

Orchestra should implement a **two-stage router** that combines the speed of predictive routing with the safety net of cascading:

```
                          Stage 1: Predictive (fast)
                          ========================
User Query --> [Feature Extractor] --> [Complexity Classifier] --> Predicted Tier
                                                                       |
                          Stage 2: Cascading (safety net)              |
                          ===========================                  v
                          [Execute at Predicted Tier] --> [Confidence Check]
                                                              |
                                                         pass | fail
                                                              |    |
                                                         Response  [Escalate to next tier]
```

### Model Tier Definitions

| Tier | Label | Examples | Cost/1M tokens (approx) | Use When |
|------|-------|----------|------------------------|----------|
| **T0** | Local/Free | Ollama (Llama 3, Phi-3), local GGUF models | $0 | Simple lookups, formatting, classification |
| **T1** | Cheap API | GPT-4o-mini, Claude Haiku, Gemini Flash | $0.10-0.50 | Straightforward QA, summarization, simple code |
| **T2** | Standard | GPT-4o, Claude Sonnet, Gemini Pro | $2-10 | Multi-step reasoning, complex code, analysis |
| **T3** | Premium | Claude Opus, GPT-4.5, o1/o3 reasoning | $10-60 | Novel research, complex math, critical decisions |

### Feature Extractor Design

```python
# Lightweight feature extraction (~1ms per query)
class QueryFeatures:
    # Surface features
    token_count: int            # from fast tokenizer
    sentence_count: int
    question_count: int

    # Complexity markers (keyword matching)
    has_reasoning_markers: bool  # "why", "explain", "prove", "compare"
    has_multi_step: bool         # "first", "then", "finally", "step by step"
    has_code_markers: bool       # code blocks, function names, imports
    has_math_markers: bool       # equations, "calculate", "solve"
    has_domain_terms: bool       # technical vocabulary detected

    # Structural complexity
    constraint_count: int        # "must", "should not", "exactly", "without"
    conditional_count: int       # "if", "when", "assuming", "given that"

    # Computed score
    complexity_score: float      # 0.0 (trivial) to 1.0 (expert-level)
```

### Complexity Scoring Algorithm

```python
def compute_complexity_score(features: QueryFeatures) -> float:
    score = 0.0

    # Length-based (0-0.2)
    score += min(features.token_count / 500, 0.2)

    # Reasoning markers (0-0.25)
    if features.has_reasoning_markers: score += 0.15
    if features.has_multi_step: score += 0.10

    # Domain complexity (0-0.25)
    if features.has_code_markers: score += 0.10
    if features.has_math_markers: score += 0.15
    if features.has_domain_terms: score += 0.10

    # Structural complexity (0-0.3)
    score += min(features.constraint_count * 0.05, 0.15)
    score += min(features.conditional_count * 0.05, 0.15)

    return min(score, 1.0)

def score_to_tier(score: float) -> int:
    if score < 0.2: return 0   # T0: Local/Free
    if score < 0.45: return 1  # T1: Cheap API
    if score < 0.75: return 2  # T2: Standard
    return 3                   # T3: Premium
```

### Integration with RouteLLM

```python
# Optional RouteLLM integration for binary strong/weak decisions within a tier
class CostRouter:
    def __init__(self, config: RouterConfig):
        self.feature_extractor = QueryFeatureExtractor()
        self.tier_classifier = TierClassifier()  # Orchestra's own

        # Optional: RouteLLM for intra-tier binary routing
        self.routellm_enabled = config.use_routellm
        if self.routellm_enabled:
            from routellm.controller import Controller
            self.routellm = Controller(
                routers=["mf"],  # Matrix factorization (best performer)
                strong_model=config.strong_model,
                weak_model=config.weak_model,
            )

    def route(self, query: str, context: TaskContext) -> ModelSelection:
        # Stage 1: Orchestra's multi-tier classification
        features = self.feature_extractor.extract(query)
        tier = self.tier_classifier.predict(features, context)

        # Stage 2 (optional): RouteLLM binary refinement within tier
        if self.routellm_enabled and tier in [1, 2]:
            # Use RouteLLM to decide between cheap/standard within the tier
            routellm_decision = self.routellm.route(query)
            tier = self._adjust_tier(tier, routellm_decision)

        return ModelSelection(tier=tier, model=self._select_model(tier))
```

### SRE Scout/Sniper Pattern Integration

Orchestra's agent patterns map naturally to router tiers:

| Agent Pattern | Router Behavior |
|---------------|----------------|
| **Scout** (reconnaissance, broad search) | Route to T0/T1 -- scouts do lightweight exploration, don't need premium models |
| **Sniper** (precise, targeted action) | Route to T2/T3 -- snipers need accuracy and deep reasoning |
| **Sentinel** (monitoring, health checks) | Route to T0 -- repetitive checks, simple pattern matching |
| **Orchestrator** (planning, delegation) | Route to T2 -- needs good reasoning but not always premium |
| **Specialist** (domain-specific deep work) | Route to T2/T3 based on domain complexity score |

```python
class ScoutSniperRouter(CostRouter):
    """Extends CostRouter with agent-role awareness."""

    ROLE_TIER_BIAS = {
        "scout": -1,      # Bias toward cheaper models
        "sniper": +1,     # Bias toward more capable models
        "sentinel": -2,   # Strongly bias toward cheapest
        "orchestrator": 0, # Use complexity score as-is
        "specialist": 0,   # Use complexity score as-is
    }

    def route(self, query: str, context: TaskContext) -> ModelSelection:
        base_selection = super().route(query, context)
        bias = self.ROLE_TIER_BIAS.get(context.agent_role, 0)
        adjusted_tier = max(0, min(3, base_selection.tier + bias))
        return ModelSelection(tier=adjusted_tier, model=self._select_model(adjusted_tier))
```

### Should Orchestra Use RouteLLM as a Dependency?

**Verdict: Optional dependency, not required.**

| Consideration | Assessment |
|---------------|------------|
| **For MVP** | Implement Orchestra's own keyword/heuristic-based multi-tier router (zero dependencies, <500 lines). Offer RouteLLM as optional enhancement. |
| **For v1.0** | Add embedding-based similarity routing using a lightweight embedding model (e.g., `all-MiniLM-L6-v2` via `sentence-transformers`). |
| **For v2.0** | Implement matrix-factorization router trained on Orchestra's own usage data, inspired by RouteLLM's MF approach. |
| **RouteLLM integration** | Provide a `routellm` extras install (`pip install orchestra[routellm]`) for users who want pre-trained binary routing. |
| **License compatibility** | Apache 2.0 -- fully compatible with any OSS license Orchestra might use. |

### Implementation Priority

1. **Phase 1 (MVP)**: Keyword/heuristic complexity scorer + tier routing. No ML dependencies. ~300 lines of Python.
2. **Phase 2**: Add confidence-based cascading (use logprobs or response length heuristics as quality signals).
3. **Phase 3**: Optional RouteLLM integration for binary strong/weak refinement within tiers.
4. **Phase 4**: Train Orchestra-specific router on production data using matrix factorization approach.

---

## Sources

- [RouteLLM Paper (ICLR 2025)](https://arxiv.org/abs/2406.18665)
- [RouteLLM GitHub Repository](https://github.com/lm-sys/RouteLLM)
- [LMSYS RouteLLM Blog Post](https://lmsys.org/blog/2024-07-01-routellm/)
- [IBM Research: LLM Routing for Quality, Low-Cost Responses](https://research.ibm.com/blog/LLM-routers)
- [IBM Research: Causal LLM Routing (NeurIPS 2025)](https://research.ibm.com/publications/causal-llm-routing-end-to-end-regret-minimization-from-observational-data)
- [IBM Research: MESS+ Dynamic Routing (NeurIPS 2025)](https://research.ibm.com/publications/mess-dynamically-learned-inference-time-llm-routing-in-model-zoos-with-service-level-guarantees)
- [A Unified Approach to Routing and Cascading for LLMs](https://arxiv.org/html/2410.10347v1)
- [Anyscale: Building an LLM Router](https://www.anyscale.com/blog/building-an-llm-router-for-high-quality-and-cost-effective-responses)
- [Emergent Mind: Multi-LLM Routing Strategies](https://www.emergentmind.com/topics/multi-llm-routing)
- [LLMRank: Understanding LLM Strengths for Model Routing](https://arxiv.org/html/2510.01234v1)
- [Uplatz: Architectures and Strategies for Dynamic LLM Routing](https://uplatz.com/blog/architectures-and-strategies-for-dynamic-llm-routing-a-framework-for-query-complexity-analysis-and-cost-optimization/)
- [Swfte AI: Intelligent LLM Routing](https://www.swfte.com/blog/intelligent-llm-routing-multi-model-ai)
- [Burnwise: LLM Model Routing Guide](https://www.burnwise.io/blog/llm-model-routing-guide)
- [Zilliz: RouteLLM Balancing Cost and Quality](https://zilliz.com/learn/routellm-open-source-framework-for-navigate-cost-quality-trade-offs-in-llm-deployment)
- [Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing](https://arxiv.org/html/2404.14618v1)
- [Extended Survey: Routing Strategies in LLM-Based Systems](https://arxiv.org/html/2502.00409v1)
