# Phase 4: Enterprise & Scale - Research & Keywords

This document tracks technical keywords, architectural concepts, and research topics identified for Phase 4 (Weeks 19-26).

Sources: ROADMAP.md, STRATEGIC-POSITIONING.md, architecture-refinements.md, RECONCILIATION.md, Phase 3 PLAN.md deferrals, EXTERNAL-RESEARCH-SYNTHESIS.md, TREE-OF-THOUGHTS-ANALYSIS.md.

---

## Infrastructure & Scalability
- **Ray Core/Serve**: Engine for distributed execution (Ray Executor). *(Roadmap T-4.x)*
- **NATS JetStream**: Persistence layer for "at-least-once" delivery in asynchronous agent communication. *(Roadmap T-4.x)*
- **Gossip Protocol**: For decentralized agent discovery within the A2A framework.
- **Sidecar Pattern**: Deployment strategy for Agent IAM and security proxies in Kubernetes.
- **Horizontal Pod Autoscaling (HPA)**: Scaling agent workers based on NATS queue depth.
- **Kubernetes Operators**: Custom controllers for managing agent lifecycles in K8s.
- **Kubernetes Deployment**: Enterprise deployment guide with Kubernetes + Terraform. *(Strategic Positioning Phase 3/4 overlap)*
- **OTel Collector Target Allocator**: Kubernetes-native Collector distribution for horizontal-scaled scraping. *(Deferred from Phase 3)*
- **Python Subinterpreters**: CPU-bound parallelism via Python 3.14 subinterpreters. *(Deferred from Phase 3)*
- **Dynamic Subgraphs**: Runtime graph composition and modification. *(Roadmap)*

## Agent IAM & Security
- **DID (Decentralized Identifiers)**: Progressive identity system (`security/identity.py`). *(architecture-refinements.md #3)*
    - `did:web`: Web-based identifier method.
    - `did:peer`: Peer-to-peer identifier method for cross-org trust.
- **AgentIdentity**: Context attribute for agent identity. *(RECONCILIATION.md — `AgentContext.identity`)*
- **Verifiable Credentials (VC)**: For cryptographically proving agent identities and permissions.
- **OIDC Bridge**: Connecting Enterprise IAM (Okta/Auth0) to the Agent DID system.
- **Capability-Based Security (zcap-ld)**: Granular delegation of permissions between agents.
- **Zero-Knowledge Proofs (ZKP)**: Selective disclosure of state during cross-organization handoffs.
- **SecretProvider**: Integration with HashiCorp Vault or AWS/GCP Secret Managers. *(RECONCILIATION.md — `AgentContext.secrets`)*
- **SOC2 Readiness**: Compliance documentation and security audit. *(Strategic Positioning)*

## Cost Routing & Intelligence
- **Cost-Aware Routing**: Dynamic model selection by task complexity. *(Deferred from Phase 3)*
- **Thompson Sampling**: Balancing exploration vs. exploitation in model selection.
- **Model Distillation**: Training specialized, smaller routers on production execution data.
- **SLA-Driven Routing**: Optimization based on "Time to First Token" (TTFT) and latency budgets.
- **Matrix Factorization**: Algorithm for predicting model performance/cost trade-offs.
- **Full Chargeback Billing System**: Per-tenant cost attribution and billing. *(Deferred from Phase 3)*
- **Per-Tenant Persistent Budget Tracking**: Durable budget state across restarts. *(Deferred from Phase 3)*
- **Provider Failover with Strategy Switching**: Auto-switch from Native Schema Enforcement to Prompted+Validation for non-native fallbacks. *(Deferred from Phase 3)*

## Advanced Memory & Data
- **MemoryManager Promote/Demote**: Tier semantics for memory lifecycle (requires multiple storage backends). *(Deferred from Phase 3)*
- **Redis L2 Backplane**: Distributed cache layer with Pub/Sub cache invalidation. *(Deferred from Phase 3)*
- **Warm Tier Semantic Deduplication**: Similarity thresholds (0.85/0.98) for deduplicating stored memories. *(Deferred from Phase 3)*
- **Cold Tier HNSW Vector Retrieval**: Approximate nearest-neighbor search for long-term memory. *(Deferred from Phase 3)*
- **HSM (Hierarchical Storage Management)**: Implementation of the "hot/cold" memory logic.
- **Vector Database (VDB) Sharding**: Scalable storage for massive semantic memory sets.
- **Semantic Caching**: Embedding-based cache lookups for non-exact question matches.
- **State Compression**: Algorithms for minimizing the payload of event-sourced state during large-scale migrations.

## Testing & Quality
- **SPRT Statistical Testing**: Sequential Probability Ratio Test for agent behavior validation. *(Deferred from Phase 3 per ToT analysis)*
- **Behavioral Fingerprinting**: Characterizing agent behavior patterns for regression detection. *(Deferred from Phase 3 per ToT analysis)*
- **Agent Mutation Testing**: Injecting faults into agent logic to verify test suite effectiveness. *(Deferred from Phase 3 per ToT analysis)*

## Safety & Guardrails
- **PromptShield SLM**: Small language model for prompt injection detection (65.3% TPR @ 0.1% FPR). *(Deferred from Phase 3)*

## Interoperability (A2A)
- **A2A Agent Card Registry**: Standardized agent descriptions per Google ADK pattern (`interop/a2a.py`). *(architecture-refinements.md #8)*
- **Agent Manifest (RFC)**: Standardized descriptions of agent tools, costs, and reliability.
- **Arbitration Nodes**: Specialized agents for resolving conflicts/disputes in multi-tenant environments.
- **A2A Protocol**: Governance rules for cross-organizational agent communication.

## SDK & Ecosystem
- **TypeScript Client SDK**: Cross-language client for Orchestra server API. *(Roadmap + Strategic Positioning)*
- **Visual Builder Partnerships**: Integrations with n8n, Flowise. *(Strategic Positioning)*
- **Agent Marketplace**: Community-contributed agent registry. *(Strategic Positioning)*
- **Certification Program**: Orchestra developer certification. *(Strategic Positioning)*

## OTel & Observability
- **OTel Collector Pipeline Config**: Full Collector deployment with pipelines, processors, exporters. *(Deferred from Phase 3)*
- **Prometheus Exporter / Scrape Endpoint**: Exposing AI Golden Signals for Prometheus scraping. *(Deferred from Phase 3)*
- **Sampling Strategy**: Head/tail sampling configuration for production telemetry volume. *(Deferred from Phase 3)*

## Cross-Cutting Architectural Patterns *(NEW — NotebookLM synthesis)*
- **CSCR (Cost-Spectrum Contrastive Routing)**: Shared embedding space with FAISS k-NN for microsecond model selection. *(Cost Routing PDF)*
- **Relay Method**: Save state to DB, kill agent instances between tasks to avoid idle costs. *(Cost Management PDF)*
- **Context Anchoring**: OTel Baggage propagating `tenant_id`/`session_id` to prevent cross-tenant hallucinations. *(Platform Maturity PDF)*
- **Model Aliasing**: Logical descriptors ("high-accuracy") instead of model IDs for zero-code failover. *(Cost Routing PDF)*
- **Zero-Trust Gateway**: Real-time validation on every LLM API call (99% threat reduction). *(Safety PDF)*
- **Trace-First Offline Analysis**: Coverage/contract tests against production traces at zero token cost. *(Quality Assurance PDF)*
- **Progressive Trust (ZKP)**: Incremental trust building via Selective Disclosure. *(IAM PDF)*
- **Hybrid Retrieval**: 30% BM25 + 70% Dense Embedding = 92% Top-10 Accuracy for cold tier. *(Memory PDF)*
- **Reliability Surface R(k,ε,λ)**: Consistency × Robustness × Fault Tolerance evaluation model. *(Quality Assurance PDF)*
- **Token Bucket Rate Limiting**: ~50 bytes/identity, O(1), supports millions of agent identities. *(Safety PDF)*

## Curated Tools & References *(NEW — user-provided)*
- **RouteLLM** (lm-sys/RouteLLM): MF + Controller for cost-aware routing
- **ParticleThompsonSamplingMAB**: Thompson Sampling + MF reference
- **MotleyCrew** (MotleyCrew-AI): Agentic workflows as Ray execution DAGs
- **ConSol** (LiuzLab/consol): SPRT for LLM self-consistency (up to 70% token savings)
- **Neo4j**: Graph memory for warm tier relationship-based retrieval
- **Prompt Guard 86M** (meta-llama): Fast local prompt injection classifier
- **DeBERTa-v3-small injection** (protectai): Smallest injection classifier
- **Certified Self-Consistency** (arXiv 2410.05268): Martingale certificates for agent outputs

## Summary Execution Order (Phase 4 Security & Architecture)

1.  **Isolation & Encryption (Protect the Data):** Implement Wasm sandboxing, gVisor workers, and NATS E2EE with DIDComm.
2.  **Identity & Input Validation (Protect the Access):** Mandate Signed Agent Cards and implement Output Scanning/Capability Attenuation.
3.  **Delegation & State Integrity (Protect the Logic):** Move toward Short-Lived Capabilities (TTLs) and Input Hash Commitments in the ZKP circuit.

---
*Initial: Gemini CLI during Phase 3 Research (2026-03-11)*
*Updated: Cross-referenced with all planning docs (2026-03-11)*
*Updated: NotebookLM PDFs (12 reports) + curated tools integrated (2026-03-11)*
*Updated: Added P0/P1/P2 Security Foundation Research (2026-03-11)*
