"""Prometheus tool bindings — PromQL query bindings for agents.

Each function acts as a named tool that an agent brain can invoke.
Functions communicate with the Prometheus HTTP API and return
structured dicts.

Requirements:
    - Prometheus server reachable (set PROMETHEUS_URL env var or
      defaults to http://localhost:9090)
    - `requests` Python package

Environment Variables:
    PROMETHEUS_URL — Prometheus server URL (default: http://localhost:9090)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")


def _query_api(
    endpoint: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Execute a query against the Prometheus HTTP API."""
    url = f"{PROMETHEUS_URL}/api/v1/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return {"error": data.get("error", "Unknown Prometheus error")}
        return data
    except requests.RequestException as exc:
        logger.error("Prometheus API error: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: query_metric
# ---------------------------------------------------------------------------


def query_metric(promql: str) -> dict[str, Any]:
    """Execute an instant PromQL query.

    Args:
        promql: A valid PromQL expression.

    Returns:
        A dict with query result type and the result data (vector,
        scalar, or string).
    """
    data = _query_api("query", {"query": promql, "time": time.time()})
    if "error" in data:
        return data

    result = data.get("data", {})
    return {
        "query": promql,
        "result_type": result.get("resultType", "unknown"),
        "results": result.get("result", []),
    }


# ---------------------------------------------------------------------------
# Tool: query_range
# ---------------------------------------------------------------------------


def query_range(
    promql: str,
    start: str | float | None = None,
    end: str | float | None = None,
    step: str = "60s",
) -> dict[str, Any]:
    """Execute a range PromQL query.

    Args:
        promql: A valid PromQL expression.
        start: Start timestamp (epoch or RFC3339). Defaults to 1 hour ago.
        end: End timestamp (epoch or RFC3339). Defaults to now.
        step: Query resolution step (e.g. '15s', '1m', '5m').

    Returns:
        A dict with result type, step used, and the matrix of values.
    """
    now = time.time()
    if start is None:
        start = now - 3600  # 1 hour ago
    if end is None:
        end = now

    params = {
        "query": promql,
        "start": start,
        "end": end,
        "step": step,
    }

    data = _query_api("query_range", params)
    if "error" in data:
        return data

    result = data.get("data", {})
    return {
        "query": promql,
        "result_type": result.get("resultType", "unknown"),
        "step": step,
        "results": result.get("result", []),
    }


# ---------------------------------------------------------------------------
# Tool: get_alerts_firing
# ---------------------------------------------------------------------------


def get_alerts_firing() -> list[dict[str, Any]]:
    """Return all currently firing Prometheus alerts.

    Returns:
        A list of dicts, each containing alert name, state, labels,
        annotations, and active-since timestamp.
    """
    data = _query_api("alerts", {})
    if "error" in data:
        return [data]

    alerts = data.get("data", {}).get("alerts", [])
    firing = []

    for alert in alerts:
        if alert.get("state") == "firing":
            firing.append(
                {
                    "name": alert.get("labels", {}).get("alertname", "unknown"),
                    "state": alert.get("state"),
                    "severity": alert.get("labels", {}).get("severity", ""),
                    "labels": alert.get("labels", {}),
                    "annotations": alert.get("annotations", {}),
                    "active_at": alert.get("activeAt", ""),
                }
            )

    return firing


# ---------------------------------------------------------------------------
# Tool: get_error_rate
# ---------------------------------------------------------------------------


def get_error_rate(
    service: str,
    namespace: str = "default",
    window: str = "5m",
) -> dict[str, Any]:
    """Return the HTTP error rate for a service.

    Calculates the ratio of 5xx responses to total responses over
    the specified time window using standard Prometheus HTTP metrics.

    Args:
        service: Name of the service (matches the `job` label).
        namespace: Kubernetes namespace (matches the `namespace` label).
        window: Time window for rate calculation (e.g. '5m', '15m').

    Returns:
        A dict with service name, error rate percentage, and the
        raw PromQL query used.
    """
    promql = (
        f'sum(rate(http_requests_total{{job="{service}",'
        f'namespace="{namespace}",code=~"5.."}}[{window}]))'
        f" / "
        f'sum(rate(http_requests_total{{job="{service}",'
        f'namespace="{namespace}"}}[{window}]))'
        f" * 100"
    )

    data = _query_api("query", {"query": promql, "time": time.time()})
    if "error" in data:
        return data

    results = data.get("data", {}).get("result", [])
    error_rate = 0.0
    if results:
        try:
            error_rate = float(results[0].get("value", [0, "0"])[1])
        except (IndexError, ValueError, TypeError):
            error_rate = 0.0

    return {
        "service": service,
        "namespace": namespace,
        "window": window,
        "error_rate_percent": round(error_rate, 4),
        "query": promql,
    }
