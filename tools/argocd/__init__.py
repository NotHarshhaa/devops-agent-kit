"""ArgoCD tool bindings for DevOps agents.

Provides functions to query and manage ArgoCD applications via the
ArgoCD REST API.
"""

from .argocd_tool import (
    get_app_sync_status,
    list_out_of_sync_apps,
    get_app_diff,
    trigger_sync,
)

__all__ = [
    "get_app_sync_status",
    "list_out_of_sync_apps",
    "get_app_diff",
    "trigger_sync",
]
