"""Kubernetes tool bindings — kubectl/K8s API bindings for agents.

Each function acts as a named tool that an agent brain (AutoGen or
LangGraph) can invoke. Functions return structured dicts so the
agent can reason over the output.

Requirements:
    - A valid kubeconfig or in-cluster config
    - `kubernetes` Python package
"""

from __future__ import annotations

import logging
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_config() -> None:
    """Load kubeconfig, preferring in-cluster when available."""
    try:
        config.load_incluster_config()
        logger.debug("Using in-cluster Kubernetes config")
    except config.ConfigException:
        config.load_kube_config()
        logger.debug("Using local kubeconfig")


def _core_v1() -> client.CoreV1Api:
    _load_config()
    return client.CoreV1Api()


def _apps_v1() -> client.AppsV1Api:
    _load_config()
    return client.AppsV1Api()


# ---------------------------------------------------------------------------
# Tool: get_pod_status
# ---------------------------------------------------------------------------


def get_pod_status(namespace: str = "default") -> list[dict[str, Any]]:
    """Return the status of all pods in a namespace.

    Args:
        namespace: Kubernetes namespace to query.

    Returns:
        A list of dicts, each containing pod name, phase, conditions,
        container statuses, and restart counts.
    """
    v1 = _core_v1()
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
    except ApiException as exc:
        logger.error("Failed to list pods in %s: %s", namespace, exc)
        return [{"error": str(exc)}]

    results = []
    for pod in pods.items:
        containers = []
        for cs in pod.status.container_statuses or []:
            state_str = "unknown"
            if cs.state:
                if cs.state.running:
                    state_str = "running"
                elif cs.state.waiting:
                    state_str = "waiting"
                elif cs.state.terminated:
                    state_str = "terminated"
            containers.append(
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": state_str,
                }
            )

        results.append(
            {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "containers": containers,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Tool: describe_deployment
# ---------------------------------------------------------------------------


def describe_deployment(
    name: str, namespace: str = "default"
) -> dict[str, Any]:
    """Describe a deployment and its replica state.

    Args:
        name: Name of the Deployment.
        namespace: Kubernetes namespace.

    Returns:
        A dict with deployment metadata, replica counts, strategy,
        and conditions.
    """
    apps = _apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as exc:
        logger.error("Failed to describe deployment %s/%s: %s", namespace, name, exc)
        return {"error": str(exc)}

    conditions = []
    if dep.status and dep.status.conditions:
        for c in dep.status.conditions:
            conditions.append(
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                }
            )

    return {
        "name": dep.metadata.name,
        "namespace": dep.metadata.namespace,
        "replicas": {
            "desired": dep.spec.replicas,
            "ready": dep.status.ready_replicas or 0 if dep.status else 0,
            "available": dep.status.available_replicas or 0 if dep.status else 0,
            "unavailable": dep.status.unavailable_replicas or 0 if dep.status else 0,
        },
        "strategy": dep.spec.strategy.type if dep.spec.strategy else "Unknown",
        "conditions": conditions,
    }


# ---------------------------------------------------------------------------
# Tool: get_failing_pods
# ---------------------------------------------------------------------------


def get_failing_pods(namespace: str = "default") -> list[dict[str, Any]]:
    """List all pods NOT in Running or Completed state.

    Args:
        namespace: Kubernetes namespace to query.

    Returns:
        A list of dicts with pod name, phase, and reason for failure.
    """
    v1 = _core_v1()
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
    except ApiException as exc:
        logger.error("Failed to list pods in %s: %s", namespace, exc)
        return [{"error": str(exc)}]

    healthy_phases = {"Running", "Succeeded"}
    failing = []

    for pod in pods.items:
        is_failing = False
        reason = ""

        # Check pod phase
        if pod.status.phase not in healthy_phases:
            is_failing = True
            if pod.status.conditions:
                for cond in pod.status.conditions:
                    if cond.status != "True":
                        reason = f"{cond.type}: {cond.message or cond.reason or 'unknown'}"
                        break

        # Check container statuses for errors (e.g. CrashLoopBackOff, ImagePullBackOff, etc.)
        if not is_failing and pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                if cs.state and cs.state.waiting:
                    w = cs.state.waiting
                    if w.reason in {
                        "CrashLoopBackOff",
                        "ImagePullBackOff",
                        "ErrImagePull",
                        "CreateContainerConfigError",
                        "CreateContainerError",
                        "InvalidImageName",
                        "RunContainerError",
                    }:
                        is_failing = True
                        reason = f"Container {cs.name} in {w.reason}: {w.message or 'no message'}"
                        break
                elif cs.state and cs.state.terminated:
                    t = cs.state.terminated
                    if t.exit_code != 0:
                        is_failing = True
                        reason = f"Container {cs.name} terminated with exit code {t.exit_code}: {t.reason or 'unknown reason'}"
                        break

        if is_failing:
            failing.append(
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "phase": pod.status.phase,
                    "reason": reason,
                }
            )

    return failing


# ---------------------------------------------------------------------------
# Tool: get_node_pressure
# ---------------------------------------------------------------------------


def get_node_pressure() -> list[dict[str, Any]]:
    """Return node resource pressure conditions.

    Returns:
        A list of dicts per node showing memory, disk, and PID pressure
        conditions along with allocatable resources.
    """
    v1 = _core_v1()
    try:
        nodes = v1.list_node()
    except ApiException as exc:
        logger.error("Failed to list nodes: %s", exc)
        return [{"error": str(exc)}]

    pressure_types = {"MemoryPressure", "DiskPressure", "PIDPressure"}
    results = []

    for node in nodes.items:
        pressures = {}
        allocatable = {}
        if node.status:
            for cond in node.status.conditions or []:
                if cond.type in pressure_types:
                    pressures[cond.type] = {
                        "active": cond.status == "True",
                        "reason": cond.reason,
                        "message": cond.message,
                    }
            allocatable = node.status.allocatable or {}

        results.append(
            {
                "name": node.metadata.name,
                "pressures": pressures,
                "allocatable": {
                    "cpu": allocatable.get("cpu", "unknown") if allocatable else "unknown",
                    "memory": allocatable.get("memory", "unknown") if allocatable else "unknown",
                    "pods": allocatable.get("pods", "unknown") if allocatable else "unknown",
                },
            }
        )

    return results
