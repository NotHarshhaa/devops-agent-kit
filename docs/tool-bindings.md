# Tool Bindings Reference

Tool bindings are the interface between agent brains and your infrastructure. Each binding exposes a set of named functions that agents can discover and call.

## Design Principles

1. **Named functions with docstrings** — every tool has a clear description of its inputs, outputs, and behavior so agent brains can reason about when to use it
2. **Structured dict returns** — tools return Python dicts, not raw strings, so agents can programmatically inspect results
3. **Graceful error handling** — on failure, tools return `{"error": "..."}` instead of raising exceptions
4. **Environment-based config** — connection details (URLs, tokens) are read from environment variables

## Environment Variables

| Variable | Default | Used By |
|----------|---------|---------|
| `ARGOCD_SERVER` | `https://localhost:8080` | ArgoCD tools |
| `ARGOCD_AUTH_TOKEN` | (empty) | ArgoCD tools |
| `ARGOCD_INSECURE` | `false` | ArgoCD tools |
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus tools |

Kubernetes tools use the standard kubeconfig or in-cluster service account — no additional environment variables needed.

---

## Kubernetes Tools (`tools/kubernetes/k8s_tool.py`)

Requires: `kubernetes` Python package, valid kubeconfig or in-cluster config.

### `get_pod_status(namespace="default")`

Returns the status of all pods in a namespace.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `namespace` | `str` | `"default"` | Kubernetes namespace to query |

**Returns:** `list[dict]` — each dict contains:
```python
{
    "name": "pod-name",
    "namespace": "default",
    "phase": "Running",
    "containers": [
        {
            "name": "container-name",
            "ready": True,
            "restart_count": 0,
            "state": "running"
        }
    ]
}
```

---

### `describe_deployment(name, namespace="default")`

Describes a deployment and its replica state.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `name` | `str` | (required) | Name of the Deployment |
| `namespace` | `str` | `"default"` | Kubernetes namespace |

**Returns:** `dict` with:
```python
{
    "name": "deployment-name",
    "namespace": "default",
    "replicas": {
        "desired": 3,
        "ready": 3,
        "available": 3,
        "unavailable": 0
    },
    "strategy": "RollingUpdate",
    "conditions": [...]
}
```

---

### `get_failing_pods(namespace="default")`

Lists all pods NOT in Running or Completed state.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `namespace` | `str` | `"default"` | Kubernetes namespace to query |

**Returns:** `list[dict]` — each dict contains:
```python
{
    "name": "pod-name",
    "namespace": "default",
    "phase": "CrashLoopBackOff",
    "reason": "ContainersNotReady: ..."
}
```

---

### `get_node_pressure()`

Returns node resource pressure conditions.

**Parameters:** None

**Returns:** `list[dict]` — each dict contains:
```python
{
    "name": "node-1",
    "pressures": {
        "MemoryPressure": {"active": False, "reason": "...", "message": "..."},
        "DiskPressure": {"active": False, "reason": "...", "message": "..."},
        "PIDPressure": {"active": False, "reason": "...", "message": "..."}
    },
    "allocatable": {"cpu": "4", "memory": "16Gi", "pods": "110"}
}
```

---

## ArgoCD Tools (`tools/argocd/argocd_tool.py`)

Requires: `requests` Python package, ArgoCD server accessible, auth token set.

### `get_app_sync_status(app_name)`

Returns sync and health status of an ArgoCD application.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `app_name` | `str` | (required) | Name of the ArgoCD application |

**Returns:** `dict` with:
```python
{
    "name": "my-app",
    "sync_status": "Synced",
    "health_status": "Healthy",
    "revision": "abc123",
    "source": {"repo_url": "...", "path": "...", "target_revision": "main"},
    "operated_at": "2024-01-01T00:00:00Z"
}
```

---

### `list_out_of_sync_apps()`

Lists all ArgoCD applications with OutOfSync status.

**Parameters:** None

**Returns:** `list[dict]` — each dict contains:
```python
{
    "name": "my-app",
    "sync_status": "OutOfSync",
    "health_status": "Healthy"
}
```

---

### `get_app_diff(app_name)`

Returns the live vs desired diff for an ArgoCD application.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `app_name` | `str` | (required) | Name of the ArgoCD application |

**Returns:** `dict` with:
```python
{
    "app_name": "my-app",
    "resources": [...],
    "total_resources": 5,
    "out_of_sync": 2
}
```

---

### `trigger_sync(app_name, prune=False, dry_run=False)`

Triggers a sync for a specific ArgoCD application.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `app_name` | `str` | (required) | Name of the application to sync |
| `prune` | `bool` | `False` | Prune resources no longer in Git |
| `dry_run` | `bool` | `False` | Perform a dry-run sync |

**Returns:** `dict` with:
```python
{
    "app_name": "my-app",
    "action": "sync",
    "status": "triggered",
    "message": "Sync triggered for 'my-app'"
}
```

> ⚠️ **This is the only mutating tool.** All other tools are read-only.

---

## Prometheus Tools (`tools/prometheus/prom_tool.py`)

Requires: `requests` Python package, Prometheus server accessible.

### `query_metric(promql)`

Executes an instant PromQL query.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `promql` | `str` | (required) | A valid PromQL expression |

**Returns:** `dict` with:
```python
{
    "query": "up",
    "result_type": "vector",
    "results": [...]
}
```

---

### `query_range(promql, start=None, end=None, step="60s")`

Executes a range PromQL query.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `promql` | `str` | (required) | A valid PromQL expression |
| `start` | `float\|str` | 1 hour ago | Start timestamp |
| `end` | `float\|str` | now | End timestamp |
| `step` | `str` | `"60s"` | Query resolution step |

**Returns:** `dict` with:
```python
{
    "query": "rate(http_requests_total[5m])",
    "result_type": "matrix",
    "step": "60s",
    "results": [...]
}
```

---

### `get_alerts_firing()`

Returns all currently firing Prometheus alerts.

**Parameters:** None

**Returns:** `list[dict]` — each dict contains:
```python
{
    "name": "HighErrorRate",
    "state": "firing",
    "severity": "critical",
    "labels": {...},
    "annotations": {...},
    "active_at": "2024-01-01T00:00:00Z"
}
```

---

### `get_error_rate(service, namespace="default", window="5m")`

Returns the HTTP error rate for a service.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `service` | `str` | (required) | Service name (matches `job` label) |
| `namespace` | `str` | `"default"` | Kubernetes namespace |
| `window` | `str` | `"5m"` | Time window for rate calculation |

**Returns:** `dict` with:
```python
{
    "service": "api-server",
    "namespace": "production",
    "window": "5m",
    "error_rate_percent": 0.42,
    "query": "..."
}
```

---

## Adding New Tool Bindings

To add a new tool binding:

1. Create a directory under `tools/` (e.g., `tools/newservice/`)
2. Create the tool module (`newservice_tool.py`) with named functions
3. Create `__init__.py` that exports all tool functions
4. Each function should:
   - Have a clear docstring describing inputs and outputs
   - Return a dict (not raw strings)
   - Handle errors gracefully with `{"error": "..."}`
   - Use environment variables for configuration
5. Register the tools in the agent that should use them (in `agents/`)
6. Update `tools/requirements.txt` if new dependencies are needed
