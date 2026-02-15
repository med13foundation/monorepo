from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.application.curation.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from src.application.services.audit_service import AuditTrailService
from src.database.session import SessionLocal, set_session_rls_context
from src.domain.entities.user import User
from src.infrastructure.observability.request_context import get_audit_context

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from fastapi import Request, Response
    from starlette.types import ASGIApp

    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDED_PREFIXES: Final[tuple[str, ...]] = (
    "/auth",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/resources",
)

READ_METHODS: Final[frozenset[str]] = frozenset({"GET"})
MUTATION_ACTIONS: Final[dict[str, str]] = {
    "POST": "phi.create",
    "PUT": "phi.update",
    "PATCH": "phi.update",
    "DELETE": "phi.delete",
}

HTTP_ERROR_THRESHOLD: Final[int] = 400


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log read access for HIPAA-aligned audit trails."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        exclude_prefixes: tuple[str, ...] = DEFAULT_EXCLUDED_PREFIXES,
    ) -> None:
        super().__init__(app)
        self._exclude_prefixes = exclude_prefixes
        self._audit_service = AuditTrailService(SqlAlchemyAuditRepository())

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)

        if not self._should_audit(request):
            return response

        action = self._resolve_action(request.method)
        if action is None:
            return response

        context = get_audit_context(request)
        actor_id = _resolve_actor_id(request)
        details: JSONObject = {"status_code": response.status_code}
        success = response.status_code < HTTP_ERROR_THRESHOLD

        db = SessionLocal()
        set_session_rls_context(db, bypass_rls=True)
        try:
            self._audit_service.record_action(
                db,
                action=action,
                target=("http_request", request.url.path),
                actor_id=actor_id,
                details=details,
                context=context,
                success=success,
            )
        except (
            Exception
        ):  # pragma: no cover - audit logging should never break requests
            logger.exception(
                "Failed to record audit log for %s %s",
                request.method,
                request.url.path,
            )
        finally:
            db.close()

        return response

    def _should_audit(self, request: Request) -> bool:
        method = request.method.upper()
        if method not in READ_METHODS and method not in MUTATION_ACTIONS:
            return False
        path = request.url.path
        return not any(path.startswith(prefix) for prefix in self._exclude_prefixes)

    @staticmethod
    def _resolve_action(method: str) -> str | None:
        normalized_method = method.upper()
        if normalized_method in READ_METHODS:
            return "phi.read"
        return MUTATION_ACTIONS.get(normalized_method)


def _resolve_actor_id(request: Request) -> str | None:
    state_user = getattr(request.state, "user", None)
    if isinstance(state_user, User):
        return str(state_user.id)
    return None


__all__ = ["AuditLoggingMiddleware"]
