from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from src.middleware.audit_logging import AuditLoggingMiddleware
from src.middleware.request_context import RequestContextMiddleware

if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest


def _build_test_app(
    *,
    stream_release: threading.Event | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(AuditLoggingMiddleware)

    @app.get("/tracked")
    def tracked(request: Request) -> dict[str, object]:
        audit_context = getattr(request.state, "audit_context", {})
        request_id = getattr(request.state, "request_id", None)
        return {
            "request_id": request_id,
            "audit_request_id": (
                audit_context.get("request_id")
                if isinstance(audit_context, dict)
                else None
            ),
        }

    @app.get("/stream")
    def stream() -> StreamingResponse:
        def _generate() -> Generator[bytes]:
            if stream_release is not None:
                stream_release.wait(timeout=1)
            yield b"stream-chunk"

        return StreamingResponse(_generate(), media_type="text/plain")

    return app


def test_request_context_middleware_sets_request_id_header_and_state() -> None:
    app = _build_test_app()
    client = TestClient(app)

    response = client.get("/tracked", headers={"X-Request-ID": "request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-123"
    assert response.json() == {
        "request_id": "request-123",
        "audit_request_id": "request-123",
    }


def test_audit_logging_middleware_records_status_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_test_app()
    recorded: list[dict[str, object]] = []

    def _capture_record_action(
        self: AuditLoggingMiddleware,
        *,
        action: str,
        path: str,
        actor_id: str | None,
        details: dict[str, object],
        context: dict[str, object],
        success: bool,
    ) -> None:
        recorded.append(
            {
                "action": action,
                "path": path,
                "actor_id": actor_id,
                "details": details,
                "context": context,
                "success": success,
            },
        )

    monkeypatch.setattr(
        AuditLoggingMiddleware,
        "_record_action",
        _capture_record_action,
    )
    client = TestClient(app)

    response = client.get("/tracked", headers={"X-Request-ID": "request-456"})

    assert response.status_code == 200
    assert recorded == [
        {
            "action": "phi.read",
            "path": "/tracked",
            "actor_id": None,
            "details": {"status_code": 200},
            "context": {
                "request_id": "request-456",
                "ip_address": "testclient",
                "user_agent": "testclient",
                "method": "GET",
                "path": "/tracked",
            },
            "success": True,
        },
    ]


def test_audit_logging_middleware_failure_does_not_break_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _build_test_app()

    def _raise_record_action(
        self: AuditLoggingMiddleware,
        *,
        action: str,
        path: str,
        actor_id: str | None,
        details: dict[str, object],
        context: dict[str, object],
        success: bool,
    ) -> None:
        msg = "audit write failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        AuditLoggingMiddleware,
        "_record_action",
        _raise_record_action,
    )
    client = TestClient(app)

    with caplog.at_level(logging.ERROR):
        response = client.get("/tracked")

    assert response.status_code == 200
    assert "Failed to record audit log for GET /tracked" in caplog.text


def test_audit_logging_records_stream_on_response_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_release = threading.Event()
    app = _build_test_app(stream_release=stream_release)
    recorded: list[dict[str, object]] = []

    def _capture_record_action(
        self: AuditLoggingMiddleware,
        *,
        action: str,
        path: str,
        actor_id: str | None,
        details: dict[str, object],
        context: dict[str, object],
        success: bool,
    ) -> None:
        recorded.append(
            {
                "action": action,
                "path": path,
                "actor_id": actor_id,
                "details": details,
                "context": context,
                "success": success,
            },
        )

    monkeypatch.setattr(
        AuditLoggingMiddleware,
        "_record_action",
        _capture_record_action,
    )
    client = TestClient(app)

    with client.stream(
        "GET",
        "/stream",
        headers={"X-Request-ID": "request-stream"},
    ) as response:
        try:
            assert response.status_code == 200
            assert recorded == [
                {
                    "action": "phi.read",
                    "path": "/stream",
                    "actor_id": None,
                    "details": {"status_code": 200},
                    "context": {
                        "request_id": "request-stream",
                        "ip_address": "testclient",
                        "user_agent": "testclient",
                        "method": "GET",
                        "path": "/stream",
                    },
                    "success": True,
                },
            ]
            stream_release.set()
            assert b"".join(response.iter_bytes()) == b"stream-chunk"
            assert len(recorded) == 1
        finally:
            stream_release.set()


def test_audit_logging_records_stream_when_client_does_not_consume_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_release = threading.Event()
    app = _build_test_app(stream_release=stream_release)
    recorded: list[dict[str, object]] = []

    def _capture_record_action(
        self: AuditLoggingMiddleware,
        *,
        action: str,
        path: str,
        actor_id: str | None,
        details: dict[str, object],
        context: dict[str, object],
        success: bool,
    ) -> None:
        recorded.append(
            {
                "action": action,
                "path": path,
                "actor_id": actor_id,
                "details": details,
                "context": context,
                "success": success,
            },
        )

    monkeypatch.setattr(
        AuditLoggingMiddleware,
        "_record_action",
        _capture_record_action,
    )
    client = TestClient(app)

    try:
        with client.stream(
            "GET",
            "/stream",
            headers={"X-Request-ID": "request-stream-abort"},
        ) as response:
            assert response.status_code == 200
            assert recorded == [
                {
                    "action": "phi.read",
                    "path": "/stream",
                    "actor_id": None,
                    "details": {"status_code": 200},
                    "context": {
                        "request_id": "request-stream-abort",
                        "ip_address": "testclient",
                        "user_agent": "testclient",
                        "method": "GET",
                        "path": "/stream",
                    },
                    "success": True,
                },
            ]
            stream_release.set()
    finally:
        stream_release.set()


def test_audit_logging_records_stream_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_release = threading.Event()
    app = _build_test_app(stream_release=stream_release)
    recorded: list[dict[str, object]] = []

    def _capture_record_action(
        self: AuditLoggingMiddleware,
        *,
        action: str,
        path: str,
        actor_id: str | None,
        details: dict[str, object],
        context: dict[str, object],
        success: bool,
    ) -> None:
        recorded.append(
            {
                "action": action,
                "path": path,
                "actor_id": actor_id,
                "details": details,
                "context": context,
                "success": success,
            },
        )

    monkeypatch.setattr(
        AuditLoggingMiddleware,
        "_record_action",
        _capture_record_action,
    )
    client = TestClient(app)

    try:
        with client.stream(
            "GET",
            "/stream",
            headers={"X-Request-ID": "request-stream-once"},
        ) as response:
            assert response.status_code == 200
            stream_release.set()
            assert b"".join(response.iter_bytes()) == b"stream-chunk"
    finally:
        stream_release.set()

    assert len(recorded) == 1
