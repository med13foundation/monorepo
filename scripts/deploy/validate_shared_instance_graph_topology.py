#!/usr/bin/env python3
"""Validate shared-instance graph topology wiring in deployed Cloud Run services."""

from __future__ import annotations

import json
import os
import subprocess
import sys

JSONMap = dict[str, object]
PathSegment = str | int


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        message = f"Missing required env var: {name}"
        raise RuntimeError(message)
    return value


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def _run_gcloud_json(*args: str) -> JSONMap:
    command = [
        "gcloud",
        *args,
        "--project",
        _require_env("PROJECT_ID"),
        "--region",
        _require_env("REGION"),
        "--format=json",
    ]
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = f"gcloud command failed: {' '.join(command)}\n{result.stderr.strip()}"
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        message = f"gcloud returned invalid JSON for {' '.join(command)}"
        raise RuntimeError(message) from exc
    if not isinstance(payload, dict):
        message = f"gcloud returned non-object JSON for {' '.join(command)}"
        raise TypeError(message)
    return payload


def _describe_service(service_name: str) -> JSONMap:
    return _run_gcloud_json("run", "services", "describe", service_name)


def _describe_job(job_name: str) -> JSONMap:
    return _run_gcloud_json("run", "jobs", "describe", job_name)


def _path_get(data: JSONMap, *path: PathSegment) -> object | None:
    current: object = data
    for segment in path:
        if isinstance(segment, int):
            if not isinstance(current, list) or len(current) <= segment:
                return None
            current = current[segment]
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None
    return current


def _collect_service_urls(service_snapshot: JSONMap) -> set[str]:
    urls: set[str] = set()
    status_url = _path_get(service_snapshot, "status", "url")
    if isinstance(status_url, str) and status_url.strip():
        urls.add(_normalize_url(status_url))

    raw_urls = _path_get(
        service_snapshot,
        "metadata",
        "annotations",
        "run.googleapis.com/urls",
    )
    if isinstance(raw_urls, str) and raw_urls.strip():
        try:
            parsed_urls = json.loads(raw_urls)
        except json.JSONDecodeError:
            parsed_urls = [raw_urls]
        if isinstance(parsed_urls, list):
            for url in parsed_urls:
                if isinstance(url, str) and url.strip():
                    urls.add(_normalize_url(url))
    return urls


def _collect_service_env(service_snapshot: JSONMap) -> dict[str, str]:
    env_entries = (
        _path_get(service_snapshot, "spec", "template", "spec", "containers", 0, "env")
        or _path_get(service_snapshot, "template", "containers", 0, "env")
        or []
    )
    env_map: dict[str, str] = {}
    if not isinstance(env_entries, list):
        return env_map
    for entry in env_entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if isinstance(name, str) and isinstance(value, str):
            env_map[name] = value
    return env_map


def _cloudsql_instance(service_snapshot: JSONMap) -> str:
    annotation = _path_get(
        service_snapshot,
        "spec",
        "template",
        "metadata",
        "annotations",
        "run.googleapis.com/cloudsql-instances",
    )
    if isinstance(annotation, str):
        return annotation.strip()
    return ""


def _validate() -> None:
    graph_service = _require_env("GRAPH_SERVICE")
    api_service = _require_env("API_SERVICE")
    admin_service = _require_env("ADMIN_SERVICE")
    graph_service_url = _normalize_url(_require_env("GRAPH_SERVICE_URL"))
    graph_public_url = _normalize_url(
        os.getenv("GRAPH_PUBLIC_URL", graph_service_url).strip() or graph_service_url,
    )

    shared_cloudsql = os.getenv("CLOUDSQL_CONNECTION_NAME", "").strip()
    graph_cloudsql = os.getenv("GRAPH_CLOUDSQL_CONNECTION_NAME", "").strip()
    if shared_cloudsql and graph_cloudsql and shared_cloudsql != graph_cloudsql:
        message = (
            "Shared-instance validation requires CLOUDSQL_CONNECTION_NAME and "
            "GRAPH_CLOUDSQL_CONNECTION_NAME to match"
        )
        raise RuntimeError(message)

    graph_snapshot = _describe_service(graph_service)
    api_snapshot = _describe_service(api_service)
    admin_snapshot = _describe_service(admin_service)

    actual_graph_urls = _collect_service_urls(graph_snapshot)
    if graph_service_url not in actual_graph_urls:
        message = "GRAPH_SERVICE_URL does not match the deployed graph service URL set"
        raise RuntimeError(message)
    if graph_public_url not in actual_graph_urls:
        message = "GRAPH_PUBLIC_URL does not match the deployed graph service URL set"
        raise RuntimeError(message)

    api_env = _collect_service_env(api_snapshot)
    configured_backend_graph_url = _normalize_url(api_env.get("GRAPH_SERVICE_URL", ""))
    if configured_backend_graph_url != graph_service_url:
        message = (
            "API service GRAPH_SERVICE_URL does not match the expected "
            "graph-service URL"
        )
        raise RuntimeError(message)

    admin_env = _collect_service_env(admin_snapshot)
    expected_admin_url = graph_public_url
    for env_name in (
        "GRAPH_API_BASE_URL",
        "INTERNAL_GRAPH_API_URL",
        "NEXT_PUBLIC_GRAPH_API_URL",
    ):
        configured_value = _normalize_url(admin_env.get(env_name, ""))
        if configured_value != expected_admin_url:
            message = (
                f"Admin service {env_name} does not match the expected "
                "graph public URL"
            )
            raise RuntimeError(message)

    deployed_graph_cloudsql = _cloudsql_instance(graph_snapshot)
    deployed_api_cloudsql = _cloudsql_instance(api_snapshot)
    if graph_cloudsql and deployed_graph_cloudsql != graph_cloudsql:
        message = (
            "Graph service Cloud SQL annotation does not match "
            "GRAPH_CLOUDSQL_CONNECTION_NAME"
        )
        raise RuntimeError(message)
    if shared_cloudsql and deployed_api_cloudsql != shared_cloudsql:
        message = (
            "API service Cloud SQL annotation does not match "
            "CLOUDSQL_CONNECTION_NAME"
        )
        raise RuntimeError(message)
    if (
        deployed_graph_cloudsql
        and deployed_api_cloudsql
        and deployed_graph_cloudsql != deployed_api_cloudsql
    ):
        message = (
            "Graph and platform API services are not pointed at the same shared "
            "Cloud SQL instance"
        )
        raise RuntimeError(message)

    migration_job_name = os.getenv("GRAPH_MIGRATION_JOB_NAME", "").strip()
    if migration_job_name:
        _describe_job(migration_job_name)

    print("shared_instance_graph_topology: ok")


def main() -> int:
    try:
        _validate()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
