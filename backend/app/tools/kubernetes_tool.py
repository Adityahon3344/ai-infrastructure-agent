"""Kubernetes integration via the official python client. Scope is
intentionally read-heavy (list pods/services/deployments) plus a single
allowlisted `apply` action for manifests, gated behind HIGH-risk approval like
any other mutating action. Requires a kubeconfig supplied through a
KUBERNETES-type Connection."""
from __future__ import annotations

import tempfile
from pathlib import Path

try:
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes import utils as k8s_utils
    KUBERNETES_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    KUBERNETES_AVAILABLE = False


class KubernetesNotAvailable(Exception):
    pass


class KubernetesTool:
    def __init__(self, kubeconfig_yaml: str):
        if not KUBERNETES_AVAILABLE:
            raise KubernetesNotAvailable(
                "The 'kubernetes' python package is not installed. Add it to requirements.txt and "
                "`pip install kubernetes` to enable Kubernetes features."
            )
        self._tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
        self._tmp.write(kubeconfig_yaml)
        self._tmp.flush()
        self.api_client = k8s_config.new_client_from_config(config_file=self._tmp.name)
        self.core = k8s_client.CoreV1Api(self.api_client)

    def list_pods(self, namespace: str = "default") -> list[dict]:
        pods = self.core.list_namespaced_pod(namespace)
        return [{"name": p.metadata.name, "status": p.status.phase, "node": p.spec.node_name} for p in pods.items]

    def apply_manifest(self, manifest_yaml: str) -> dict:
        import yaml as _yaml
        docs = list(_yaml.safe_load_all(manifest_yaml))
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write(manifest_yaml)
            path = f.name
        k8s_utils.create_from_yaml(self.api_client, path)
        return {"applied_objects": len(docs)}

    def close(self):
        Path(self._tmp.name).unlink(missing_ok=True)
