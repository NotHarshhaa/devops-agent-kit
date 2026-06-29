"""ArgoCD tool bindings — sync/status bindings for agents.

Each function acts as a named tool that an agent brain can invoke.
Functions communicate with the ArgoCD REST API and return structured
dicts.

Requirements:
    - ArgoCD server reachable (set ARGOCD_SERVER env var or defaults
      to localhost:8080)
    - Valid auth token (set ARGOCD_AUTH_TOKEN env var)
    - `requests` Python package

Environment Variables:
    ARGOCD_SERVER     — ArgoCD server URL (default: https://localhost:8080)
    ARGOCD_AUTH_TOKEN — Bearer token for authentication
    ARGOCD_INSECURE   — Set to "true" to skip TLS verification
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
import urllib3

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ARGOCD_SERVER = os.getenv("ARGOCD_SERVER", "https://localhost:8080").rstrip("/")
ARGOCD_TOKEN = os.getenv("ARGOCD_AUTH_TOKEN", "")
ARGOCD_INSECURE = os.getenv("ARGOCD_INSECURE", "false").lower() == "true"

if ARGOCD_INSECURE:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _headers() -> dict[str, str]:
    """Build request headers with auth token."""
    h = {"Content-Type": "application/json"}
    if ARGOCD_TOKEN:
        h["Authorization"] = f"Bearer {ARGOCD_TOKEN}"
    return h


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    """Make a GET request to the ArgoCD API."""
    url = f"{ARGOCD_SERVER}/api/v1/{path}"
    try:
        resp = requests.get(
            url,
            headers=_headers(),
            params=params,
            verify=not ARGOCD_INSECURE,
            timeout=10,
        )
        try:
            data = resp.json()
            if isinstance(data, dict) and "message" in data and resp.status_code >= 400:
                return {"error": data["message"]}
        except ValueError:
            pass

        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("ArgoCD API error: %s", exc)
        if 'resp' in locals() and resp.text:
            return {"error": f"{exc} - Response: {resp.text}"}
        return {"error": str(exc)}


def _post(path: str, json_body: dict | None = None) -> dict[str, Any]:
    """Make a POST request to the ArgoCD API."""
    url = f"{ARGOCD_SERVER}/api/v1/{path}"
    try:
        resp = requests.post(
            url,
            headers=_headers(),
            json=json_body or {},
            verify=not ARGOCD_INSECURE,
            timeout=30,
        )
        try:
            data = resp.json()
            if isinstance(data, dict) and "message" in data and resp.status_code >= 400:
                return {"error": data["message"]}
        except ValueError:
            pass

        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("ArgoCD API error: %s", exc)
        if 'resp' in locals() and resp.text:
            return {"error": f"{exc} - Response: {resp.text}"}
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: get_app_sync_status
# ---------------------------------------------------------------------------


def get_app_sync_status(app_name: str) -> dict[str, Any]:
    """Return sync and health status of an ArgoCD application.

    Args:
        app_name: Name of the ArgoCD application.

    Returns:
        A dict with sync status, health status, source repo, revision,
        and last sync time.
    """
    data = _get(f"applications/{app_name}")
    if "error" in data:
        return data

    status = data.get("status", {})
    sync = status.get("sync", {})
    health = status.get("health", {})

    return {
        "name": app_name,
        "sync_status": sync.get("status", "Unknown"),
        "health_status": health.get("status", "Unknown"),
        "revision": sync.get("revision", ""),
        "source": {
            "repo_url": data.get("spec", {}).get("source", {}).get("repoURL", ""),
            "path": data.get("spec", {}).get("source", {}).get("path", ""),
            "target_revision": data.get("spec", {})
            .get("source", {})
            .get("targetRevision", ""),
        },
        "operated_at": status.get("operationState", {})
        .get("finishedAt", "N/A"),
    }


# ---------------------------------------------------------------------------
# Tool: list_out_of_sync_apps
# ---------------------------------------------------------------------------


def list_out_of_sync_apps() -> list[dict[str, str]]:
    """List all ArgoCD applications with OutOfSync status.

    Returns:
        A list of dicts with app name, sync status, and health status.
    """
    data = _get("applications")
    if "error" in data:
        return [data]

    out_of_sync = []
    for item in data.get("items", []):
        sync_status = (
            item.get("status", {}).get("sync", {}).get("status", "Unknown")
        )
        if sync_status == "OutOfSync":
            health_status = (
                item.get("status", {}).get("health", {}).get("status", "Unknown")
            )
            out_of_sync.append(
                {
                    "name": item.get("metadata", {}).get("name", ""),
                    "sync_status": sync_status,
                    "health_status": health_status,
                }
            )

    return out_of_sync


# ---------------------------------------------------------------------------
# Tool: get_app_diff
# ---------------------------------------------------------------------------


def get_app_diff(app_name: str) -> dict[str, Any]:
    """Return the live vs desired diff for an ArgoCD application.

    Args:
        app_name: Name of the ArgoCD application.

    Returns:
        A dict containing managed resources and their diff status.
    """
    data = _get(f"applications/{app_name}/managed-resources")
    if "error" in data:
        return data

    diffs = []
    for resource in data.get("items", []):
        diff_info = {
            "kind": resource.get("kind", ""),
            "name": resource.get("name", ""),
            "namespace": resource.get("namespace", ""),
            "status": resource.get("status", "Unknown"),
            "health": resource.get("health", {}).get("status", "Unknown")
            if resource.get("health")
            else "Unknown",
        }

        # Include diff detail if resource has a diff
        if resource.get("diff"):
            diff_info["has_diff"] = True
            diff_info["diff_summary"] = resource.get("diff", "")

        diffs.append(diff_info)

    return {
        "app_name": app_name,
        "resources": diffs,
        "total_resources": len(diffs),
        "out_of_sync": sum(
            1 for d in diffs if d.get("status") == "OutOfSync"
        ),
    }


# ---------------------------------------------------------------------------
# Tool: trigger_sync
# ---------------------------------------------------------------------------


def trigger_sync(
    app_name: str, prune: bool = False, dry_run: bool = False
) -> dict[str, Any]:
    """Trigger a sync for a specific ArgoCD application.

    Args:
        app_name: Name of the ArgoCD application to sync.
        prune: If True, prune resources that are no longer in Git.
        dry_run: If True, perform a dry-run sync.

    Returns:
        A dict with sync operation result.
    """
    if dry_run:
        return {
            "app_name": app_name,
            "action": "sync",
            "dry_run": True,
            "message": f"Would sync application '{app_name}' (prune={prune})",
        }

    body = {
        "name": app_name,
        "prune": prune,
        "dryRun": False,
        "strategy": {"hook": {}},
    }

    data = _post(f"applications/{app_name}/sync", json_body=body)
    if "error" in data:
        return data

    return {
        "app_name": app_name,
        "action": "sync",
        "status": "triggered",
        "message": f"Sync triggered for '{app_name}'",
    }
