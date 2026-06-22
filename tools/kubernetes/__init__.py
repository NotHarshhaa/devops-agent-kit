"""Kubernetes tool bindings for DevOps agents.

Provides functions to query Kubernetes cluster state via the official
Python client. Each function is a named tool that agent brains can
discover and call.
"""

from .k8s_tool import (
    get_pod_status,
    describe_deployment,
    get_failing_pods,
    get_node_pressure,
)

__all__ = [
    "get_pod_status",
    "describe_deployment",
    "get_failing_pods",
    "get_node_pressure",
]
