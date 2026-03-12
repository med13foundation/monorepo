# Plan

We will migrate the kernel from "claim-first ingestion + canonical-first serving" to a strict hybrid model where relation claims are authoritative and canonical `relations` are materialized projections. The approach is to harden schema lineage, remove direct edge writes, keep canonical queries as the default read surface, and make every projected relation explainable by one or more claims.

## Progress
- Completed: added explicit projection lineage with `relation_projection_sources`, plus the required `(id, research_space_id)` uniqueness on `relations`.
- Completed: wired extraction persistence, curator claim resolution, direct `POST /relations`, and graph-connection persistence to create claim-backed projection lineage rows.
- Completed: added orphan-relation diagnostics plus deferred PostgreSQL enforcement so new canonical relations must have claim-backed projection lineage by transaction commit.
- Completed: tightened extraction, graph connection, manual relation creation, and claim-resolution promotion so projection-lineage failure rolls back the canonical relation write.
- Completed: added focused migration, unit, and API coverage for the new lineage path.
- Remaining: move canonical write ownership fully behind a projection service, and tighten read paths so canonical graph responses are guaranteed claim-backed by policy rather than convention.

## Scope
- In: schema and migration work for projection lineage, relation write-path refactors, canonical read-path hardening, claim participant normalization, and validation/rollout checks for claim-backed projections.
- Out: redesigning the `claim_relations` taxonomy, major UI/visual redesign beyond preserving canonical and claim-overlay modes, and retroactive perfect reconstruction of legacy canonical relations that were created without claims.

## Action items
[x] Add a projection-lineage table in `alembic/versions/`, `src/models/database/kernel/`, `src/domain/entities/kernel/`, and `src/domain/repositories/kernel/` that links each canonical `relations.id` to one or more `relation_claims.id`, stores projection metadata, and becomes the authoritative explainability record for projected edges.
[x] Add migration checks and staged enforcement for orphan canonical relations so new writes cannot create a `relations` row without projection lineage, while existing orphan rows are reported and remediated through a backfill or curator repair workflow before full enforcement.
[ ] Refactor `src/application/services/kernel/kernel_relation_service.py` and `src/infrastructure/repositories/kernel/kernel_relation_repository.py` so generic canonical edge creation is no longer the public write primitive; introduce a projection service that materializes or updates a relation only from claim-backed inputs.
[x] Route extraction persistence through the new projection service by updating `src/application/agents/services/_extraction_relation_candidate_write_flow.py` and `src/application/agents/services/_extraction_relation_persistence_helpers.py` so extraction continues to write claims first and then records projection lineage when a persistable candidate is materialized into `relations`.
[x] Change direct relation-writing flows in `src/routes/research_spaces/kernel_relations_routes.py` and `src/application/agents/services/graph_connection_service.py` so they create claims or review proposals first instead of writing canonical `relations` directly; keep curator resolution as the explicit promotion path from accepted claims to projected relations.
[ ] Collapse duplicate evidence truth by making canonical `relation_evidence` derived from linked `claim_evidence` rows or by replacing it with a projection-summary layer, then update `src/infrastructure/repositories/kernel/graph_query_repository.py` and related presenters so canonical query results can always explain themselves via linked claims.
[ ] Make `claim_participants` mandatory for all new claims, use `src/application/services/kernel/kernel_claim_participant_backfill_service.py` to close historical gaps, and remove claim retrieval logic that depends on raw `metadata_payload` for core structural joins.
[ ] Update deterministic search, relation listing, graph export, and subgraph assembly so canonical queries remain the default read surface but only return claim-backed projections, while claim overlay remains an inspection and debugging mode rather than an alternate truth source.
[x] Add migration, repository, route, and integration tests for orphan-relation rejection, projection lineage presence, extraction projection semantics, graph-connection claim-first behavior, and canonical explainability guarantees; validate with `make type-check`, `make test`, and focused kernel route/integration suites.
[ ] Roll out in phases by first measuring orphan canonical relations, then backfilling or repairing lineage, then cutting over write paths, then enabling hard enforcement, and finally removing or locking down the direct `POST /relations` surface once no internal callers depend on it.

## Verified
- Passed: `./venv/bin/python -m pytest tests/unit/database/test_alembic_migration_regressions.py tests/unit/application/services/test_graph_connection_service.py tests/integration/api/test_kernel_routes_api.py -q`
- Passed: `make all`
- Note: PostgreSQL-only API cases in `tests/integration/api/test_kernel_routes_api.py` remained skipped in this environment, consistent with existing test markers.

## Open questions
- Resolved for now: projection lineage lives in a dedicated `relation_projection_sources` table; the remaining question is whether `relation_claims.linked_relation_id` should eventually become a compatibility field only or be removed after full cutover.
- Should `relation_evidence` remain as a cache or materialized summary for fast reads, or should canonical evidence be served directly from claim-backed joins?
- Should curator-authored canonical relations be modeled as explicit manual claims, or should direct curator creation of canonical relations be removed entirely?
