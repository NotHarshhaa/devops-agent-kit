#!/usr/bin/env python3
"""Drift Detector Agent — detects infrastructure drift.

Queries Kubernetes and ArgoCD state, compares against declared Git
config, and reports infrastructure drift.

This agent can run with either AutoGen or LangGraph as its brain.

Usage (via CLI):
    devops-agent run --agent drift-detector --brain autogen
    devops-agent run --agent drift-detector --brain langgraph

Direct usage:
    python agents/drift-detector-agent.py --brain autogen --config <config.yaml>
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

from tools.kubernetes import get_pod_status, describe_deployment, get_failing_pods
from tools.argocd import get_app_sync_status, list_out_of_sync_apps, get_app_diff

logger = logging.getLogger("drift-detector-agent")

# ---------------------------------------------------------------------------
# Agent Tool Definitions (for brain registration)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_pod_status",
        "description": "Returns status of pods in a namespace",
        "function": get_pod_status,
        "parameters": {"namespace": {"type": "string", "default": "default"}},
    },
    {
        "name": "describe_deployment",
        "description": "Describes a deployment and its replica state",
        "function": describe_deployment,
        "parameters": {
            "name": {"type": "string", "required": True},
            "namespace": {"type": "string", "default": "default"},
        },
    },
    {
        "name": "get_failing_pods",
        "description": "Lists all pods not in a Running/Completed state",
        "function": get_failing_pods,
        "parameters": {"namespace": {"type": "string", "default": "default"}},
    },
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
]

SYSTEM_PROMPT = """You are a DevOps Drift Detection agent. Your job is to:
1. Check ArgoCD for any out-of-sync applications
2. For each out-of-sync app, get the diff between live and desired state
3. Check Kubernetes for any failing pods that might indicate drift
4. Compile a clear drift report with:
   - Which applications are out of sync
   - What specific resources have drifted
   - Whether any pods are in a failed state
   - Recommended remediation actions

Be thorough and check all available data before reporting. Always provide
actionable recommendations.
"""


# ---------------------------------------------------------------------------
# Brain Runners
# ---------------------------------------------------------------------------


def run_with_autogen(config: dict, namespace: str, dry_run: bool) -> None:
    """Run the drift detector agent using AutoGen as the brain."""
    logger.info("Starting drift-detector with AutoGen brain")

    try:
        from autogen import AssistantAgent, UserProxyAgent
    except ImportError:
        logger.error(
            "AutoGen not installed. Run: pip install -r agent-brain/autogen/"
            "python/packages/autogen-agentchat/requirements.txt"
        )
        sys.exit(1)

    # Build AutoGen tool wrappers
    tool_functions = {t["name"]: t["function"] for t in TOOLS}

    llm_config = {
        "model": config.get("model", "gpt-4o"),
        "temperature": config.get("temperature", 0.2),
    }

    assistant = AssistantAgent(
        name="drift_detector",
        system_message=SYSTEM_PROMPT,
        llm_config={"config_list": [llm_config]},
    )

    user_proxy = UserProxyAgent(
        name="devops_operator",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=config.get("max_rounds", 10),
        code_execution_config=False,
    )

    # Register tools with the assistant
    for tool_name, tool_fn in tool_functions.items():
        assistant.register_for_llm(name=tool_name, description=f"Tool: {tool_name}")(
            tool_fn
        )
        user_proxy.register_for_execution(name=tool_name)(tool_fn)

    task = f"Detect infrastructure drift in namespace '{namespace}'."
    if dry_run:
        task += " This is a DRY RUN — do not make any changes."

    user_proxy.initiate_chat(assistant, message=task)


def run_with_langgraph(config: dict, namespace: str, dry_run: bool) -> None:
    """Run the drift detector agent using LangGraph as the brain."""
    logger.info("Starting drift-detector with LangGraph brain")

    try:
        from langchain_core.tools import tool as langchain_tool
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        logger.error(
            "LangGraph not installed. Run: pip install langgraph langchain-openai"
        )
        sys.exit(1)

    # Wrap tool functions as LangChain tools
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

    task = f"Detect infrastructure drift in namespace '{namespace}'."
    if dry_run:
        task += " This is a DRY RUN — do not make any changes."

    result = agent.invoke(
        {"messages": [("user", task)]},
        config={"recursion_limit": config.get("recursion_limit", 25)},
    )

    # Print final response
    for msg in result.get("messages", []):
        if hasattr(msg, "content") and msg.content:
            print(msg.content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drift Detector Agent")
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

    # Load brain config
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info("Loaded config from %s", config_path)
    logger.info(
        "Config: model=%s, brain=%s",
        config.get("model", "gpt-4o"),
        args.brain,
    )

    if args.brain == "autogen":
        run_with_autogen(config, args.namespace, args.dry_run)
    elif args.brain == "langgraph":
        run_with_langgraph(config, args.namespace, args.dry_run)


if __name__ == "__main__":
    main()
