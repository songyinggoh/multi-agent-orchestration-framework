# A2A Protocol Implementation & Agentic AI Governance Research

**Date:** 2026-03-06
**Status:** COMPLETE
**Constraint:** All free / open-source

---

## Part A: A2A Protocol v1.0

### 1. Protocol Overview

A2A (Agent-to-Agent) is an open protocol donated to the **Linux Foundation**, enabling communication between opaque agentic applications regardless of underlying framework.

- **Transport:** HTTPS (secure by default)
- **Payload:** JSON-RPC 2.0 for all requests/responses
- **Streaming:** SSE (Server-Sent Events) for long-running tasks
- **Status:** Draft v1.0 specification (released from v0.3.0)

### 2. Core Components

| Component | Description |
|---|---|
| **A2A Client** | Application/agent that initiates requests to an A2A Server |
| **A2A Server (Remote Agent)** | Agent system exposing an A2A-compliant endpoint |
| **Agent Card** | JSON metadata document: identity, capabilities, skills, endpoint, auth requirements |

### 3. Agent Card Schema (Key Fields)

```json
{
  "name": "Research Agent",
  "description": "Performs web research and produces summaries",
  "version": "1.0.0",
  "url": "https://agent.example.com/a2a",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "extendedAgentCard": { ... }
  },
  "skills": [
    {
      "id": "web-research",
      "name": "Web Research",
      "description": "Search and synthesize information from the web",
      "inputModes": ["text"],
      "outputModes": ["text", "file"]
    }
  ],
  "authentication": {
    "schemes": ["bearer"],
    "credentials": "https://auth.example.com/.well-known/openid-configuration"
  }
}
```

v1.0 change: `extendedAgentCard` moved from top-level into `capabilities` for architectural consistency.

### 4. Task Lifecycle (JSON-RPC Methods)

| Method | Purpose |
|---|---|
| `tasks/send` | Create or update a task (synchronous) |
| `tasks/sendSubscribe` | Create task with SSE streaming response |
| `tasks/get` | Get task status and result |
| `tasks/cancel` | Cancel a running task |
| `tasks/pushNotification/set` | Register webhook for task updates |

### 5. Existing A2A Implementations

- **Microsoft Agent Framework**: Native A2A integration documented at learn.microsoft.com
- **LangChain/LangSmith**: A2A endpoint support in Agent Server
- **Amazon Bedrock AgentCore**: A2A protocol contract support
- **Spring AI**: Full A2A integration (Jan 2026 blog post)
- **Google ADK**: Original creator, full support

### 6. A2A + MCP Relationship

| Protocol | Purpose | Analogy |
|---|---|---|
| **MCP** | Agent-to-Tool communication ("what tools exist and how to call them") | USB-C (hardware interface) |
| **A2A** | Agent-to-Agent communication ("what agents exist and how to collaborate") | HTTP (service interface) |

They are complementary: an A2A server can expose its agent's capabilities while internally using MCP to access tools. An Orchestra workflow could be both an MCP server (exposing tools) and an A2A server (exposing agent capabilities).

### 7. Orchestra A2A Design

```python
# Orchestra as A2A Server:
# - Every compiled workflow publishes an Agent Card
# - External agents discover via /.well-known/agent.json
# - Invoke via JSON-RPC 2.0 at /a2a endpoint
# - Results streamed via SSE

# Orchestra as A2A Client:
# - Discover external agents by fetching their Agent Cards
# - Wrap external A2A agent as a graph node (A2ANode)
# - Invoke via JSON-RPC, handle streaming responses
# - Apply capability-based security to external agent invocations

class A2ANode(GraphNode):
    """Graph node that invokes an external A2A agent."""
    agent_card: AgentCard
    timeout: float = 30.0
    auth: AuthConfig | None = None
```

---

## Part B: Agentic AI Governance

### 8. EU AI Act Implications (Critical for 2026)

**Timeline:**
- Feb 2025: Prohibited practices provisions took effect
- **Aug 2026: High-risk system rules take effect** — first significant enforcement
- 2027: Full enforcement

**Key requirements for agent systems:**
- **Human oversight mandate**: High-risk AI must enable "effective human oversight" — directly conflicts with full autonomy
- **Transparency**: Every micro-decision must be traceable (audit trails)
- **Risk governance**: Risk assessment required for high-risk agent deployments
- **Accountability**: Clear attribution of agent actions to responsible parties

**Orchestra implications:**
- Event sourcing already provides the audit trail foundation
- HITL autonomy spectrum (in/on/out-of-the-loop) maps to EU AI Act compliance levels
- Agent identity (DID) provides attribution
- Guardrails middleware provides risk mitigation evidence

### 9. Three-Tiered Governance Framework (MintMCP 2026)

| Tier | Scope | Orchestra Feature |
|---|---|---|
| **Agent-level** | Individual agent behavior, tool access, output quality | Capability-based IAM, guardrails middleware |
| **Workflow-level** | Inter-agent coordination, escalation, termination | Graph engine, circuit breakers, kill switches |
| **Organization-level** | Compliance, audit, reporting, cost management | Event sourcing, OTel tracing, cost tracker |

### 10. HITL Autonomy Spectrum (Deloitte 2026)

| Mode | Description | Orchestra Implementation |
|---|---|---|
| **Human-in-the-loop** | Human approves every significant action | `interrupt_before()` on all agent nodes |
| **Human-on-the-loop** | Agent acts freely, human monitors and can veto | Real-time OTel dashboard + kill switch. Agent proceeds unless vetoed within SLO window. |
| **Human-out-of-the-loop** | Full autonomy with audit trail | No interrupts. Full event sourcing. Anomaly detection triggers alerts, not blocks. |

Should be **configurable per-agent and per-workflow**, not a global setting.

---

## Part C: Consensus/Ensemble Routing

### 11. State of the Art (2026)

**Key finding:** Multi-model consensus reduces hallucination by up to **73%** for factual questions (CollectivIQ benchmark, March 2026).

**Approaches:**
| Approach | Method | Best For |
|---|---|---|
| **Majority voting** | Send to N models, take most common answer | Simple factual queries |
| **Mixture-of-Agents** | Models reference each other's outputs iteratively | Complex reasoning |
| **JiSi (Route-and-Aggregate)** | Training-free, dynamic routing + aggregation selection | Scaling with model count |
| **Bayesian orchestration** | Cost-aware sequential decision-making | Budget-constrained scenarios |
| **Higher-order aggregation** | Beyond majority voting, leveraging agreement patterns | Outperforms voting in 16/16 ensembles tested |

**Orchestra integration:** Add as an optional `ConsensusNode` in the graph engine:
```python
graph.add_consensus(
    node_id="fact_check",
    models=["gpt-4o", "claude-sonnet", "gemini-pro"],
    strategy="majority_vote",  # or "mixture_of_agents", "bayesian"
    min_agreement=0.66,
)
```

### 12. Governance Module Design for Orchestra

Orchestra already has strong governance foundations. Additional features needed:

| Feature | Foundation Exists? | Additional Work |
|---|---|---|
| **Full audit trail** | Yes (event sourcing) | Add structured compliance export (JSON/CSV) |
| **Decision explainability** | Partial (OTel traces) | Add "reasoning trace" capture: why did the router choose this agent? |
| **Cost accountability** | Yes (cost tracker) | Add per-department/per-user cost attribution |
| **Risk assessment** | Partial (guardrails) | Add risk scoring per workflow before execution |
| **Compliance reporting** | No | Add `orchestra compliance report` CLI command |
| **Data lineage** | Partial (event sourcing) | Track which data sources influenced which agent decisions |

---

## Sources

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A GitHub (Linux Foundation)](https://github.com/a2aproject/A2A)
- [A2A Protocol Definitions](https://a2a-protocol.org/latest/definitions/)
- [A2A Key Concepts](https://a2a-protocol.org/latest/topics/key-concepts/)
- [A2A Sample Methods and JSON Responses](https://a2aprotocol.ai/docs/guide/a2a-sample-methods-and-json-responses)
- [Amazon Bedrock A2A Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a-protocol-contract.html)
- [LangChain A2A Endpoint](https://docs.langchain.com/langsmith/server-a2a)
- [EU AI Act Portal](https://artificialintelligenceact.eu/)
- [Agentic AI Governance Framework 2026](https://certmage.com/agentic-ai-governance-frameworks/)
- [MintMCP 3-Tiered Governance](https://www.mintmcp.com/blog/agentic-ai-goverance-framework)
- [Deloitte: AI Agent Orchestration 2026](https://www.deloitte.com/us/en/insights/industry/technology/technology-media-and-telecom-predictions/2026/ai-agent-orchestration.html)
- [CollectivIQ: Multi-Model Consensus](https://www.digitalapplied.com/blog/collectiviq-multi-model-ai-consensus-enterprise-platform)
- [JiSi: Route-and-Aggregate LLM Ensemble](https://arxiv.org/html/2601.01330v1)
- [Bayesian Multi-LLM Orchestration](https://arxiv.org/html/2601.01522v1)
- [Higher-Order LLM Aggregation](https://arxiv.org/html/2510.01499v1)
