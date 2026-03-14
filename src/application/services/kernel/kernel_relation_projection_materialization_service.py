"""Materialize canonical relations as claim-backed projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.kernel.relations import RelationEvidenceWrite
from src.domain.value_objects.relation_types import normalize_relation_type
from src.graph.core.read_model import (
    GraphReadModelTrigger,
    GraphReadModelUpdate,
)

from ._kernel_relation_projection_materialization_support import (
    RelationProjectionMaterializationError,
    RelationProjectionMaterializationResult,
    _backfill_claim_evidence_from_relation_cache,
    _claim_evidence_provenance_id,
    _claim_evidence_summary,
    _claim_evidence_tier,
    _dedupe_relation_ids,
    _is_active_support_claim,
    _participant_for_role,
    _ProjectionEndpoints,
    _relation_provenance_id,
)

if TYPE_CHECKING:
    from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
    from src.domain.entities.kernel.relation_claims import KernelRelationClaim
    from src.domain.entities.kernel.relation_projection_sources import (
        RelationProjectionOrigin,
    )
    from src.domain.entities.kernel.relations import (
        KernelRelation,
    )
    from src.domain.repositories.kernel.claim_evidence_repository import (
        KernelClaimEvidenceRepository,
    )
    from src.domain.repositories.kernel.claim_participant_repository import (
        KernelClaimParticipantRepository,
    )
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_claim_repository import (
        KernelRelationClaimRepository,
    )
    from src.domain.repositories.kernel.relation_projection_source_repository import (
        KernelRelationProjectionSourceRepository,
    )
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.graph.core.read_model import GraphReadModelUpdateDispatcher


class KernelRelationProjectionMaterializationService:
    """Canonical relation write owner for claim-backed projection materialization."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        relation_repo: KernelRelationRepository,
        relation_claim_repo: KernelRelationClaimRepository,
        claim_participant_repo: KernelClaimParticipantRepository,
        claim_evidence_repo: KernelClaimEvidenceRepository,
        entity_repo: KernelEntityRepository,
        dictionary_repo: DictionaryRepository,
        relation_projection_repo: KernelRelationProjectionSourceRepository,
        read_model_update_dispatcher: GraphReadModelUpdateDispatcher,
    ) -> None:
        self._relations = relation_repo
        self._claims = relation_claim_repo
        self._participants = claim_participant_repo
        self._claim_evidence = claim_evidence_repo
        self._entities = entity_repo
        self._dictionary = dictionary_repo
        self._projection_sources = relation_projection_repo
        self._read_model_updates = read_model_update_dispatcher

    def materialize_support_claim(
        self,
        claim_id: str,
        research_space_id: str,
        projection_origin: RelationProjectionOrigin,
        reviewed_by: str | None = None,
    ) -> RelationProjectionMaterializationResult:
        del reviewed_by
        claim = self._get_claim_or_raise(
            claim_id=claim_id,
            research_space_id=research_space_id,
        )
        self._assert_support_claim_materializable(claim)
        endpoints = self._resolve_projection_endpoints(
            claim=claim,
            research_space_id=research_space_id,
        )
        claim_evidences = self._claim_evidence.find_by_claim_id(claim_id)
        relation = self._relations.upsert_relation(
            research_space_id=research_space_id,
            source_id=endpoints.source_id,
            relation_type=endpoints.relation_type,
            target_id=endpoints.target_id,
            curation_status="DRAFT",
            provenance_id=_relation_provenance_id(
                claim=claim,
                evidences=claim_evidences,
            ),
        )
        stale_relation_ids: list[str] = []
        for existing_row in self._projection_sources.find_by_claim_id(
            research_space_id=research_space_id,
            claim_id=claim_id,
        ):
            existing_relation_id = str(existing_row.relation_id)
            if existing_relation_id == str(relation.id):
                continue
            if self._projection_sources.delete_projection_source(
                research_space_id=research_space_id,
                relation_id=existing_relation_id,
                claim_id=claim_id,
            ):
                stale_relation_ids.append(existing_relation_id)
        self._projection_sources.create(
            research_space_id=research_space_id,
            relation_id=str(relation.id),
            claim_id=claim_id,
            projection_origin=projection_origin,
            source_document_id=(
                str(claim.source_document_id)
                if claim.source_document_id is not None
                else None
            ),
            source_document_ref=claim.source_document_ref,
            agent_run_id=claim.agent_run_id,
            metadata={"origin": projection_origin.lower()},
        )
        self._claims.link_relation(claim_id, linked_relation_id=str(relation.id))
        rebuilt = self.rebuild_relation_projection(
            relation_id=str(relation.id),
            research_space_id=research_space_id,
        )
        deleted_relation_ids = list(rebuilt.deleted_relation_ids)
        rebuilt_relation_ids = list(rebuilt.rebuilt_relation_ids)
        for stale_relation_id in stale_relation_ids:
            stale_result = self.rebuild_relation_projection(
                relation_id=stale_relation_id,
                research_space_id=research_space_id,
            )
            deleted_relation_ids.extend(stale_result.deleted_relation_ids)
            rebuilt_relation_ids.extend(stale_result.rebuilt_relation_ids)
        return RelationProjectionMaterializationResult(
            relation=rebuilt.relation,
            rebuilt_relation_ids=tuple(
                _dedupe_relation_ids([str(relation.id), *rebuilt_relation_ids]),
            ),
            deleted_relation_ids=tuple(_dedupe_relation_ids(deleted_relation_ids)),
            derived_evidence_rows=rebuilt.derived_evidence_rows,
        )

    def detach_claim_projection(
        self,
        claim_id: str,
        research_space_id: str,
    ) -> RelationProjectionMaterializationResult:
        self._claims.clear_relation_link(claim_id)
        affected_relation_ids = self._projection_sources.delete_by_claim_id(
            research_space_id=research_space_id,
            claim_id=claim_id,
        )
        rebuilt_relation_ids: list[str] = []
        deleted_relation_ids: list[str] = []
        for relation_id in affected_relation_ids:
            rebuilt = self.rebuild_relation_projection(
                relation_id=relation_id,
                research_space_id=research_space_id,
            )
            rebuilt_relation_ids.extend(rebuilt.rebuilt_relation_ids)
            deleted_relation_ids.extend(rebuilt.deleted_relation_ids)
        return RelationProjectionMaterializationResult(
            relation=None,
            rebuilt_relation_ids=tuple(_dedupe_relation_ids(rebuilt_relation_ids)),
            deleted_relation_ids=tuple(_dedupe_relation_ids(deleted_relation_ids)),
            derived_evidence_rows=0,
        )

    def rebuild_relation_projection(  # noqa: C901, PLR0912, PLR0915
        self,
        relation_id: str,
        research_space_id: str,
    ) -> RelationProjectionMaterializationResult:
        current_relation = self._relations.get_by_id(
            relation_id,
            claim_backed_only=False,
        )
        projection_rows = self._projection_sources.find_by_relation_id(relation_id)
        if not projection_rows:
            if current_relation is None:
                return RelationProjectionMaterializationResult(
                    relation=None,
                    rebuilt_relation_ids=(),
                    deleted_relation_ids=(),
                    derived_evidence_rows=0,
                )
            self._relations.delete(relation_id)
            result = RelationProjectionMaterializationResult(
                relation=None,
                rebuilt_relation_ids=(),
                deleted_relation_ids=(relation_id,),
                derived_evidence_rows=0,
            )
            self._dispatch_projection_change(
                research_space_id=research_space_id,
                claim_ids=(),
                relation_ids=(relation_id,),
                entity_ids=(
                    str(current_relation.source_id),
                    str(current_relation.target_id),
                ),
            )
            return result

        claims_by_id = {
            str(claim.id): claim
            for claim in self._claims.list_by_ids(
                [str(row.claim_id) for row in projection_rows],
            )
        }
        participants_by_claim_id = self._participants.find_by_claim_ids(
            [str(row.claim_id) for row in projection_rows],
        )
        current_evidence = self._relations.list_evidence_for_relation(
            research_space_id=research_space_id,
            relation_id=relation_id,
            claim_backed_only=False,
        )
        valid_sources: list[tuple[str, KernelRelationClaim, _ProjectionEndpoints]] = []
        pruned_claim_ids: list[str] = []
        expected_signature: tuple[str, str, str, str] | None = None

        for row in projection_rows:
            claim_id = str(row.claim_id)
            claim = claims_by_id.get(claim_id)
            if claim is None:
                pruned_claim_ids.append(claim_id)
                continue
            if not _is_active_support_claim(claim):
                pruned_claim_ids.append(claim_id)
                continue
            try:
                endpoints = self._resolve_projection_endpoints(
                    claim=claim,
                    research_space_id=research_space_id,
                    participants=participants_by_claim_id.get(claim_id, []),
                )
            except RelationProjectionMaterializationError:
                pruned_claim_ids.append(claim_id)
                continue
            signature = (
                endpoints.source_id,
                endpoints.relation_type,
                endpoints.target_id,
                research_space_id,
            )
            if expected_signature is None:
                expected_signature = signature
            if signature != expected_signature:
                pruned_claim_ids.append(claim_id)
                continue
            valid_sources.append((claim_id, claim, endpoints))

        for claim_id in pruned_claim_ids:
            self._projection_sources.delete_projection_source(
                research_space_id=research_space_id,
                relation_id=relation_id,
                claim_id=claim_id,
            )

        if not valid_sources:
            if current_relation is not None:
                self._relations.delete(relation_id)
                result = RelationProjectionMaterializationResult(
                    relation=None,
                    rebuilt_relation_ids=(),
                    deleted_relation_ids=(relation_id,),
                    derived_evidence_rows=0,
                )
                self._dispatch_projection_change(
                    research_space_id=research_space_id,
                    claim_ids=tuple(pruned_claim_ids),
                    relation_ids=(relation_id,),
                    entity_ids=(
                        str(current_relation.source_id),
                        str(current_relation.target_id),
                    ),
                )
                return result
            return RelationProjectionMaterializationResult(relation=None)

        if len(valid_sources) == 1 and not self._claim_evidence.find_by_claim_id(
            valid_sources[0][0],
        ):
            _backfill_claim_evidence_from_relation_cache(
                claim_id=valid_sources[0][0],
                claim=valid_sources[0][1],
                current_evidence=current_evidence,
                claim_evidence_repo=self._claim_evidence,
            )

        endpoints = valid_sources[0][2]
        relation = self._relations.upsert_relation(
            research_space_id=research_space_id,
            source_id=endpoints.source_id,
            relation_type=endpoints.relation_type,
            target_id=endpoints.target_id,
            curation_status=(
                current_relation.curation_status
                if current_relation is not None
                else "DRAFT"
            ),
            provenance_id=(
                str(current_relation.provenance_id)
                if current_relation is not None
                and current_relation.provenance_id is not None
                else None
            ),
        )
        for claim_id, _claim, _endpoints in valid_sources:
            self._claims.link_relation(claim_id, linked_relation_id=str(relation.id))

        derived_evidences: list[RelationEvidenceWrite] = []
        for claim_id, claim, _endpoints in valid_sources:
            derived_evidences.extend(
                [
                    RelationEvidenceWrite(
                        confidence=float(evidence.confidence),
                        evidence_summary=_claim_evidence_summary(
                            claim=claim,
                            evidence=evidence,
                        ),
                        evidence_sentence=evidence.sentence,
                        evidence_sentence_source=evidence.sentence_source,
                        evidence_sentence_confidence=evidence.sentence_confidence,
                        evidence_sentence_rationale=evidence.sentence_rationale,
                        evidence_tier=_claim_evidence_tier(evidence),
                        provenance_id=_claim_evidence_provenance_id(evidence),
                        source_document_id=evidence.source_document_id,
                        source_document_ref=evidence.source_document_ref,
                        agent_run_id=evidence.agent_run_id or claim.agent_run_id,
                    )
                    for evidence in self._claim_evidence.find_by_claim_id(claim_id)
                ],
            )
        relation = self._relations.replace_derived_evidence_cache(
            str(relation.id),
            evidences=derived_evidences,
        )
        deleted_relation_ids: tuple[str, ...] = ()
        if current_relation is not None and str(current_relation.id) != str(
            relation.id,
        ):
            self._relations.delete(str(current_relation.id))
            deleted_relation_ids = (str(current_relation.id),)
        result = RelationProjectionMaterializationResult(
            relation=relation,
            rebuilt_relation_ids=(str(relation.id),),
            deleted_relation_ids=deleted_relation_ids,
            derived_evidence_rows=len(derived_evidences),
        )
        self._dispatch_projection_change(
            research_space_id=research_space_id,
            claim_ids=tuple(claim_id for claim_id, _claim, _endpoints in valid_sources),
            relation_ids=(
                str(relation.id),
                *deleted_relation_ids,
            ),
            entity_ids=(
                str(relation.source_id),
                str(relation.target_id),
            ),
        )
        return result

    def find_claim_backed_relation_for_claim(
        self,
        *,
        claim_id: str,
        research_space_id: str,
    ) -> KernelRelation | None:
        claim = self._get_claim_or_raise(
            claim_id=claim_id,
            research_space_id=research_space_id,
        )
        endpoints = self._resolve_projection_endpoints(
            claim=claim,
            research_space_id=research_space_id,
        )
        return self._relations.find_by_triple(
            research_space_id=research_space_id,
            source_id=endpoints.source_id,
            relation_type=endpoints.relation_type,
            target_id=endpoints.target_id,
            claim_backed_only=True,
        )

    def _get_claim_or_raise(
        self,
        *,
        claim_id: str,
        research_space_id: str,
    ) -> KernelRelationClaim:
        claim = self._claims.get_by_id(claim_id)
        if claim is None or str(claim.research_space_id) != research_space_id:
            msg = f"Relation claim {claim_id} not found in research space {research_space_id}"
            raise RelationProjectionMaterializationError(msg)
        return claim

    def _assert_support_claim_materializable(self, claim: KernelRelationClaim) -> None:
        if claim.polarity != "SUPPORT":
            msg = "Only SUPPORT claims can materialize canonical relations"
            raise RelationProjectionMaterializationError(msg)
        if claim.claim_status != "RESOLVED":
            msg = "Only RESOLVED claims can materialize canonical relations"
            raise RelationProjectionMaterializationError(msg)
        if claim.persistability != "PERSISTABLE":
            msg = "Only PERSISTABLE claims can materialize canonical relations"
            raise RelationProjectionMaterializationError(msg)

    def _resolve_projection_endpoints(
        self,
        *,
        claim: KernelRelationClaim,
        research_space_id: str,
        participants: list[KernelClaimParticipant] | None = None,
    ) -> _ProjectionEndpoints:
        claim_participants = (
            participants
            if participants is not None
            else self._participants.find_by_claim_id(str(claim.id))
        )
        subject = _participant_for_role(claim_participants, role="SUBJECT")
        object_participant = _participant_for_role(claim_participants, role="OBJECT")
        if (
            subject is None
            or object_participant is None
            or subject.entity_id is None
            or object_participant.entity_id is None
        ):
            msg = (
                "Claim-backed materialization requires SUBJECT/OBJECT participants "
                "with entity anchors"
            )
            raise RelationProjectionMaterializationError(msg)
        source_entity = self._entities.get_by_id(str(subject.entity_id))
        target_entity = self._entities.get_by_id(str(object_participant.entity_id))
        if source_entity is None or target_entity is None:
            msg = "Claim participant endpoint entities must exist before projection"
            raise RelationProjectionMaterializationError(msg)
        if str(source_entity.research_space_id) != research_space_id:
            msg = f"Source entity {source_entity.id} is not in research space {research_space_id}"
            raise RelationProjectionMaterializationError(msg)
        if str(target_entity.research_space_id) != research_space_id:
            msg = f"Target entity {target_entity.id} is not in research space {research_space_id}"
            raise RelationProjectionMaterializationError(msg)
        normalized_relation_type = normalize_relation_type(claim.relation_type)
        if not normalized_relation_type:
            msg = "relation_type is required"
            raise RelationProjectionMaterializationError(msg)
        canonical_relation_type = normalized_relation_type
        resolved_relation_type = self._dictionary.resolve_relation_synonym(
            normalized_relation_type,
        )
        if resolved_relation_type is not None:
            resolved_relation_type_id = getattr(resolved_relation_type, "id", None)
            if (
                isinstance(resolved_relation_type_id, str)
                and resolved_relation_type_id.strip()
            ):
                canonical_relation_type = resolved_relation_type_id.strip().upper()
        if not self._dictionary.is_triple_allowed(
            source_entity.entity_type,
            canonical_relation_type,
            target_entity.entity_type,
        ):
            msg = (
                f"Triple ({source_entity.entity_type}, {canonical_relation_type}, "
                f"{target_entity.entity_type}) is not allowed by constraints"
            )
            raise RelationProjectionMaterializationError(msg)
        return _ProjectionEndpoints(
            source_id=str(source_entity.id),
            source_label=source_entity.display_label,
            source_type=source_entity.entity_type,
            relation_type=canonical_relation_type,
            target_id=str(target_entity.id),
            target_label=target_entity.display_label,
            target_type=target_entity.entity_type,
        )

    def _dispatch_projection_change(
        self,
        *,
        research_space_id: str,
        claim_ids: tuple[str, ...],
        relation_ids: tuple[str, ...],
        entity_ids: tuple[str, ...],
    ) -> None:
        normalized_claim_ids = tuple(dict.fromkeys(claim_ids))
        normalized_relation_ids = tuple(dict.fromkeys(relation_ids))
        normalized_entity_ids = tuple(dict.fromkeys(entity_ids))
        updates = (
            GraphReadModelUpdate(
                model_name="entity_neighbors",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                claim_ids=normalized_claim_ids,
                relation_ids=normalized_relation_ids,
                entity_ids=normalized_entity_ids,
                space_id=research_space_id,
            ),
            GraphReadModelUpdate(
                model_name="entity_relation_summary",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                claim_ids=normalized_claim_ids,
                relation_ids=normalized_relation_ids,
                entity_ids=normalized_entity_ids,
                space_id=research_space_id,
            ),
            GraphReadModelUpdate(
                model_name="entity_claim_summary",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                claim_ids=normalized_claim_ids,
                relation_ids=normalized_relation_ids,
                entity_ids=normalized_entity_ids,
                space_id=research_space_id,
            ),
        )
        self._read_model_updates.dispatch_many(updates)


__all__ = [
    "KernelRelationProjectionMaterializationService",
    "RelationProjectionMaterializationError",
    "RelationProjectionMaterializationResult",
]
