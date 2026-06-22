#!/usr/bin/env python3
"""Infra Monitor Agent — continuous infrastructure monitoring.

Continuously polls Prometheus metrics, detects anomalies, and
surfaces actionable summaries. Supports a configurable polling
interval for long-running monitoring sessions.

This agent can run with either AutoGen or LangGraph as its brain.

Usage (via CLI):
    devops-agent run --agent infra-monitor --brain autogen --interval 5m
    devops-agent run --agent infra-monitor --brain langgraph --interval 10m

Direct usage:
    python agents/infra-monitor-agent.py --brain autogen --config <config.yaml> --interval 5m
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import signal
import sys
import time
from pathlib import Path

import yaml

# Add project root to path for tool imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.kubernetes import get_pod_status, get_failing_pods, get_node_pressure
from tools.prometheus import query_metric, query_range, get_alerts_firing, get_error_rate

logger = logging.getLogger("infra-monitor-agent")

# ---------------------------------------------------------------------------
# Agent Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_pod_status",
        "description": "Returns status of pods in a namespace",
        "function": get_pod_status,
        "parameters": {"namespace": {"type": "string", "default": "default"}},
    },
    {
        "name": "get_failing_pods",
        "description": "Lists all pods not in a Running/Completed state",
        "function": get_failing_pods,
        "parameters": {"namespace": {"type": "string", "default": "default"}},
    },
    {
        "name": "get_node_pressure",
        "description": "Returns node resource pressure conditions",
        "function": get_node_pressure,
        "parameters": {},
    },
    {
        "name": "query_metric",
        "description": "Executes an instant PromQL query",
        "function": query_metric,
        "parameters": {"promql": {"type": "string", "required": True}},
    },
    {
        "name": "query_range",
        "description": "Executes a range PromQL query over a time window",
        "function": query_range,
        "parameters": {
            "promql": {"type": "string", "required": True},
            "start": {"type": "number", "default": None},
            "end": {"type": "number", "default": None},
            "step": {"type": "string", "default": "60s"},
        },
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

SYSTEM_PROMPT = """You are an Infrastructure Monitoring agent. Your job is to
continuously monitor the health of infrastructure and detect anomalies.

For each monitoring cycle:
1. Check for any currently firing Prometheus alerts
2. Look for pods in a failing state
3. Check node resource pressure (memory, disk, PID)
4. Query key metrics:
   - CPU utilization across nodes
   - Memory usage trends
   - Error rates for critical services
5. Detect anomalies by comparing current values to recent trends
6. Produce a concise status summary:
   - 🟢 HEALTHY: No issues detected
   - 🟡 WARNING: Potential issues that need attention
   - 🔴 CRITICAL: Issues requiring immediate action

Include specific numbers and actionable recommendations. Be concise
but thorough.
"""

# Graceful shutdown flag
_shutdown_requested = False


def _handle_signal(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    logger.info("Shutdown signal received, completing current cycle...")
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Interval Parsing
# ---------------------------------------------------------------------------


def parse_interval(interval_str: str) -> int:
    """Parse a human-readable interval string to seconds.

    Supports formats like '5m', '1h', '30s', '2h30m'.
    """
    if not interval_str:
        return 300  # Default 5 minutes

    total_seconds = 0
    pattern = re.compile(r"(\d+)([smh])")
    matches = pattern.findall(interval_str.lower())

    if not matches:
        try:
            return int(interval_str)
        except ValueError:
            logger.warning("Invalid interval '%s', defaulting to 5m", interval_str)
            return 300

    multipliers = {"s": 1, "m": 60, "h": 3600}
    for value, unit in matches:
        total_seconds += int(value) * multipliers[unit]

    return total_seconds


# ---------------------------------------------------------------------------
# Brain Runners
# ---------------------------------------------------------------------------


def run_with_autogen(config: dict, namespace: str, dry_run: bool) -> str:
    """Run a single monitoring cycle using AutoGen as the brain."""
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
        name="infra_monitor",
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

    task = f"Run an infrastructure health check for namespace '{namespace}'."
    if dry_run:
        task += " This is a DRY RUN — report findings but take no actions."

    result = user_proxy.initiate_chat(assistant, message=task)
    return str(result)


def run_with_langgraph(config: dict, namespace: str, dry_run: bool) -> str:
    """Run a single monitoring cycle using LangGraph as the brain."""
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

    task = f"Run an infrastructure health check for namespace '{namespace}'."
    if dry_run:
        task += " This is a DRY RUN — report findings but take no actions."

    result = agent.invoke(
        {"messages": [("user", task)]},
        config={"recursion_limit": config.get("recursion_limit", 25)},
    )

    output_parts = []
    for msg in result.get("messages", []):
        if hasattr(msg, "content") and msg.content:
            output_parts.append(msg.content)

    return "\n".join(output_parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infra Monitor Agent")
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
        "--interval",
        default="",
        help="Polling interval (e.g. 5m, 1h). If empty, runs once.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without executing"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )
    return parser.parse_args()


def main() -> None:
    global _shutdown_requested
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

    run_fn = run_with_autogen if args.brain == "autogen" else run_with_langgraph

    if args.interval:
        interval_secs = parse_interval(args.interval)
        logger.info(
            "Continuous monitoring mode — interval=%ds, brain=%s",
            interval_secs,
            args.brain,
        )

        cycle = 0
        while not _shutdown_requested:
            cycle += 1
            logger.info("=== Monitoring cycle %d ===", cycle)
            try:
                output = run_fn(config, args.namespace, args.dry_run)
                print(output)
            except Exception:
                logger.exception("Error in monitoring cycle %d", cycle)

            if _shutdown_requested:
                break

            logger.info("Sleeping %ds until next cycle...", interval_secs)
            # Sleep in small increments so we can respond to signals
            for _ in range(interval_secs):
                if _shutdown_requested:
                    break
                time.sleep(1)

        logger.info("Infra monitor shut down after %d cycles", cycle)
    else:
        # Single run mode
        logger.info("Single-run mode — brain=%s", args.brain)
        output = run_fn(config, args.namespace, args.dry_run)
        print(output)


if __name__ == "__main__":
    main()
