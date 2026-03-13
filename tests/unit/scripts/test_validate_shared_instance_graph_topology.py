from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "deploy"
    / "validate_shared_instance_graph_topology.py"
)


def _write_fake_gcloud(bin_dir: Path) -> None:
    fake_gcloud = bin_dir / "gcloud"
    fake_gcloud.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]

services = {
    "graph-service": {
        "metadata": {
            "annotations": {
                "run.googleapis.com/urls": "[\\"https://graph.example.com\\"]"
            }
        },
        "status": {"url": "https://graph.example.com"},
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "run.googleapis.com/cloudsql-instances": "project:region:shared-sql"
                    }
                },
                "spec": {
                    "containers": [{"env": []}]
                },
            }
        },
    },
    "api-service": {
        "metadata": {"annotations": {}},
        "status": {"url": "https://api.example.com"},
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "run.googleapis.com/cloudsql-instances": "project:region:shared-sql"
                    }
                },
                "spec": {
                    "containers": [{
                        "env": [
                            {"name": "GRAPH_SERVICE_URL", "value": "https://graph.example.com"}
                        ]
                    }]
                },
            }
        },
    },
    "admin-service": {
        "metadata": {"annotations": {}},
        "status": {"url": "https://admin.example.com"},
        "spec": {
            "template": {
                "metadata": {"annotations": {}},
                "spec": {
                    "containers": [{
                        "env": [
                            {"name": "GRAPH_API_BASE_URL", "value": "https://graph.example.com"},
                            {"name": "INTERNAL_GRAPH_API_URL", "value": "https://graph.example.com"},
                            {"name": "NEXT_PUBLIC_GRAPH_API_URL", "value": "https://graph.example.com"}
                        ]
                    }]
                },
            }
        },
    },
}

jobs = {
    "graph-migrate": {"metadata": {"name": "graph-migrate"}}
}

if args[:3] == ["run", "services", "describe"]:
    print(json.dumps(services[args[3]]))
    raise SystemExit(0)

if args[:3] == ["run", "jobs", "describe"]:
    print(json.dumps(jobs[args[3]]))
    raise SystemExit(0)

raise SystemExit(1)
""",
        encoding="utf-8",
    )
    fake_gcloud.chmod(fake_gcloud.stat().st_mode | stat.S_IEXEC)


def _base_env(bin_dir: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PROJECT_ID": "project",
        "REGION": "region",
        "GRAPH_SERVICE": "graph-service",
        "API_SERVICE": "api-service",
        "ADMIN_SERVICE": "admin-service",
        "GRAPH_SERVICE_URL": "https://graph.example.com",
        "GRAPH_PUBLIC_URL": "https://graph.example.com",
        "CLOUDSQL_CONNECTION_NAME": "project:region:shared-sql",
        "GRAPH_CLOUDSQL_CONNECTION_NAME": "project:region:shared-sql",
        "GRAPH_MIGRATION_JOB_NAME": "graph-migrate",
    }


def test_validate_shared_instance_graph_topology_succeeds(tmp_path: Path) -> None:
    _write_fake_gcloud(tmp_path)

    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=_base_env(tmp_path),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "shared_instance_graph_topology: ok" in result.stdout


def test_validate_shared_instance_graph_topology_rejects_url_mismatch(
    tmp_path: Path,
) -> None:
    _write_fake_gcloud(tmp_path)
    env = _base_env(tmp_path)
    env["GRAPH_SERVICE_URL"] = "https://wrong.example.com"

    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 1
    assert "GRAPH_SERVICE_URL does not match" in result.stderr
