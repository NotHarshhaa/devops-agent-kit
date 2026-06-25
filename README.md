<div align="center">

<img src="https://img.shields.io/badge/devops--agent--kit-v0.1.0-blue?style=for-the-badge&logo=github" alt="version"/>
<img src="https://img.shields.io/badge/Go-CLI-00ADD8?style=for-the-badge&logo=go" alt="go"/>
<img src="https://img.shields.io/badge/Submodules-AutoGen%20%7C%20LangGraph-orange?style=for-the-badge" alt="submodules"/>
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="license"/>
<img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge" alt="prs"/>

<br/><br/>

# 🤖 devops-agent-kit

**A modular agentic AI toolkit for DevOps automation.**  
Bring AI-powered reasoning to your Kubernetes, ArgoCD, and Prometheus workflows —  
with a Go CLI, pluggable tool bindings, and dual agent brains (AutoGen + LangGraph) as submodules.

<br/>

[Getting Started](#-getting-started) · [Architecture](#-architecture) · [Agents](#-agents) · [Tool Bindings](#-tool-bindings) · [CLI Reference](#-cli-reference) · [Contributing](#-contributing)

</div>

---

## 📖 Overview

`devops-agent-kit` is a batteries-included framework for building **DevOps AI agents** that reason over your infrastructure state. It ships with:

- A **Go CLI** (`devops-agent`) to run agents from your terminal or CI pipelines
- **Two agentic AI frameworks** as Git submodules — Microsoft AutoGen and LangChain LangGraph — letting you pick the reasoning engine that fits the task
- **Tool bindings** for Kubernetes, ArgoCD, and Prometheus — the agent's hands-on-keyboard layer
- **Pre-built agents** for drift detection, deploy review, and infra monitoring out of the box

The design philosophy is simple: **your orchestration layer stays in control**, the AI brain plugs in as a dependency.

---

## 🏗️ Architecture

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

### Key Design Decisions

| Concern | Choice | Why |
|---|---|---|
| CLI language | Go | Fast binary, single artifact, easy CI integration |
| Agent brains | AutoGen + LangGraph (submodules) | Pick per-task; no hard lock-in |
| Tool bindings | Python | Native Kubernetes/Prom client libraries |
| Config format | YAML | GitOps-friendly, human-readable |

---

## 🚀 Getting Started

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Go | `>= 1.21` | Build the CLI |
| Python | `>= 3.10` | Run agents and tool bindings |
| Git | `>= 2.20` | Submodule support |
| kubectl | any | Kubernetes tool binding |
| ArgoCD CLI | any | ArgoCD tool binding (optional) |

### Clone with Submodules

```bash
# Clone the repo and initialize both submodules in one step
git clone --recurse-submodules https://github.com/NotHarshhaa/devops-agent-kit.git
cd devops-agent-kit
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

### Build the CLI

```bash
make build
# Binary output: ./bin/devops-agent
```

Or manually:

```bash
cd cli && go build -o ../bin/devops-agent .
```

### Install Python Dependencies

```bash
# Install tool binding dependencies
pip install -r tools/requirements.txt

# Install agent brain dependencies (choose one or both)
pip install -r agent-brain/autogen/python/packages/autogen-agentchat/requirements.txt
pip install -r agent-brain/langgraph/requirements.txt
```

---

## 🤖 Agents

Three agents ship out of the box. All are defined in `agents/` and can use either brain.

### `drift-detector-agent`
Queries Kubernetes and ArgoCD state, compares against declared Git config, and reports infrastructure drift.

```bash
./bin/devops-agent run --agent drift-detector --brain autogen
```

### `deploy-reviewer-agent`
Reviews pending ArgoCD syncs against Prometheus SLO/SLI health before approving a rollout.

```bash
./bin/devops-agent run --agent deploy-reviewer --brain langgraph
```

### `infra-monitor-agent`
Continuously polls Prometheus metrics, detects anomalies, and surfaces actionable summaries.

```bash
./bin/devops-agent run --agent infra-monitor --brain autogen --interval 5m
```

---

## 🔧 Tool Bindings

Tool bindings live in `tools/` and are the interface between the agent brain and your infrastructure. Each binding exposes a set of named tools that agents can call.

### Kubernetes (`tools/kubernetes/k8s_tool.py`)

| Tool | Description |
|---|---|
| `get_pod_status` | Returns status of pods in a namespace |
| `describe_deployment` | Describes a deployment and its replica state |
| `get_failing_pods` | Lists all pods not in a Running/Completed state |
| `get_node_pressure` | Returns node resource pressure conditions |

### ArgoCD (`tools/argocd/argocd_tool.py`)

| Tool | Description |
|---|---|
| `get_app_sync_status` | Returns sync and health status of an ArgoCD app |
| `list_out_of_sync_apps` | Lists all apps with OutOfSync status |
| `get_app_diff` | Returns the live vs desired diff for an app |
| `trigger_sync` | Triggers a sync for a specific application |

### Prometheus (`tools/prometheus/prom_tool.py`)

| Tool | Description |
|---|---|
| `query_metric` | Executes an instant PromQL query |
| `query_range` | Executes a range PromQL query |
| `get_alerts_firing` | Returns all currently firing Prometheus alerts |
| `get_error_rate` | Returns HTTP error rate for a service |

---

## 🧠 Choosing a Brain

Both agent brains are included as Git submodules under `agent-brain/`. You can choose per agent invocation.

| Brain | Best For | Flag |
|---|---|---|
| **AutoGen** (Microsoft) | Multi-agent conversations, role-based workflows | `--brain autogen` |
| **LangGraph** (LangChain) | Graph-based agent flows, complex decision trees | `--brain langgraph` |

Configure each brain in `orchestration/configs/`:

```yaml
# orchestration/configs/autogen-config.yaml
model: gpt-4o
temperature: 0.2
max_rounds: 10
tools_enabled: true
```

```yaml
# orchestration/configs/langgraph-config.yaml
model: gpt-4o
recursion_limit: 25
checkpointer: memory
```

---

## 📟 CLI Reference

```
devops-agent — AI-powered DevOps automation CLI

USAGE:
  devops-agent [command] [flags]

COMMANDS:
  run       Run an agent with a specified brain and tool bindings
  status    Check health of connected tool bindings
  version   Print CLI version

FLAGS:
  -p, --pipeline  Path to pipeline YAML configuration
  --agent      Agent to run (drift-detector | deploy-reviewer | infra-monitor)
  --brain      Agent brain to use (autogen | langgraph)
  --namespace  Kubernetes namespace to target (default: default)
  --interval   Polling interval for continuous agents (e.g. 5m)
  --dry-run    Preview agent actions without executing
  --verbose    Enable verbose output

EXAMPLES:
  devops-agent run --pipeline orchestration/pipelines/argocd-agent.yaml
  devops-agent run --agent drift-detector --brain autogen
  devops-agent run --agent deploy-reviewer --brain langgraph --namespace production
  devops-agent run --agent infra-monitor --brain autogen --interval 10m
  devops-agent status
```

---

## 🛠️ Makefile Reference

```bash
make init          # Initialize all submodules
make build         # Build the Go CLI binary
make run-drift     # Run drift-detector with AutoGen
make run-deploy    # Run deploy-reviewer with LangGraph
make status        # Check tool bindings health
make update-subs   # Pull latest commits for all submodules
make clean         # Remove build artifacts
```

---

## 🔄 Managing Submodules

### Update submodules to latest upstream

```bash
# Update both agent brains
git submodule update --remote --merge

# Update a specific one
git submodule update --remote agent-brain/autogen
```

### Pin submodules to a specific commit

```bash
cd agent-brain/autogen
git checkout v0.4.0
cd ../..
git add agent-brain/autogen
git commit -m "chore: pin autogen to v0.4.0"
```

### Check submodule status

```bash
git submodule status
```

---

## 🗺️ Roadmap

- [x] `drift-detector-agent` — initial implementation
- [x] `deploy-reviewer-agent` — initial implementation  
- [x] `infra-monitor-agent` — initial implementation
- [x] Go CLI `run` and `status` commands (including cross-platform resolution and pipeline parsing)
- [x] Kubernetes tool bindings
- [x] ArgoCD tool bindings
- [x] Prometheus tool bindings
- [x] AutoGen brain config wiring
- [x] LangGraph brain config wiring
- [x] Agent result output to Slack (via notifications configuration in pipeline runner)
- [ ] GitHub Actions workflow for CI
- [ ] Helm chart for in-cluster deployment
- [ ] Support for additional brains (CrewAI, OpenAI Swarm)
- [ ] Agent result output to PagerDuty

---

## 🤝 Contributing

Contributions are welcome — new tool bindings, agents, brain integrations, and bug fixes.

```bash
# Fork and clone
git clone --recurse-submodules https://github.com/YOUR_USERNAME/devops-agent-kit.git

# Create a feature branch
git checkout -b feat/my-new-tool-binding

# Make changes, then open a PR against main
```

Please follow the existing pattern for tool bindings — each tool should be a named function with a clear docstring describing its inputs and outputs, so agent brains can discover and call them correctly.

---

## 📄 License

MIT License — see [LICENSE](./LICENSE) for details.

---

<div align="center">

Built by [@NotHarshhaa](https://github.com/NotHarshhaa) · Part of the [KranixIO](https://github.com/KranixIO) ecosystem

⭐ Star this repo if it saves you an on-call page

</div>
