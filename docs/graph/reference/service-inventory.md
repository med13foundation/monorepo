# Graph Service Inventory

This document records the active runtime surface of the standalone graph
service, the callers that are allowed to reach it, and the artifacts that define
the public contract.

## Contract artifacts

- `docs/graph/reference/endpoints.md`
  Human-readable method/path/access inventory.
- `services/graph_api/openapi.json`
  Generated request/response contract for the live service.
- `src/web/types/graph-service.generated.ts`
  Generated TypeScript contract consumed by the web/admin client.

## Service-owned runtime

### Entrypoints, runtime wiring, and packaging

- `services/graph_api/__init__.py`
- `services/graph_api/__main__.py`
- `services/graph_api/main.py`
- `services/graph_api/app.py`
- `services/graph_api/auth.py`
- `services/graph_api/config.py`
- `services/graph_api/database.py`
- `services/graph_api/composition.py`
- `services/graph_api/dependencies.py`
- `services/graph_api/manage.py`
- `services/graph_api/alembic.ini`
- `services/graph_api/alembic/`
- `services/graph_api/README.md`
- `services/graph_api/Dockerfile`

### Service-local governance and persistence helpers

- `services/graph_api/governance.py`
- `services/graph_api/dictionary_repository.py` (compatibility re-export)
- `services/graph_api/concept_repository.py` (compatibility re-export)

### Service-local graph read/write helpers

- `services/graph_api/graph_document_builder.py`
- `services/graph_api/_graph_document_support.py`
- `services/graph_api/_relation_evidence_presenter.py`
- `services/graph_api/_relation_subgraph_helpers.py`
- `services/graph_api/operation_runs.py`

### Neutral shared graph-runtime helpers used by the service

- `src/database/graph_schema.py`
- `src/infrastructure/dependency_injection/graph_runtime_factories.py`
- `src/infrastructure/repositories/graph_observability_repository.py`
- `src/infrastructure/queries/graph_security_queries.py`

### Generated service contract artifact

- `services/graph_api/openapi.json`

### Service-owned routers

- `services/graph_api/routers/health.py`
- `services/graph_api/routers/entities.py`
- `services/graph_api/routers/observations.py`
- `services/graph_api/routers/provenance.py`
- `services/graph_api/routers/claims.py`
- `services/graph_api/routers/relations.py`
- `services/graph_api/routers/graph_documents.py`
- `services/graph_api/routers/graph_views.py`
- `services/graph_api/routers/search.py`
- `services/graph_api/routers/graph_connections.py`
- `services/graph_api/routers/relation_suggestions.py`
- `services/graph_api/routers/reasoning_paths.py`
- `services/graph_api/routers/hypotheses.py`
- `services/graph_api/routers/concepts.py`
- `services/graph_api/routers/dictionary.py`
- `services/graph_api/routers/spaces.py`
- `services/graph_api/routers/operations.py`

## Shared graph domain/runtime code reused by the service

These modules still live under `src/`, but the standalone graph service is now
their runtime owner:

- `src/application/services/kernel/`
- `src/infrastructure/repositories/kernel/`
- `src/models/database/kernel/`
- `src/application/agents/services/graph_search_service.py`
- `src/application/agents/services/graph_connection_service.py`

The graph-boundary validator requires any runtime use of these modules outside
`services/graph_api/` to go through the typed client or approved service-local
bridge modules.

## Platform-side graph callers

### Backend/platform HTTP client boundary

- `src/infrastructure/graph_service/client.py`
- `src/infrastructure/graph_service/runtime.py`
- `src/infrastructure/graph_service/pipeline.py`
- `src/infrastructure/graph_service/space_sync.py`
- `src/infrastructure/graph_service/space_lifecycle_sync.py`
- `src/infrastructure/graph_service/errors.py`

### Web/client boundary

- `src/web/lib/api/graph-client.ts`
- `src/web/lib/api/graph-base-url.ts`
- `src/web/lib/api/kernel.ts`
- `src/web/lib/api/concepts.ts`
- `src/web/lib/api/dictionary.ts`
- `src/web/types/graph-service.generated.ts`

### Platform-owned graph control-plane callers

- `src/application/services/research_space_management_service.py`
- `src/application/services/membership_management_service.py`
- `src/application/services/space_lifecycle_sync_service.py`
- `src/routes/research_spaces/space_routes.py`
- `src/routes/research_spaces/membership_routes.py`

## Operational entrypoints

### Graph runtime

- `make run-graph-service`
- `make graph-db-wait`
- `make graph-db-migrate`
- `python -m services.graph_api`
- `python -m services.graph_api.manage`

### Graph control-plane and repair flows

- `make graph-readiness`
- `make graph-reasoning-rebuild`
- `make graph-space-sync`
- `scripts/check_claim_projection_readiness.py`
- `scripts/rebuild_reasoning_paths.py`
- `scripts/sync_graph_spaces.py`

### Graph boundary and contract tooling

- `scripts/validate_graph_service_boundary.py`
- `scripts/export_graph_openapi.py`
- `scripts/generate_ts_types.py`
- `make graph-service-openapi`
- `make graph-service-client-types`
- `make graph-service-sync-contracts`
- `make graph-service-contract-check`
- `make graph-service-lint`
- `make graph-service-type-check`
- `make graph-service-test`
- `make graph-service-checks`

### Deploy/runtime hardening

- `.github/workflows/graph-service-deploy.yml`
- `scripts/deploy/sync_graph_cloud_run_runtime_config.sh`
- `scripts/deploy/validate_shared_instance_graph_topology.py`
- `make graph-topology-validate`

## Current public path inventory

Exact method/path semantics live in `docs/graph/reference/endpoints.md`, and exact
request/response schemas live in `services/graph_api/openapi.json`.

The service currently publishes these path templates:

### Health

- `/health`

### Space-scoped graph paths

- `/v1/spaces/{space_id}/entities`
- `/v1/spaces/{space_id}/entities/{entity_id}`
- `/v1/spaces/{space_id}/entities/{entity_id}/similar`
- `/v1/spaces/{space_id}/entities/{entity_id}/connections`
- `/v1/spaces/{space_id}/entities/embeddings/refresh`
- `/v1/spaces/{space_id}/observations`
- `/v1/spaces/{space_id}/observations/{observation_id}`
- `/v1/spaces/{space_id}/provenance`
- `/v1/spaces/{space_id}/provenance/{provenance_id}`
- `/v1/spaces/{space_id}/claims`
- `/v1/spaces/{space_id}/claims/by-entity/{entity_id}`
- `/v1/spaces/{space_id}/claims/{claim_id}`
- `/v1/spaces/{space_id}/claims/{claim_id}/participants`
- `/v1/spaces/{space_id}/claims/{claim_id}/evidence`
- `/v1/spaces/{space_id}/claims/{claim_id}/mechanism-chain`
- `/v1/spaces/{space_id}/claim-relations`
- `/v1/spaces/{space_id}/claim-relations/{relation_id}`
- `/v1/spaces/{space_id}/claim-participants/backfill`
- `/v1/spaces/{space_id}/claim-participants/coverage`
- `/v1/spaces/{space_id}/relations`
- `/v1/spaces/{space_id}/relations/{relation_id}`
- `/v1/spaces/{space_id}/relations/conflicts`
- `/v1/spaces/{space_id}/graph/export`
- `/v1/spaces/{space_id}/graph/subgraph`
- `/v1/spaces/{space_id}/graph/neighborhood/{entity_id}`
- `/v1/spaces/{space_id}/graph/document`
- `/v1/spaces/{space_id}/graph/views/{view_type}/{resource_id}`
- `/v1/spaces/{space_id}/graph/search`
- `/v1/spaces/{space_id}/graph/connections/discover`
- `/v1/spaces/{space_id}/graph/relation-suggestions`
- `/v1/spaces/{space_id}/reasoning-paths`
- `/v1/spaces/{space_id}/reasoning-paths/{path_id}`
- `/v1/spaces/{space_id}/hypotheses`
- `/v1/spaces/{space_id}/hypotheses/manual`
- `/v1/spaces/{space_id}/hypotheses/generate`
- `/v1/spaces/{space_id}/concepts/sets`
- `/v1/spaces/{space_id}/concepts/members`
- `/v1/spaces/{space_id}/concepts/aliases`
- `/v1/spaces/{space_id}/concepts/policy`
- `/v1/spaces/{space_id}/concepts/decisions`
- `/v1/spaces/{space_id}/concepts/decisions/propose`
- `/v1/spaces/{space_id}/concepts/decisions/{decision_id}/status`

### Graph admin and control-plane paths

- `/v1/admin/spaces`
- `/v1/admin/spaces/{space_id}`
- `/v1/admin/spaces/{space_id}/memberships`
- `/v1/admin/spaces/{space_id}/memberships/{user_id}`
- `/v1/admin/spaces/{space_id}/sync`
- `/v1/admin/projections/readiness`
- `/v1/admin/projections/repair`
- `/v1/admin/reasoning-paths/rebuild`
- `/v1/admin/operations/runs`
- `/v1/admin/operations/runs/{run_id}`

### Dictionary governance paths

- `/v1/dictionary/search`
- `/v1/dictionary/search/by-domain/{domain_context}`
- `/v1/dictionary/reembed`
- `/v1/dictionary/resolution-policies`
- `/v1/dictionary/relation-constraints`
- `/v1/dictionary/changelog`
- `/v1/dictionary/variables`
- `/v1/dictionary/variables/{variable_id}/review-status`
- `/v1/dictionary/variables/{variable_id}/revoke`
- `/v1/dictionary/variables/{variable_id}/merge`
- `/v1/dictionary/value-sets`
- `/v1/dictionary/value-sets/{value_set_id}/items`
- `/v1/dictionary/value-set-items/{value_set_item_id}/active`
- `/v1/dictionary/entity-types`
- `/v1/dictionary/entity-types/{entity_type_id}`
- `/v1/dictionary/entity-types/{entity_type_id}/review-status`
- `/v1/dictionary/entity-types/{entity_type_id}/revoke`
- `/v1/dictionary/entity-types/{entity_type_id}/merge`
- `/v1/dictionary/relation-types`
- `/v1/dictionary/relation-types/{relation_type_id}`
- `/v1/dictionary/relation-types/{relation_type_id}/review-status`
- `/v1/dictionary/relation-types/{relation_type_id}/revoke`
- `/v1/dictionary/relation-types/{relation_type_id}/merge`
- `/v1/dictionary/relation-synonyms`
- `/v1/dictionary/relation-synonyms/resolve`
- `/v1/dictionary/relation-synonyms/{synonym_id}/review-status`
- `/v1/dictionary/relation-synonyms/{synonym_id}/revoke`
- `/v1/dictionary/transforms`
- `/v1/dictionary/transforms/{transform_id}/verify`
- `/v1/dictionary/transforms/{transform_id}/promote`

The platform app no longer publishes graph routes under the
`/research-spaces/{space_id}/` prefix.

## Authoritative test surfaces

### Standalone service integration

- `tests/integration/graph_service/test_graph_api.py`

### Graph invariant matrix

- `tests/graph/README.md`

### Graph performance

- `tests/performance/test_graph_query_performance.py`
- `docs/graph/reference/read-model-benchmarks.md`

### Boundary enforcement

- `tests/unit/architecture/test_architectural_compliance.py`
- `scripts/validate_graph_service_boundary.py`

### Service-local tooling gates

- `tests/unit/services/graph_api/`
- `tests/unit/infrastructure/graph_service/`
- `tests/unit/scripts/test_export_graph_openapi.py`
- `tests/unit/scripts/test_generate_ts_types.py`

## Removed platform ownership

The platform research-spaces router no longer owns graph routes, and the old
graph route modules under `src/routes/research_spaces/` have been deleted.

The remaining platform responsibility is graph control-plane sync and
orchestration that call the standalone graph service over HTTP.
