# Architecture

This document describes the architecture of `devops-agent-kit` — a modular agentic AI toolkit for DevOps automation.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   devops-agent-kit                      │
│                                                         │
│  ┌──────────┐    ┌─────────────────────────────────┐   │
│  │  Go CLI  │───▶│        Agent Definitions         │   │
│  │          │    │  drift-detector-agent.py         │   │
│  │ cmd run  │    │  deploy-reviewer-agent.py        │   │
│  │ cmd status    │  infra-monitor-agent.py          │   │
│  └──────────┘    └────────────┬────────────────────┘   │
│                               │                         │
│              ┌────────────────▼──────────────────┐     │
│              │         Tool Bindings              │     │
│              │  kubernetes/ argocd/ prometheus/   │     │
│              └────────────────┬──────────────────┘     │
│                               │                         │
│         ┌─────────────────────▼──────────────────┐     │
│         │          agent-brain/ (submodules)      │     │
│         │   autogen/          langgraph/          │     │
│         │   microsoft/autogen langchain-ai/       │     │
│         │                     langgraph           │     │
│         └────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

## Layers

### 1. Go CLI (`cli/`)

The CLI is the user-facing entry point. It is built in Go using the [Cobra](https://cobra.dev/) library and compiles to a single static binary.

**Responsibilities:**
- Parse user commands and flags
- Validate agent and brain selection
- Resolve project paths and config files
- Shell out to Python to launch agents
- Check health of tool binding backends

**Commands:**
| Command | Description |
|---------|-------------|
| `run` | Launch an agent with a specified brain |
| `status` | Check connectivity to K8s, ArgoCD, Prometheus |
| `version` | Print version and build info |

### 2. Agent Definitions (`agents/`)

Each agent is a Python script that wires together tool bindings with a brain. Agents accept CLI arguments for:
- Brain selection (`--brain autogen|langgraph`)
- Brain config path (`--config <path>`)
- Kubernetes namespace (`--namespace`)
- Polling interval (`--interval`, for continuous agents)
- Dry-run mode (`--dry-run`)

Agents define:
- A `TOOLS` list describing available tools
- A `SYSTEM_PROMPT` guiding the AI's behavior
- `run_with_autogen()` and `run_with_langgraph()` functions

### 3. Tool Bindings (`tools/`)

Tool bindings are the agent's interface to infrastructure. Each binding is a Python module exposing named functions with clear docstrings.

**Design principles:**
- Functions return structured dicts (never raw strings)
- Each function has a docstring describing inputs and outputs
- Error cases return `{"error": "..."}` instead of raising
- Configuration via environment variables

### 4. Agent Brains (`agent-brain/`)

Two AI reasoning frameworks are included as Git submodules:

| Brain | Source | Best For |
|-------|--------|----------|
| AutoGen | `microsoft/autogen` | Multi-agent conversations, role-based workflows |
| LangGraph | `langchain-ai/langgraph` | Graph-based agent flows, complex decision trees |

Brains are configured via YAML files in `orchestration/configs/`.

### 5. Orchestration (`orchestration/`)

Contains pipeline definitions and brain configurations:
- **Pipelines** (`pipelines/`) define end-to-end workflows including which agent, brain, tools, thresholds, and schedules to use
- **Configs** (`configs/`) define brain-specific settings (model, temperature, limits)

## Data Flow

```
User/CI
  │
  ▼
Go CLI (devops-agent run --agent X --brain Y)
  │
  ├─ Validates flags
  ├─ Resolves paths
  │
  ▼
Python Agent Script (agents/X-agent.py)
  │
  ├─ Loads brain config (orchestration/configs/Y-config.yaml)
  ├─ Registers tool bindings
  ├─ Initializes brain (AutoGen or LangGraph)
  │
  ▼
AI Brain (agent-brain/Y/)
  │
  ├─ Receives system prompt + task
  ├─ Reasons about which tools to call
  │
  ▼
Tool Bindings (tools/kubernetes|argocd|prometheus)
  │
  ├─ Calls infrastructure APIs
  ├─ Returns structured data
  │
  ▼
AI Brain
  │
  ├─ Analyzes results
  ├─ Decides next action or generates report
  │
  ▼
Output (stdout / future: Slack, PagerDuty)
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Go for the CLI | Fast binary, single artifact, easy CI integration, no runtime dependencies |
| Python for tools and agents | Rich ecosystem of K8s/Prom/ArgoCD client libraries |
| Submodules for brains | No hard lock-in; update independently; pick per task |
| YAML for config | GitOps-friendly, human-readable, easy to diff |
| Structured dict returns | Agents can reason over data; no brittle string parsing |
| Environment-based tool config | 12-factor friendly; works in containers and CI |

## Security Considerations

- **ArgoCD tokens** should be stored in environment variables or secrets managers, never in config files
- **Kubernetes access** follows the principle of least privilege — the service account or kubeconfig should only have the permissions needed by the tool bindings
- **Dry-run mode** is available on all agents to preview actions without executing
- **The `trigger_sync` tool** is the only mutating operation; all others are read-only
