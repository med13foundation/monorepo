# Graph API Service

This package is the beginning of the standalone graph service extraction.

Current scope:

- independent FastAPI app
- service-local config, database session, and auth helpers
- standalone graph-service authz now resolves space access through a graph-local space access port instead of the platform membership service
- graph-connection composition now resolves tenant settings through a graph-local space settings port instead of the platform `ResearchSpaceRepository`
- graph-owned runtime now resolves tenant metadata through a graph-local space registry adapter for owner checks, settings lookup, auto-promotion policy resolution, and global reasoning-path rebuild enumeration
- graph-owned tenant metadata now persists in a graph-owned `graph_spaces` table with standalone admin registry APIs
- graph-service authz now resolves non-owner members through graph-owned `graph_space_memberships` instead of the platform membership table
- graph-owned control-plane and governance tables can now live in a dedicated `GRAPH_DB_SCHEMA` instead of always living in `public`
- standalone admin APIs now support atomic graph-space sync, including full graph-owned membership snapshot replacement for a space
- platform space and membership application services now push graph tenant sync through a graph control-plane port instead of repeating route-level helper calls
- the platform now has a dedicated tenant reconciliation path under `scripts/sync_graph_spaces.py` and `make graph-space-sync` for rebuilding graph-space state from platform truth
- architecture validation now runs `scripts/validate_graph_service_boundary.py` so new direct imports of graph internals outside the standalone service fail unless they are in the explicit legacy allowlist
- graph control-plane APIs now require a graph-service-local admin claim instead of depending on the platform `UserRole.ADMIN` role
- standalone runtime now requires an explicit `GRAPH_DATABASE_URL` instead of inheriting the platform `DATABASE_URL` resolver contract
- standalone runtime now supports `GRAPH_DB_SCHEMA` so graph-owned control-plane and governance tables can run from a dedicated schema with a graph-aware Postgres `search_path`
- standalone runtime now uses graph-local DB pool settings under `GRAPH_DB_*` instead of the platform `MED13_DB_*` pool env contract
- service-local DB operations now exist under `python -m services.graph_api.manage` and back the dedicated `make graph-db-wait` / `make graph-db-migrate` commands
- service-local container packaging now exists under `services/graph_api/Dockerfile`
- service-local runtime dependencies now live in
  `services/graph_api/requirements.txt` so the graph container does not install
  the shared root package or Artana runtime
- entity similarity, embedding refresh, and relation suggestions no longer live
  in the graph service; those heuristic workflows belong in the harness layer
- graph-service Cloud Run runtime sync now exists under `scripts/deploy/sync_graph_cloud_run_runtime_config.sh`
- graph-service promotion now has a dedicated GitHub Actions workflow in `.github/workflows/graph-service-deploy.yml`
- service-local composition for graph, dictionary, and concept services
- service-local governance adapters/builders now expose shared dictionary and concept service composition under `services/graph_api/governance.py`
- `services/graph_api/dictionary_repository.py` and `services/graph_api/concept_repository.py` are compatibility re-exports over the shared graph-governance persistence layer
- service-local OpenAPI export now lives under `scripts/export_graph_openapi.py`, with the current artifact at `services/graph_api/openapi.json`
- service-local quality gates now run under `make graph-service-checks`
- graph-owned schema no longer carries foreign keys to platform `users` or `source_documents`
- graph view assembly now uses a graph-local source-document reference port instead of the platform document repository contract
- entity endpoints under `/v1/spaces/{space_id}/entities/...`
- observation endpoints under `/v1/spaces/{space_id}/observations/...`
- provenance endpoints under `/v1/spaces/{space_id}/provenance/...`
- deterministic graph read endpoints under `/v1/spaces/{space_id}/...`
- canonical relation create and curation-update endpoints under `/v1/spaces/{space_id}/relations/...`
- canonical graph export and unified graph document endpoints
- claim-ledger reads and claim-status mutation endpoints
- claim-relation write and review endpoints
- graph-view and mechanism-chain endpoints
- service-owned maintenance endpoints for participant backfill, projection readiness, projection repair, and reasoning-path rebuilds
- service-owned operation history endpoints under `/v1/admin/operations/runs` for readiness, repair, backfill, and rebuild workflows
- service-owned graph-space registry endpoints under `/v1/admin/spaces/...`
- service-owned graph-space sync endpoint under `/v1/admin/spaces/{space_id}/sync`
- service-owned graph-space membership endpoints under `/v1/admin/spaces/{space_id}/memberships/...`
- service-owned dictionary governance endpoints under `/v1/dictionary/...`, including revoke, merge, changelog, deterministic domain listing, and transform registry workflows
- service-owned concept governance endpoints under `/v1/spaces/{space_id}/concepts/...`
- service-owned hypothesis workflow endpoints under `/v1/spaces/{space_id}/hypotheses/...`
- first typed platform HTTP client under `src/infrastructure/graph_service/`, including graph-space registry and membership management
- platform space lifecycle and membership write routes now sync graph tenant state into the standalone service over HTTP after successful platform writes
- web entity, observation, provenance, and relation write helpers now target the standalone graph service for extracted endpoints
- operational readiness and reasoning-rebuild scripts now consume the graph service over HTTP
- pipeline orchestration graph-seed discovery now consumes graph-connection over the standalone graph-service HTTP client
- durable worker-side graph search and graph-connection flows now use service-to-service graph adapters over HTTP
- post-ingestion graph hooks and the minimal full-workflow script now use the standalone graph-service client for extracted graph operations
- runnable entrypoint at `services.graph_api.main:app`

Current non-goals:

- background rebuild jobs
- typed client cutover for non-graph callers

The service currently reuses the existing graph domain/application code from the
main repo while establishing a real HTTP boundary and service-local runtime.

Run locally with:

```bash
make graph-db-migrate
make run-graph-service
```

Quality/contract checks:

```bash
make graph-service-checks
```

Required runtime environment:

- `GRAPH_DATABASE_URL`
- optional `GRAPH_DB_SCHEMA`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- optional `GRAPH_DB_POOL_SIZE`
- optional `GRAPH_DB_MAX_OVERFLOW`
- optional `GRAPH_DB_POOL_TIMEOUT_SECONDS`
- optional `GRAPH_DB_POOL_RECYCLE_SECONDS`
- optional `GRAPH_DB_POOL_USE_LIFO`
- optional `GRAPH_DOMAIN_PACK`
- optional `GRAPH_SERVICE_HOST`
- optional `GRAPH_SERVICE_PORT`
- optional `GRAPH_SERVICE_RELOAD`

Pack lifecycle reference:

- `docs/graph/reference/domain-pack-lifecycle.md`
  Documents how built-in packs are registered at startup, how
  `GRAPH_DOMAIN_PACK` selects the active pack, and where runtime composition is
  expected to consume pack-owned extensions.

Deployment/runtime notes:

- Cloud Run packaging uses `services/graph_api/Dockerfile`
- the dedicated deploy workflow is `.github/workflows/graph-service-deploy.yml`
- platform API/admin deploys now inject graph-service URLs through
  `scripts/deploy/sync_cloud_run_runtime_config.sh` so extracted callers do not
  fall back to `localhost`
- runtime and operational scripts now require explicit `GRAPH_SERVICE_URL`
  outside local/test environments
- when `GRAPH_DB_SCHEMA` is set to a non-`public` value, graph-service runtime
  sessions and graph migrations target that schema for graph-owned
  control-plane and governance tables
- dedicated-schema Postgres validation now passes for the standalone graph gate
  with `GRAPH_DB_SCHEMA=graph_runtime`
- deploy/runtime sync fails fast if graph URLs, graph secrets, or the configured
  graph migration job are missing
- deployed graph runtime validation also rejects reuse of the platform
  `DATABASE_URL` secret name for `GRAPH_DATABASE_URL`
