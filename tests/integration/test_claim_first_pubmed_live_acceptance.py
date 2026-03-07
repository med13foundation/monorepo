"""Live PubMed acceptance coverage for claim-first orchestration."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.application.agents.services.extraction_service import (
    ExtractionService,
    ExtractionServiceDependencies,
)
from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.database.seeds.seeder import seed_all
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
from src.domain.agents.contracts.extraction import (
    ExtractedRelation,
    ExtractionContract,
)
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.domain.entities.data_source_configs import PubMedQueryConfig
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user import UserRole
from src.domain.entities.user_data_source import SourceType
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.infrastructure.data_sources.pubmed_gateway import PubMedSourceGateway
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)
from src.type_definitions.ingestion import IngestResult

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.entities.kernel.dictionary import DictionarySearchResult

_NON_ALNUM_PATTERN = re.compile(r"[^A-Za-z0-9]+")
_MAX_EVIDENCE_EXCERPT_CHARS = 480


def _resolve_record_pmid(record: dict[str, object]) -> str | None:
    for key in ("pmid", "pubmed_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    candidate_ids = record.get("pubmed_ids")
    if isinstance(candidate_ids, list):
        for value in candidate_ids:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_record_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    return normalized


def _resolve_evidence_excerpt(
    *,
    record: dict[str, object],
    source_label: str,
    target_label: str,
) -> str:
    normalized_title = _normalize_record_text(record.get("title"))
    normalized_abstract = _normalize_record_text(record.get("abstract"))
    candidate_texts = (
        normalized_abstract,
        (
            f"{normalized_title} {normalized_abstract}"
            if normalized_title is not None and normalized_abstract is not None
            else None
        ),
        normalized_title,
    )
    lowered_source = source_label.casefold()
    lowered_target = target_label.casefold()
    for candidate_text in candidate_texts:
        if candidate_text is None:
            continue
        lowered_candidate = candidate_text.casefold()
        source_index = lowered_candidate.find(lowered_source)
        target_index = lowered_candidate.find(lowered_target)
        if source_index < 0 or target_index < 0:
            continue
        first_index = min(source_index, target_index)
        last_index = max(
            source_index + len(source_label),
            target_index + len(target_label),
        )
        excerpt_start = max(0, first_index - 80)
        excerpt_end = min(len(candidate_text), last_index + 120)
        normalized_excerpt = _normalize_record_text(
            _NON_ALNUM_PATTERN.sub(
                " ",
                candidate_text[excerpt_start:excerpt_end],
            ),
        )
        if normalized_excerpt is None:
            continue
        bounded_excerpt = normalized_excerpt[:_MAX_EVIDENCE_EXCERPT_CHARS]
        lowered_excerpt = bounded_excerpt.casefold()
        if lowered_source in lowered_excerpt and lowered_target in lowered_excerpt:
            return bounded_excerpt
    raise AssertionError(
        (
            "Live PubMed record does not contain a usable evidence excerpt for "
            f"{source_label} and {target_label}: {_resolve_record_pmid(record)}"
        ),
    )


def _live_pubmed_enabled() -> bool:
    return os.getenv("MED13_RUN_LIVE_PUBMED_CLAIM_FIRST", "0").strip() == "1"


def _auth_headers(user: UserModel) -> dict[str, str]:
    secret = os.getenv(
        "MED13_DEV_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )
    provider = JWTProvider(secret_key=secret)
    token = provider.create_access_token(
        user_id=user.id,
        role=user.role,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-TEST-USER-ID": str(user.id),
        "X-TEST-USER-EMAIL": user.email,
        "X-TEST-USER-ROLE": user.role,
    }


class _DirectHarness(DictionarySearchHarnessPort):
    def __init__(self, repository: SqlAlchemyDictionaryRepository) -> None:
        self._repository = repository

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        return self._repository.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )


class _FixedExtractionAgent(ExtractionAgentPort):
    def __init__(self, contract: ExtractionContract) -> None:
        self._contract = contract

    async def extract(
        self,
        context: ExtractionContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionContract:
        del context, model_id
        return self._contract

    async def close(self) -> None:
        return None


class _NoopIngestionPipeline:
    def run(self, records, research_space_id: str) -> IngestResult:
        del records, research_space_id
        return IngestResult(success=True, entities_created=0, observations_created=0)


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.slow
@pytest.mark.asyncio
async def test_claim_first_live_pubmed_three_pmids_end_to_end(  # noqa: PLR0915
    postgres_required,
) -> None:
    """Live acceptance: capture claims + graph edges for three real PMIDs."""
    assert postgres_required is None
    if not _live_pubmed_enabled():
        pytest.skip(
            "Set MED13_RUN_LIVE_PUBMED_CLAIM_FIRST=1 to run live PubMed acceptance.",
        )

    from src.database.session import SessionLocal

    live_cases = (
        ("41130977", "Cardiomyopathy"),
        ("22541436", "Obesity"),
        ("30769017", "Hypothyroidism"),
    )

    session = SessionLocal()
    try:
        seed_all(session)

        user = UserModel(
            email=f"claim-first-live-{uuid4().hex}@example.com",
            username=f"claim-first-live-{uuid4().hex}",
            full_name="Claim First Live Acceptance",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER.value,
            status="active",
            email_verified=True,
        )
        session.add(user)
        session.flush()

        space = ResearchSpaceModel(
            slug=f"claim-first-live-{uuid4().hex[:16]}",
            name="Claim First Live PubMed Space",
            description="Live PubMed claim-first acceptance space",
            owner_id=user.id,
            status="active",
            settings={
                "relation_auto_promotion": {"enabled": False},
                "relation_governance_mode": "HUMAN_IN_LOOP",
            },
        )
        session.add(space)
        session.flush()

        source = UserDataSourceModel(
            id=str(uuid4()),
            owner_id=str(user.id),
            research_space_id=str(space.id),
            name="Live PubMed Claim First Source",
            description="Source for live claim-first acceptance",
            source_type=SourceTypeEnum.PUBMED,
            configuration={"query": "MED13", "domain_context": "clinical"},
            status=SourceStatusEnum.ACTIVE,
            ingestion_schedule={},
            quality_metrics={},
            tags=[],
            version="1.0",
        )
        session.add(source)
        session.flush()

        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        dictionary_service = DictionaryManagementService(
            dictionary_repo=dictionary_repo,
            dictionary_search_harness=_DirectHarness(dictionary_repo),
            embedding_provider=None,
        )
        entity_repo = SqlAlchemyKernelEntityRepository(session)
        relation_repo = SqlAlchemyKernelRelationRepository(session)
        claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
        claim_participant_repo = SqlAlchemyKernelClaimParticipantRepository(
            session,
        )
        claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)

        seed_gene = entity_repo.create(
            research_space_id=str(space.id),
            entity_type="GENE",
            display_label="MED13",
            metadata={"source": "live_acceptance"},
        )
        for phenotype_label in {label for _, label in live_cases}:
            entity_repo.create(
                research_space_id=str(space.id),
                entity_type="PHENOTYPE",
                display_label=phenotype_label,
                metadata={"source": "live_acceptance"},
            )

        gateway = PubMedSourceGateway()
        source_document_ids_by_pmid: dict[str, str] = {}

        for pmid, target_label in live_cases:
            config = PubMedQueryConfig(
                query=f"{pmid}[PMID]",
                domain_context="clinical",
                open_access_only=True,
                max_results=1,
                pinned_pubmed_id=pmid,
                relevance_threshold=0,
            )
            records = await gateway.fetch_records(config)
            assert records, f"Live PubMed fetch returned no records for PMID {pmid}"

            record = next(
                (
                    candidate
                    for candidate in records
                    if _resolve_record_pmid(candidate) == pmid
                ),
                records[0],
            )
            resolved_pmid = _resolve_record_pmid(record)
            assert resolved_pmid == pmid
            evidence_excerpt = _resolve_evidence_excerpt(
                record=record,
                source_label="MED13",
                target_label=target_label,
            )

            document = SourceDocument(
                id=uuid4(),
                research_space_id=UUID(str(space.id)),
                source_id=UUID(str(source.id)),
                external_record_id=f"pubmed:{pmid}",
                source_type=SourceType.PUBMED,
                document_format=DocumentFormat.JSON,
                raw_storage_key=f"live/pubmed/{pmid}.json",
                enrichment_status=EnrichmentStatus.ENRICHED,
                extraction_status=DocumentExtractionStatus.PENDING,
                metadata={"raw_record": record},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            source_document_ids_by_pmid[pmid] = str(document.id)

            recognition_contract = EntityRecognitionContract(
                decision="generated",
                confidence_score=0.95,
                rationale=f"Live recognition context for PMID {pmid}.",
                evidence=[
                    EvidenceItem(
                        source_type="db",
                        locator=f"pmid:{pmid}",
                        excerpt=str(record.get("title", ""))[:200],
                        relevance=0.9,
                    ),
                ],
                source_type="pubmed",
                document_id=str(document.id),
                primary_entity_type="PUBLICATION",
                field_candidates=[],
                recognized_entities=[],
                recognized_observations=[],
                pipeline_payloads=[],
                shadow_mode=False,
                agent_run_id=f"recognition-live-{pmid}",
            )
            extraction_contract = ExtractionContract(
                decision="generated",
                confidence_score=0.93,
                rationale=f"Live extraction candidate for PMID {pmid}.",
                evidence=[
                    EvidenceItem(
                        source_type="paper",
                        locator=f"pmid:{pmid}",
                        excerpt=str(record.get("title", ""))[:200],
                        relevance=0.9,
                    ),
                ],
                source_type="pubmed",
                document_id=str(document.id),
                observations=[],
                relations=[
                    ExtractedRelation(
                        source_type="GENE",
                        relation_type="ASSOCIATED_WITH",
                        target_type="PHENOTYPE",
                        source_label="MED13",
                        target_label=target_label,
                        evidence_excerpt=evidence_excerpt,
                        evidence_locator=f"pubmed:{pmid}:abstract",
                        confidence=0.88,
                    ),
                ],
                rejected_facts=[],
                pipeline_payloads=[],
                shadow_mode=False,
                agent_run_id=f"extraction-live-{pmid}",
            )

            extraction_service = ExtractionService(
                dependencies=ExtractionServiceDependencies(
                    extraction_agent=_FixedExtractionAgent(extraction_contract),
                    ingestion_pipeline=_NoopIngestionPipeline(),
                    relation_repository=relation_repo,
                    relation_claim_repository=claim_repo,
                    claim_participant_repository=claim_participant_repo,
                    claim_evidence_repository=claim_evidence_repo,
                    entity_repository=entity_repo,
                    dictionary_service=dictionary_service,
                ),
            )

            outcome = await extraction_service.extract_from_entity_recognition(
                document=document,
                recognition_contract=recognition_contract,
                research_space_settings={
                    "relation_governance_mode": "HUMAN_IN_LOOP",
                    "relation_auto_promotion": {"enabled": False},
                },
            )
            assert outcome.status == "extracted"
            assert outcome.persisted_relations_count >= 1
            assert outcome.rejected_relation_reasons == ()
            await extraction_service.close()

        session.commit()

        claims = claim_repo.find_by_research_space(str(space.id), limit=200, offset=0)
        assert claims, "No relation claims were created for live PubMed acceptance run."
        for pmid, _ in live_cases:
            source_document_id = source_document_ids_by_pmid[pmid]
            claims_for_pmid = [
                claim
                for claim in claims
                if str(claim.source_document_id) == source_document_id
            ]
            assert claims_for_pmid, f"No claim rows found for PMID {pmid}"
            assert any(
                claim.persistability == "PERSISTABLE" for claim in claims_for_pmid
            )
            assert any(
                claim.linked_relation_id is not None for claim in claims_for_pmid
            )

        app = create_app()
        client = TestClient(app)
        headers = _auth_headers(user)

        def edge_count_for(curation_statuses: list[str] | None) -> int:
            payload: dict[str, object] = {
                "mode": "seeded",
                "seed_entity_ids": [str(seed_gene.id)],
                "depth": 2,
                "top_k": 50,
                "max_nodes": 200,
                "max_edges": 200,
            }
            if curation_statuses is not None:
                payload["curation_statuses"] = curation_statuses

            response = client.post(
                f"/research-spaces/{space.id}/graph/subgraph",
                headers=headers,
                json=payload,
            )
            assert response.status_code == 200, response.text
            return len(response.json()["edges"])

        all_edges = edge_count_for(None)
        approved_edges = edge_count_for(["APPROVED"])
        pending_edges = edge_count_for(["DRAFT", "UNDER_REVIEW"])
        rejected_edges = edge_count_for(["REJECTED", "RETRACTED"])

        assert all_edges >= 1
        assert pending_edges == all_edges
        assert approved_edges == 0
        assert rejected_edges == 0
    finally:
        session.close()
