"""Prometheus tool bindings for DevOps agents.

Provides functions to query Prometheus metrics and alerts via the
HTTP API.
"""

from .prom_tool import (
    query_metric,
    query_range,
    get_alerts_firing,
    get_error_rate,
)

__all__ = [
    "query_metric",
    "query_range",
    "get_alerts_firing",
    "get_error_rate",
]
