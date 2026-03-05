# Memory Architecture Research: State-of-the-Art Agent Memory Systems

**Date:** 2026-03-06
**Purpose:** Evaluate external memory solutions for Orchestra's 4-tier memory system (working, short-term, long-term, entity)
**Decision:** Build from scratch vs. integrate Mem0 vs. use Redis vs. other solutions

---

## Table of Contents

1. [Mem0 (Open-Source Agent Memory)](#1-mem0-open-source-agent-memory)
2. [MemOS (Memory Operating System)](#2-memos-memory-operating-system)
3. [Supermemory](#3-supermemory)
4. [Survey: "Memory in the Age of AI Agents" (arxiv 2512.13564)](#4-survey-memory-in-the-age-of-ai-agents)
5. [Redis AI Agent Memory](#5-redis-ai-agent-memory)
6. [Practical Comparison for Orchestra](#6-practical-comparison-for-orchestra)
7. [Recommendation](#7-recommendation)

---

## 1. Mem0 (Open-Source Agent Memory)

### Architecture

Mem0 is a scalable, memory-centric architecture that dynamically extracts, consolidates, and retrieves salient information from ongoing conversations. It operates in two main phases:

**Extraction Phase:**
- Ingests three context sources: (1) the latest exchange, (2) a rolling summary, and (3) the _m_ most recent messages
- Uses an LLM to extract a concise set of candidate memories (factual statements about the user, preferences, decisions, etc.)

**Update (Consolidation) Phase:**
- Each new candidate fact is compared against the top _s_ most similar entries in the vector database
- If a match is found, the system merges or updates the existing memory (deduplication + conflict resolution)
- If no match, the fact is inserted as a new memory entry
- This prevents unbounded memory growth and ensures consistency

**Retrieval Phase:**
- At query time, the user's message is embedded and used for semantic similarity search against the vector store
- Top-k relevant memories are injected into the LLM context alongside the conversation

### Performance Claims

The Mem0 research paper (arxiv 2504.19413) reports the following benchmarks:

| Metric | Claim | Context |
|--------|-------|---------|
| **Accuracy** | 26% relative improvement in LLM-as-a-Judge metric over OpenAI's memory | Measured across multi-session dialogue tasks |
| **Latency** | 91% reduction in p95 latency | Compared to full-context approaches (stuffing entire history into prompt) |
| **Token savings** | 90%+ reduction in token usage | vs. full-context approaches in multi-session dialogues |

**Verification notes:** These claims compare against _full-context baselines_ (sending all conversation history), which is an intentionally wasteful baseline. The 26% accuracy improvement is against OpenAI's built-in memory (ChatGPT memory), which is a more meaningful comparison. The latency and token savings are expected when replacing full-context with extracted facts -- any memory system that extracts summaries would show similar savings. The accuracy claim is the genuinely significant one.

### Mem0g: Graph-Based Extension

Mem0g is an enhanced variant that layers a graph-based store on top of the vector memory:

- **Graph structure:** Memories stored as directed labeled graphs -- entities are nodes, relationships are edges
- **Graph backend:** Uses Neo4j as the underlying graph database
- **Entity extraction:** GPT-4o-mini extracts entities and relationships from every memory write
- **Dual storage:** Embeddings stored in vector DB, relationships mirrored in graph backend
- **Retrieval strategies:**
  1. _Entity-centric:_ Identifies key entities in query, finds corresponding nodes, traverses connected relationships
  2. _Semantic triplet:_ Encodes the query as a dense embedding and matches against relationship triplets
- **Temporal reasoning:** When a conflict is detected, an LLM-based update resolver marks relationships as obsolete without removing them, preserving history
- **Performance:** ~2% overall score improvement over base Mem0; significant gains specifically on temporal and open-domain tasks, and multi-hop reasoning queries

### License and Integration

- **License:** Apache 2.0 (permissible for commercial use, compatible with Orchestra)
- **Installation:** `pip install mem0ai` (Python >=3.9, <4.0)
- **SDKs:** Python and Node.js
- **Deployment:** Self-hosted open-source version + managed cloud platform (paid)
- **Vector backends supported:** Qdrant (default), ChromaDB, Pinecone, Weaviate, pgvector, and others
- **Graph backend:** Neo4j (for Mem0g features)
- **Cloud integrations:** AWS (ElastiCache for Valkey + Neptune Analytics), GCP

### Can Orchestra Use Mem0 as an Optional Memory Backend?

**Yes.** Mem0's architecture is well-suited as an optional backend for Orchestra:

- It provides a clean Python API (`Memory()` class) for add/search/update/delete operations
- It supports multiple vector store backends, including pgvector (which aligns with Orchestra's PostgreSQL preference)
- It can run fully self-hosted with no cloud dependency
- Apache 2.0 license is compatible with Orchestra's open-source model
- The main concern is the LLM dependency for extraction -- Mem0 requires an LLM call for every memory write operation, which adds latency and cost. However, this can use local models via Ollama.

**Integration pattern:** Orchestra would define a `MemoryBackend` protocol. Mem0 would be one implementation behind that protocol, alongside a custom implementation. Users choose at configuration time.

---

## 2. MemOS (Memory Operating System)

### Overview

MemOS was introduced in mid-2025 by researchers from Shanghai Jiao Tong University and Zhejiang University. It treats memory as a first-class manageable system resource, analogous to how an operating system manages files, processes, and I/O. It is the first system to propose a comprehensive "Memory Operating System" abstraction for LLMs.

**Note:** There are two projects named "MemOS" on GitHub. The relevant one for this analysis is `BAI-LAB/MemoryOS` (EMNLP 2025 Oral) and the related `MemTensor/MemOS` with broader scope. The core paper is arxiv 2505.22101 (short version) and arxiv 2507.03724 (full version).

### How It Coordinates Facts, Summaries, and Experiences

MemOS unifies three distinct types of memory content:

1. **Plaintext memories:** Declarative facts, user preferences, extracted knowledge (similar to Mem0's approach)
2. **Activation-based memories:** KV-cache states that can be injected directly into transformer attention layers, bypassing the need for text-based retrieval entirely
3. **Parameter-level memories:** Fine-tuned model weights or LoRA adapters that encode persistent knowledge into the model itself

The coordination happens through the **MemCube** abstraction -- a container that encapsulates both memory content and metadata (provenance, versioning, access control). MemCubes can be composed, migrated, and fused over time.

### Key Abstractions

| Abstraction | Purpose |
|-------------|---------|
| **MemCube** | Encapsulates memory content + metadata (provenance, version, access control) |
| **MemScheduler** | Asynchronous memory operations with millisecond-level latency for production stability |
| **Memory Feedback** | Natural-language feedback loop for correcting, supplementing, or replacing memories |
| **Multi-Cube KB** | Multiple knowledge bases as composable memory cubes with isolation and controlled sharing |

### Performance

- 159% boost in temporal reasoning tasks vs. OpenAI's memory system
- 38.9% overall improvement on the LOCOMO benchmark
- Up to 94% reduction in latency through efficient KV-cache injections

### Open-Source and Production Readiness

- **License:** MIT (highly permissive, compatible with Orchestra)
- **Status:** Open-sourced on GitHub, available on PyPI (`pip install MemoryOS`)
- **Ecosystem compatibility:** Works with HuggingFace, OpenAI, Ollama
- **Production readiness:** MemOS v2.0 ("Stardust") release includes production features (async scheduling, multi-modal memory, tool memory), but the project is younger and less battle-tested than Mem0

### Relevance to Orchestra

MemOS's KV-cache injection and parameter-level memory are novel but tightly coupled to specific model architectures. The MemCube abstraction is intellectually interesting but may be over-engineered for Orchestra's needs. The plaintext memory layer overlaps significantly with Mem0. Orchestra should monitor MemOS but not adopt it as a primary dependency at this stage -- it is more of a research system than a production library.

---

## 3. Supermemory

### How It Solves Long-Term Forgetting

Supermemory is a memory engine designed to solve the "long-term coherence" problem -- the tendency for AI agents to lose context and produce contradictions over sustained interactions (the "30% accuracy drop" observed in most systems on LongMemEval benchmarks).

Key mechanisms:
- **Automatic extraction:** Learns from conversations, extracts facts, builds user profiles
- **Knowledge updates:** Explicitly handles contradictions and superseded information
- **Temporal awareness:** Tracks when facts were learned and can reason about time-dependent truths
- **Expiration/forgetting:** Actively forgets expired information rather than accumulating stale data
- **Contextual delivery:** Delivers the right context at the right time based on query relevance

### LongMemEval Benchmark Results

Supermemory claims #1 ranking on three major memory benchmarks:
- **LongMemEval** (ICLR 2025): Evaluates five core abilities -- information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention
- **LoCoMo** (Snap Research): Long-context conversational memory evaluation
- **ConvoMem:** Conversational memory benchmark

Specific claim: Supermemory achieves SOTA on LongMemEval_s, effectively solving temporal reasoning and knowledge conflicts in high-noise environments (115k+ tokens). While most systems suffer a 30% accuracy drop under sustained interactions, Supermemory-class systems achieve over 90% accuracy on the same tests.

### Architecture and Availability

- **GitHub:** `supermemoryai/supermemory` -- described as "Memory engine and app that is extremely fast, scalable. The Memory API for the AI era."
- **Open source:** Yes, the core engine is open-source on GitHub
- **API-first:** Designed as a Memory API service rather than an embeddable library
- **Architecture:** Details on internal architecture are less publicly documented than Mem0's. It appears to combine vector search with structured knowledge graphs and temporal indexing, but the specifics are proprietary to their research.

### Relevance to Orchestra

Supermemory's benchmark results are impressive but it is primarily positioned as a hosted API service. The open-source version may not include all the features that achieve the benchmark scores. For Orchestra, Supermemory is best considered as validation that the temporal reasoning and knowledge update problems are solvable, rather than as a direct integration target. Orchestra's custom long-term memory tier should aim to match these capabilities.

---

## 4. Survey: "Memory in the Age of AI Agents" (arxiv 2512.13564)

### Taxonomy

The survey proposes a three-dimensional taxonomy for agent memory:

#### Dimension 1: Forms (How memory is stored)

| Form | Description |
|------|-------------|
| **Token-level** | Memory stored as text tokens in the context window (conversation history, retrieved documents) |
| **Parametric** | Memory encoded in model weights (fine-tuning, LoRA adapters) |
| **Latent** | Memory stored as hidden-state vectors or KV-cache entries (sub-symbolic, not human-readable) |

#### Dimension 2: Functions (What memory is for)

| Function | Description | Sub-types |
|----------|-------------|-----------|
| **Factual Memory** | Declarative knowledge base -- user profiles, environmental states, persona consistency, goal coherence | Facts, preferences, world state |
| **Experiential Memory** | Procedural knowledge -- _how_ to solve problems | Case-based (raw trajectories for replay), Strategy-based (abstracted workflows/insights), Skill-based (executable code/tool APIs) |
| **Working Memory** | Active, transient information being processed in the current reasoning step | Current context, scratchpad, intermediate results |

#### Dimension 3: Dynamics (How memory changes over time)

| Phase | Key Processes |
|-------|---------------|
| **Formation** | How memories are created -- extraction from conversations, learning from experience, encoding decisions |
| **Evolution** | How memories change -- consolidation, conflict resolution, forgetting, reinforcement, abstraction |
| **Retrieval** | How memories are accessed -- semantic search, structured lookup, associative recall, temporal queries |

### Key Findings

1. **Memory formation** is under-studied compared to retrieval -- most systems focus on how to find memories, not how to create high-quality memories in the first place
2. **Memory evolution** (consolidation, forgetting, conflict resolution) is critical for long-running agents but rarely implemented well
3. **Experiential memory** (learning from past task execution) is the most impactful but hardest to implement -- skill-based memory (reusable code/tool compositions) shows the most promise
4. **Multi-agent memory** (shared memory across agents) introduces coordination challenges analogous to distributed systems (consistency, isolation, access control)
5. **Trustworthiness** of memories is an emerging concern -- poisoned memories, hallucinated facts, and privacy leakage

### Architectural Recommendations

The survey identifies several frontiers:
- **Memory automation:** Reducing reliance on hand-crafted extraction rules
- **RL integration:** Using reinforcement learning to optimize memory formation and retrieval policies
- **Multimodal memory:** Extending beyond text to images, audio, and structured data
- **Multi-agent memory:** Shared memory pools with access control and consistency guarantees
- **Memory benchmarks:** Need for standardized evaluation (LongMemEval, LoCoMo, etc.)

### Relevance to Orchestra

This survey strongly validates Orchestra's 4-tier architecture. The mapping is:

| Survey Category | Orchestra Tier |
|-----------------|----------------|
| Working Memory | Working memory (in-process) |
| Factual Memory | Entity memory + Long-term memory |
| Experiential Memory (case-based) | Short-term memory (recent task history) |
| Experiential Memory (strategy/skill) | Long-term memory (learned patterns) |

The survey's emphasis on **memory evolution** (consolidation, forgetting) is a gap in most existing frameworks and represents an opportunity for Orchestra to differentiate.

---

## 5. Redis AI Agent Memory

### Overview

Redis has positioned itself as a "context engine" for AI agents, providing an in-memory data store that combines structured state management with semantic search capabilities. The official `redis/agent-memory-server` project provides a purpose-built memory server for agent systems.

### Architecture

Redis Agent Memory Server implements a dual-tier architecture:

| Tier | Storage | Access Pattern | Latency |
|------|---------|---------------|---------|
| **Short-term** | In-memory Redis data structures (hashes, lists, sorted sets) | Direct key lookup, recency-based | Microseconds |
| **Long-term** | Redis vector search (RediSearch module) | Semantic similarity search | Low milliseconds |

### How Redis Handles Semantic Search + Structured State

Redis combines multiple capabilities in a single system:

1. **Vector search:** Redis Stack includes RediSearch with vector indexing (HNSW algorithm), enabling semantic similarity search over embedded memories
2. **Structured state:** RedisJSON stores extracted facts, user profiles, and agent state as semi-structured JSON documents with exact match and range queries
3. **Hybrid retrieval:** Production systems use structured lookups first (exact match on user IDs, preferences, timestamps) with vector search as a second pass for semantic relevance
4. **Semantic caching:** Vector embedding-based response caching can reduce LLM API calls by ~69%

### Key Strengths

- **Sub-millisecond structured lookups:** Critical when latency compounds across multiple reasoning steps
- **Unified platform:** Single system for caching, state, vectors, and pub/sub (no need for separate vector DB)
- **Production maturity:** Redis is battle-tested at scale in production environments
- **Session management:** Built-in TTL (time-to-live) for automatic expiration of short-term memories
- **Pub/Sub:** Can notify agents of memory changes in real-time

### Limitations for Orchestra

- Requires Redis Stack (not just base Redis) for vector search and JSON capabilities
- No built-in LLM-powered extraction or consolidation (you must implement this yourself)
- Memory is volatile by default -- requires persistence configuration (RDB/AOF) for durability
- Graph capabilities require a separate module (RedisGraph was deprecated; would need Neo4j or similar for entity relationships)
- Adds an infrastructure dependency that conflicts with Orchestra's "zero-infrastructure" dev experience

---

## 6. Practical Comparison for Orchestra

### Option A: Build 4-Tier from Scratch

| Aspect | Assessment |
|--------|------------|
| **Control** | Full control over every aspect of memory formation, evolution, and retrieval |
| **Performance** | Can optimize for Orchestra's specific access patterns |
| **Maintenance** | Highest maintenance burden -- must implement extraction, consolidation, conflict resolution, vector search, graph queries |
| **Risk** | Risk of building a mediocre version of what Mem0 already does well |
| **Timeline** | 3-6 months of focused development for a production-quality system |
| **Differentiation** | Opportunity to implement novel features (experiential memory, memory evolution) |

### Option B: Integrate Mem0

| Aspect | Assessment |
|--------|------------|
| **Control** | Good -- Mem0 is modular and configurable, supports multiple backends |
| **Performance** | Proven 26% accuracy improvement; adds LLM latency for extraction |
| **Maintenance** | Low for memory management; Mem0 team maintains core logic |
| **Risk** | Dependency on external project; Mem0's extraction quality depends on LLM choice |
| **Timeline** | 2-4 weeks for integration behind an abstraction layer |
| **Compatibility** | Apache 2.0 license; supports pgvector (aligns with Orchestra's PostgreSQL strategy) |

### Option C: Use Redis

| Aspect | Assessment |
|--------|------------|
| **Control** | Medium -- Redis provides storage primitives, not memory intelligence |
| **Performance** | Excellent latency; no built-in extraction or consolidation |
| **Maintenance** | Medium -- Redis is mature, but you must build all memory logic yourself |
| **Risk** | Adds infrastructure requirement; Redis Stack is less common than base Redis |
| **Timeline** | 1-2 months for storage layer; still need extraction/consolidation logic |
| **Trade-off** | Gets you fast storage but not the "smart" parts of memory management |

### Tier-by-Tier Analysis

#### Working Memory (In-Process)

**Recommendation: Always custom (in-process Python)**

- Working memory is the agent's scratchpad during a single execution step
- Must be zero-latency (no network calls)
- Tightly coupled to Orchestra's state graph and reducer system
- No external system is appropriate here
- Implementation: Python dict/dataclass within the graph state, managed by typed reducers

#### Short-Term Memory (Recent Conversation History)

| Option | Pros | Cons |
|--------|------|------|
| **SQLite/PostgreSQL (custom)** | Zero-dependency in dev (SQLite); production-grade in prod (PostgreSQL); full control over schema; aligns with event-sourcing architecture | Must implement summarization/compression yourself |
| **Mem0** | Automatic extraction and deduplication; rolling summary built-in | Overkill for recent history; adds LLM call overhead for every interaction |
| **Redis** | Fastest access; built-in TTL for expiration; great for session state | Infrastructure dependency; no extraction logic |

**Recommendation: Custom (SQLite in dev, PostgreSQL in prod)**

Short-term memory in Orchestra is essentially the recent event log from the event-sourced architecture. It should store raw events and maintain a rolling window. Adding Mem0 here would impose unnecessary LLM calls for what is fundamentally a storage and windowing problem. A custom implementation using SQLite/PostgreSQL is simpler, faster, and aligns with Orchestra's existing persistence strategy.

#### Long-Term Memory (Persistent Knowledge Across Sessions)

| Option | Pros | Cons |
|--------|------|------|
| **pgvector (custom)** | Single database (PostgreSQL) for everything; full control; no new dependencies | Must implement extraction, consolidation, conflict resolution, vector indexing yourself |
| **Mem0** | Battle-tested extraction and consolidation; 26% accuracy improvement; supports pgvector as backend; handles deduplication and conflict resolution | LLM dependency for extraction; another dependency to manage |
| **Supermemory** | SOTA benchmark results; handles temporal reasoning and knowledge updates | API-first design (not embeddable library); less proven in production |

**Recommendation: Mem0 as optional backend behind Orchestra's MemoryBackend protocol**

Long-term memory is where the "smart" parts matter most -- extraction quality, deduplication, conflict resolution, and semantic retrieval. These are exactly what Mem0 excels at. Orchestra should:
1. Define a `MemoryBackend` protocol (interface) for long-term memory
2. Ship a simple pgvector-based implementation as the default (no external dependencies)
3. Provide a Mem0 adapter as an optional, recommended upgrade (`pip install orchestra[mem0]`)
4. The Mem0 adapter uses pgvector as Mem0's vector backend, keeping PostgreSQL as the single database

This gives users a working system out of the box with a clear upgrade path.

#### Entity Memory (Structured Knowledge About Entities)

| Option | Pros | Cons |
|--------|------|------|
| **Custom EAV (Entity-Attribute-Value)** | Simple schema in PostgreSQL; full control; queryable with SQL | Limited relationship traversal; no native graph queries |
| **Mem0g (Graph)** | Rich relationship modeling; temporal reasoning; multi-hop queries; proven architecture | Requires Neo4j (heavy infrastructure); couples to Mem0's extraction pipeline |
| **Custom + pgvector** | Entity profiles as JSON documents with vector embeddings; hybrid search | Limited to single-hop relationships; no graph traversal |

**Recommendation: Custom EAV with PostgreSQL as default; Mem0g as optional advanced backend**

Entity memory in most agent applications involves storing structured facts about known entities (users, projects, documents). A PostgreSQL-based EAV or JSONB schema handles 90% of use cases without requiring a graph database. For applications that genuinely need multi-hop relationship traversal (e.g., "who is connected to whom through which projects"), Mem0g with Neo4j is the proven solution.

Orchestra should:
1. Ship a PostgreSQL JSONB-based entity store as the default
2. Support optional Neo4j-backed graph memory (either via Mem0g or a custom adapter)
3. The graph backend should be a progressive upgrade, not a requirement

---

## 7. Recommendation

### Summary Architecture

```
Orchestra Memory Architecture
==============================

Tier 1: WORKING MEMORY          -> Always custom (in-process Python)
   - Python dict/dataclass in graph state
   - Managed by typed reducers
   - Zero-latency, zero-dependency

Tier 2: SHORT-TERM MEMORY       -> Custom (SQLite dev / PostgreSQL prod)
   - Event log with rolling window
   - Recent messages + rolling summary
   - Built on event-sourcing architecture
   - TTL-based expiration

Tier 3: LONG-TERM MEMORY        -> Custom pgvector default + optional Mem0
   - Default: Simple pgvector semantic search
   - Upgrade: Mem0 adapter (extraction, consolidation, dedup)
   - Both use PostgreSQL as single database
   - MemoryBackend protocol for pluggability

Tier 4: ENTITY MEMORY           -> Custom PostgreSQL JSONB default + optional graph
   - Default: JSONB entity profiles with attribute tracking
   - Upgrade: Neo4j graph backend (via Mem0g or custom)
   - EntityStore protocol for pluggability
```

### Key Design Decisions

1. **Protocol-first design:** Define `MemoryBackend` and `EntityStore` protocols. All implementations (custom, Mem0, Redis, etc.) implement these protocols. Users can swap backends without changing application code.

2. **PostgreSQL as the universal backend:** All default implementations use PostgreSQL (with SQLite for development). This aligns with Orchestra's zero-infrastructure-to-production strategy and avoids forcing users to run Redis, Neo4j, or other systems.

3. **Mem0 as the recommended upgrade, not a requirement:** The simple pgvector implementation works out of the box. Mem0 is an optional extra for users who want production-grade memory management. This preserves Orchestra's "single `pip install`" philosophy.

4. **Memory evolution is the differentiator:** The survey (arxiv 2512.13564) identifies memory consolidation, conflict resolution, and forgetting as under-studied. Orchestra should invest in these capabilities, either through Mem0 integration or custom implementation. This is where the framework can genuinely differentiate.

5. **Experiential memory as a future tier:** The survey identifies experiential memory (learning from past task execution) as high-impact. Orchestra should plan for a 5th tier -- skill/strategy memory -- that stores successful tool compositions and reasoning patterns for reuse. No existing framework does this well.

### Integration Effort Estimates

| Component | Effort | Dependencies |
|-----------|--------|--------------|
| Working memory (in-process) | 1-2 weeks | None (pure Python) |
| Short-term memory (event log) | 2-3 weeks | SQLite/PostgreSQL |
| Long-term memory (pgvector default) | 3-4 weeks | PostgreSQL + pgvector |
| Long-term memory (Mem0 adapter) | 1-2 weeks | mem0ai package |
| Entity memory (JSONB default) | 2-3 weeks | PostgreSQL |
| Entity memory (graph adapter) | 2-3 weeks | Neo4j (optional) |
| MemoryBackend/EntityStore protocols | 1 week | None |
| **Total (defaults only)** | **~10 weeks** | PostgreSQL |
| **Total (with all adapters)** | **~14 weeks** | PostgreSQL, mem0ai, Neo4j |

---

## Sources

### Mem0
- [GitHub - mem0ai/mem0](https://github.com/mem0ai/mem0)
- [Mem0 Research Paper (arxiv 2504.19413)](https://arxiv.org/abs/2504.19413)
- [Mem0 Research Page - 26% Accuracy Boost](https://mem0.ai/research)
- [Mem0 Graph Memory Documentation](https://docs.mem0.ai/open-source/features/graph-memory)
- [AWS Integration - Mem0 + ElastiCache + Neptune](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/)
- [Mem0 Python SDK Quickstart](https://docs.mem0.ai/open-source/python-quickstart)
- [mem0ai on PyPI](https://pypi.org/project/mem0ai/)

### MemOS
- [GitHub - BAI-LAB/MemoryOS (EMNLP 2025 Oral)](https://github.com/BAI-LAB/MemoryOS)
- [GitHub - MemTensor/MemOS](https://github.com/MemTensor/MemOS)
- [MemOS Paper (arxiv 2507.03724)](https://arxiv.org/abs/2507.03724)
- [MemOS Short Version (arxiv 2505.22101)](https://arxiv.org/abs/2505.22101)
- [VentureBeat - Chinese Researchers Unveil MemOS](https://venturebeat.com/ai/chinese-researchers-unveil-memos-the-first-memory-operating-system-that-gives-ai-human-like-recall/)

### Supermemory
- [Supermemory Research](https://supermemory.ai/research)
- [GitHub - supermemoryai/supermemory](https://github.com/supermemoryai/supermemory)
- [LongMemEval Paper (arxiv 2410.10813)](https://arxiv.org/abs/2410.10813)
- [LongMemEval GitHub](https://github.com/xiaowu0162/LongMemEval)

### Survey
- [Memory in the Age of AI Agents (arxiv 2512.13564)](https://arxiv.org/abs/2512.13564)
- [Agent Memory Paper List (GitHub)](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- [AlphaXiv Discussion](https://www.alphaxiv.org/resources/2512.13564v1)

### Redis
- [Redis AI Agent Memory Blog](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [Redis Agent Memory Server (GitHub)](https://github.com/redis/agent-memory-server)
- [Redis Agent Memory Server Docs](https://redis.github.io/agent-memory-server/)
- [Redis - Build Smarter AI Agents](https://redis.io/blog/build-smarter-ai-agents-manage-short-term-and-long-term-memory-with-redis/)
- [Redis vs Postgres for Agent State (SitePoint)](https://www.sitepoint.com/state-management-for-long-running-agents-redis-vs-postgres/)
