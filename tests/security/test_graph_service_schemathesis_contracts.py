from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from schemathesis import openapi
from schemathesis.core.transport import Response
from schemathesis.specs.openapi.checks import ignored_auth

from services.graph_api.app import create_app
from tests.graph_service_support import (
    build_graph_admin_headers,
    reset_graph_service_database,
)

if TYPE_CHECKING:
    from schemathesis.schemas import APIOperation


schema = openapi.from_asgi("/openapi.json", create_app())


def _get_operation(path: str, method: str) -> APIOperation:
    for result in schema.get_all_operations():
        operation = result._value
        if operation.path == path and operation.method.upper() == method.upper():
            return operation
    message = f"Operation {method} {path} not found in graph-service OpenAPI schema"
    raise AssertionError(message)


HEALTH_OPERATION = _get_operation("/health", "GET")
ADMIN_SPACE_LIST_OPERATION = _get_operation("/v1/admin/spaces", "GET")


def test_graph_service_health_contract() -> None:
    case = schema.make_case(
        operation=HEALTH_OPERATION,
        method=HEALTH_OPERATION.method,
        path=HEALTH_OPERATION.path,
    )
    with TestClient(create_app()) as client:
        response = client.get("/health")
        try:
            case.validate_response(
                Response.from_httpx(response, verify=False),
                excluded_checks=[ignored_auth],
            )
        finally:
            response.close()


def test_graph_service_admin_space_list_contract() -> None:
    reset_graph_service_database()
    try:
        case = schema.make_case(
            operation=ADMIN_SPACE_LIST_OPERATION,
            method=ADMIN_SPACE_LIST_OPERATION.method,
            path=ADMIN_SPACE_LIST_OPERATION.path,
        )
        with TestClient(create_app()) as client:
            response = client.get(
                "/v1/admin/spaces",
                headers=build_graph_admin_headers(),
            )
            try:
                case.validate_response(
                    Response.from_httpx(response, verify=False),
                    excluded_checks=[ignored_auth],
                )
            finally:
                response.close()
    finally:
        reset_graph_service_database()
