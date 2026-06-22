#!/usr/bin/env python3
"""Deploy Reviewer Agent — reviews deployments before approval.

Reviews pending ArgoCD syncs against Prometheus SLO/SLI health
before approving a rollout.

This agent can run with either AutoGen or LangGraph as its brain.

Usage (via CLI):
    devops-agent run --agent deploy-reviewer --brain langgraph
    devops-agent run --agent deploy-reviewer --brain autogen --namespace production

Direct usage:
    python agents/deploy-reviewer-agent.py --brain langgraph --config <config.yaml>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

# Add project root to path for tool imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.argocd import (
    get_app_sync_status,
    list_out_of_sync_apps,
    get_app_diff,
    trigger_sync,
)
from tools.prometheus import query_metric, get_alerts_firing, get_error_rate

logger = logging.getLogger("deploy-reviewer-agent")

# ---------------------------------------------------------------------------
# Agent Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_app_sync_status",
        "description": "Returns sync and health status of an ArgoCD app",
        "function": get_app_sync_status,
        "parameters": {"app_name": {"type": "string", "required": True}},
    },
    {
        "name": "list_out_of_sync_apps",
        "description": "Lists all apps with OutOfSync status",
        "function": list_out_of_sync_apps,
        "parameters": {},
    },
    {
        "name": "get_app_diff",
        "description": "Returns the live vs desired diff for an app",
        "function": get_app_diff,
        "parameters": {"app_name": {"type": "string", "required": True}},
    },
    {
        "name": "trigger_sync",
        "description": "Triggers a sync for a specific ArgoCD application",
        "function": trigger_sync,
        "parameters": {
            "app_name": {"type": "string", "required": True},
            "prune": {"type": "boolean", "default": False},
            "dry_run": {"type": "boolean", "default": False},
        },
    },
    {
        "name": "query_metric",
        "description": "Executes an instant PromQL query",
        "function": query_metric,
        "parameters": {"promql": {"type": "string", "required": True}},
    },
    {
        "name": "get_alerts_firing",
        "description": "Returns all currently firing Prometheus alerts",
        "function": get_alerts_firing,
        "parameters": {},
    },
    {
        "name": "get_error_rate",
        "description": "Returns HTTP error rate for a service",
        "function": get_error_rate,
        "parameters": {
            "service": {"type": "string", "required": True},
            "namespace": {"type": "string", "default": "default"},
            "window": {"type": "string", "default": "5m"},
        },
    },
]

SYSTEM_PROMPT = """You are a Deploy Reviewer agent. Your job is to evaluate
whether a pending ArgoCD deployment is safe to proceed. Follow this workflow:

1. List all out-of-sync ArgoCD applications
2. For each pending deployment:
   a. Get the app diff to understand what will change
   b. Check Prometheus for any currently firing alerts
   c. Check the error rate for the affected services
   d. Query relevant SLO/SLI metrics
3. Make a GO / NO-GO recommendation for each deployment:
   - GO: No firing alerts, error rate below 1%, SLOs healthy
   - NO-GO: Active alerts, elevated error rate, or degraded SLOs
4. If GO and not in dry-run mode, trigger the sync
5. Provide a detailed report explaining your reasoning

Be conservative — when in doubt, recommend NO-GO and explain why.
"""


# ---------------------------------------------------------------------------
# Brain Runners
# ---------------------------------------------------------------------------


def run_with_autogen(config: dict, namespace: str, dry_run: bool) -> None:
    """Run the deploy reviewer agent using AutoGen as the brain."""
    logger.info("Starting deploy-reviewer with AutoGen brain")

    try:
        from autogen import AssistantAgent, UserProxyAgent
    except ImportError:
        logger.error(
            "AutoGen not installed. Run: pip install -r agent-brain/autogen/"
            "python/packages/autogen-agentchat/requirements.txt"
        )
        sys.exit(1)

    tool_functions = {t["name"]: t["function"] for t in TOOLS}

    llm_config = {
        "model": config.get("model", "gpt-4o"),
        "temperature": config.get("temperature", 0.2),
    }

    assistant = AssistantAgent(
        name="deploy_reviewer",
        system_message=SYSTEM_PROMPT,
        llm_config={"config_list": [llm_config]},
    )

    user_proxy = UserProxyAgent(
        name="devops_operator",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=config.get("max_rounds", 10),
        code_execution_config=False,
    )

    for tool_name, tool_fn in tool_functions.items():
        assistant.register_for_llm(name=tool_name, description=f"Tool: {tool_name}")(
            tool_fn
        )
        user_proxy.register_for_execution(name=tool_name)(tool_fn)

    task = (
        f"Review all pending ArgoCD deployments in namespace '{namespace}'. "
        f"Check health metrics before approving."
    )
    if dry_run:
        task += " This is a DRY RUN — do not trigger any syncs."

    user_proxy.initiate_chat(assistant, message=task)


def run_with_langgraph(config: dict, namespace: str, dry_run: bool) -> None:
    """Run the deploy reviewer agent using LangGraph as the brain."""
    logger.info("Starting deploy-reviewer with LangGraph brain")

    try:
        from langchain_core.tools import tool as langchain_tool
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        logger.error(
            "LangGraph not installed. Run: pip install langgraph langchain-openai"
        )
        sys.exit(1)

    lc_tools = []
    for t in TOOLS:
        fn = t["function"]
        wrapped = langchain_tool(fn)
        lc_tools.append(wrapped)

    model = ChatOpenAI(
        model=config.get("model", "gpt-4o"),
        temperature=config.get("temperature", 0.2),
    )

    agent = create_react_agent(
        model,
        tools=lc_tools,
        state_modifier=SYSTEM_PROMPT,
    )

    task = (
        f"Review all pending ArgoCD deployments in namespace '{namespace}'. "
        f"Check health metrics before approving."
    )
    if dry_run:
        task += " This is a DRY RUN — do not trigger any syncs."

    result = agent.invoke(
        {"messages": [("user", task)]},
        config={"recursion_limit": config.get("recursion_limit", 25)},
    )

    for msg in result.get("messages", []):
        if hasattr(msg, "content") and msg.content:
            print(msg.content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy Reviewer Agent")
    parser.add_argument(
        "--brain",
        required=True,
        choices=["autogen", "langgraph"],
        help="Agent brain to use",
    )
    parser.add_argument(
        "--config", required=True, help="Path to brain config YAML"
    )
    parser.add_argument(
        "--namespace", default="default", help="Kubernetes namespace"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without executing"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info("Loaded config from %s", config_path)

    if args.brain == "autogen":
        run_with_autogen(config, args.namespace, args.dry_run)
    elif args.brain == "langgraph":
        run_with_langgraph(config, args.namespace, args.dry_run)


if __name__ == "__main__":
    main()
