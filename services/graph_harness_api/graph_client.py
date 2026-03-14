"""Typed graph API access for the standalone harness service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.user import UserRole
from src.infrastructure.graph_service.client import (
    GraphServiceClient,
    GraphServiceClientConfig,
    GraphServiceHealthResponse,
)
from src.infrastructure.graph_service.runtime import (
    build_graph_service_bearer_token_for_service,
)

from .config import get_settings

if TYPE_CHECKING:
    from src.type_definitions.graph_service_contracts import (
        ClaimParticipantListResponse,
        CreateManualHypothesisRequest,
        HypothesisListResponse,
        HypothesisResponse,
        KernelClaimEvidenceListResponse,
        KernelGraphDocumentRequest,
        KernelGraphDocumentResponse,
        KernelReasoningPathDetailResponse,
        KernelReasoningPathListResponse,
        KernelRelationClaimCreateRequest,
        KernelRelationClaimListResponse,
        KernelRelationClaimResponse,
        KernelRelationConflictListResponse,
        KernelRelationSuggestionListResponse,
        KernelRelationSuggestionRequest,
    )


def _normalize_uuid(value: UUID | str) -> UUID:
    """Return one normalized UUID for graph-service client calls."""
    return value if isinstance(value, UUID) else UUID(str(value))


class GraphApiGateway:
    """Thin gateway over the deterministic graph API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = GraphServiceClient(
            GraphServiceClientConfig(
                base_url=settings.graph_api_url,
                timeout_seconds=settings.graph_api_timeout_seconds,
                default_headers={
                    "Authorization": (
                        "Bearer "
                        + build_graph_service_bearer_token_for_service(
                            role=UserRole.RESEARCHER,
                            graph_admin=True,
                        )
                    ),
                },
            ),
        )

    def get_health(self) -> GraphServiceHealthResponse:
        """Return graph service liveness information."""
        return self._client.get_health()

    def create_claim(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationClaimCreateRequest,
    ) -> KernelRelationClaimResponse:
        """Create one unresolved relation claim in the graph ledger."""
        return self._client.create_claim(
            space_id=_normalize_uuid(space_id),
            request=request,
        )

    def list_claims(
        self,
        *,
        space_id: UUID | str,
        claim_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        """List graph claims for one research space."""
        return self._client.list_claims(
            space_id=_normalize_uuid(space_id),
            claim_status=claim_status,
            offset=offset,
            limit=limit,
        )

    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        """Suggest missing dictionary-constrained relations for one graph space."""
        return self._client.suggest_relations(
            space_id=_normalize_uuid(space_id),
            request=request,
        )

    def list_reasoning_paths(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        start_entity_id: UUID | str | None = None,
        end_entity_id: UUID | str | None = None,
        status: str | None = None,
        path_kind: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelReasoningPathListResponse:
        """List reasoning paths for one graph space."""
        return self._client.list_reasoning_paths(
            space_id=_normalize_uuid(space_id),
            start_entity_id=(
                _normalize_uuid(start_entity_id)
                if start_entity_id is not None
                else None
            ),
            end_entity_id=(
                _normalize_uuid(end_entity_id) if end_entity_id is not None else None
            ),
            status=status,
            path_kind=path_kind,
            offset=offset,
            limit=limit,
        )

    def get_reasoning_path(
        self,
        *,
        space_id: UUID | str,
        path_id: UUID | str,
    ) -> KernelReasoningPathDetailResponse:
        """Fetch one explained reasoning path from the graph service."""
        return self._client.get_reasoning_path(
            space_id=_normalize_uuid(space_id),
            path_id=_normalize_uuid(path_id),
        )

    def create_manual_hypothesis(
        self,
        *,
        space_id: UUID | str,
        request: CreateManualHypothesisRequest,
    ) -> HypothesisResponse:
        """Create one manual hypothesis in the graph ledger."""
        return self._client.create_manual_hypothesis(
            space_id=_normalize_uuid(space_id),
            request=request,
        )

    def list_hypotheses(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> HypothesisListResponse:
        """List manual and generated hypotheses for one graph space."""
        return self._client.list_hypotheses(
            space_id=_normalize_uuid(space_id),
            offset=offset,
            limit=limit,
        )

    def get_graph_document(
        self,
        *,
        space_id: UUID | str,
        request: KernelGraphDocumentRequest,
    ) -> KernelGraphDocumentResponse:
        """Fetch a unified graph document for one graph space."""
        return self._client.get_graph_document(
            space_id=_normalize_uuid(space_id),
            request=request,
        )

    def list_claims_by_entity(
        self,
        *,
        space_id: UUID | str,
        entity_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        """List graph claims connected to one entity through claim participants."""
        return self._client.list_claims_by_entity(
            space_id=_normalize_uuid(space_id),
            entity_id=_normalize_uuid(entity_id),
            offset=offset,
            limit=limit,
        )

    def list_claim_participants(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> ClaimParticipantListResponse:
        """List structured participants for one graph claim."""
        return self._client.list_claim_participants(
            space_id=_normalize_uuid(space_id),
            claim_id=_normalize_uuid(claim_id),
        )

    def list_claim_evidence(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> KernelClaimEvidenceListResponse:
        """List evidence rows for one graph claim."""
        return self._client.list_claim_evidence(
            space_id=_normalize_uuid(space_id),
            claim_id=_normalize_uuid(claim_id),
        )

    def list_relation_conflicts(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationConflictListResponse:
        """List mixed-polarity canonical relation conflicts."""
        return self._client.list_relation_conflicts(
            space_id=_normalize_uuid(space_id),
            offset=offset,
            limit=limit,
        )

    def close(self) -> None:
        """Close the underlying client."""
        self._client.close()


__all__ = ["GraphApiGateway"]
