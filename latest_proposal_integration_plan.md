# Migration / Integration Plan: MED13 Resource Library -> Universal Study Graph Kernel

This plan migrates the current MED13 Resource Library from hardcoded, domain-specific entities into a **metadata-driven kernel** (dictionary + entities + observations + relations) while keeping infrastructure (auth, DI, storage, Artana, CI/CD, Next.js) intact.

It also includes an explicit phase to unify terminology and naming to **`research_space`** everywhere (instead of `study`) to reduce confusion and avoid a permanent dual-language codebase.

## Current Repo State (Reality Check)

As of **2026-02-10**, the core kernel migration (Phases 0-3) is **COMPLETE**.

- **Schema:** Kernel tables (`entities`, `observations`, `relations`) + dictionary tables (`variable_definitions`, etc.) are deployed via `001_current_baseline.py`.
- **Services:** All kernel services (`kernel_entity_service.py`, `kernel_observation_service.py`, `kernel_relation_service.py`, `dictionary_service.py`) are implemented and active.
- **Ingestion:** The full "Map -> Normalize -> Resolve -> Validate" pipeline is implemented in `src/infrastructure/ingestion/`.
- **Legacy Cleanup:** All legacy domain entities (`gene.py`, `variant.py`, etc.) and their repositories/services have been **deleted**.
- **Renaming:** `research_space` is now the canonical term across DB and backend code.

Work is now focused on **Phase 4 (Routes)**, **Phase 5 (Frontend)**, and **Phase 6 (Final Verification)**.

## Guiding Principles

1. Clean-sheet database (safe because no production data)
2. Keep auth/middleware/DI patterns; rewire rather than rewrite
3. Replace domain facts layer (entities/observations/relations) with kernel tables + generic services
4. Refactor routes/services by adapting data shapes (avoid full rewrites)
5. Frontend adapts last; route URLs can remain stable while internal names change
6. Strict type safety remains mandatory (no `Any` in domain/application layers)

## Phase 0: Quality Gates + Type Safety (Week 0-1) — [COMPLETED]

**Goal:** Stabilize before accelerating. Keep MyPy strict green while pivoting.

Work:

- [x] Make `make type-check` pass (MyPy strict).
- [x] Remove `Any` from ingestion contracts and plugin interfaces by using existing JSON types:
  - Use `JSONValue` / `JSONObject` from `src/type_definitions/common.py`
  - For arrays: `list[JSONValue]` (not `list[Any]`)
- [x] Fix DI factory typing mismatches (ensure repositories implement their domain interfaces).
- [x] Add a small kernel smoke test suite early so we can delete legacy tests confidently later.

Deliverable:

- `make all` passes (format, lint, type-check, tests).

## Phase 1: Kernel Schema + Dictionary Seeds (Week 1-2) — [COMPLETED]

**Goal:** A working kernel schema plus seeded dictionary data.

Work:

1. Verify the kernel migration creates:
   - dictionary tables (`variable_definitions`, `variable_synonyms`, `transform_registry`, `entity_resolution_policies`, `relation_constraints`)
   - fact tables (`entities`, `entity_identifiers`, `observations`, `relations`, `provenance`)
   - workspace table (`research_spaces`) and memberships (`research_space_memberships`)
2. Seed the dictionary from `src/database/seeds/` using the seeder module.
3. Add minimum DB constraints required to keep kernel data safe:
   - observations: "exactly one value\_\* populated" (DB constraint or application validation; decide explicitly)
   - relations: uniqueness/duplicate policy (optional; decide based on use cases)

Deliverable:

- [x] `alembic upgrade head` creates kernel tables
- [x] dictionary seeding runs and populates expected rows

## Phase 1.5 (NEW): Rename Everything To `research_space` (Week 2) — [COMPLETED]

**Goal:** Eliminate long-term dual terminology (`study` vs `research_space`). After this phase:

- Database: canonical workspace table is `research_spaces`
- Code: canonical parameter/field is `research_space_id`
- URLs: can remain `/spaces/...` (recommended) or introduce `/research-spaces/...` alias; but internal names are unified

### 1.5.1 Database Renames

Because this is a clean-sheet database, the simplest path is:

- [x] Update the baseline migration to create **`research_spaces`** instead of `studies`.
- [x] Rename kernel membership table to **`research_space_memberships`**.
- [x] Rename all foreign keys/columns across kernel + infra tables:
  - `study_id` -> `research_space_id` in: `entities`, `observations`, `relations`, `provenance`, `user_data_sources`, `ingestion_jobs`, etc.
- [x] Update indexes to match renamed columns (e.g., `idx_entities_space_type`, `idx_obs_space_variable`).

Deliverable:

- Fresh DB created from the single migration contains no `studies` table and no `study_id` columns.

### 1.5.2 SQLAlchemy Model Renames

Work:

- [x] Replace `StudyModel` / `StudyMembershipModel` with `ResearchSpaceModel` / `ResearchSpaceMembershipModel` (kernel equivalents).
- [x] Update ORM relationships from `UserModel` to owned spaces + memberships.
- [x] Update all kernel models that reference `study_id` to use `research_space_id`.

Deliverable:

- ORM metadata matches DB schema; application starts and queries work.

### 1.5.3 Repository + Service API Renames

Work:

- [x] Rename repository/service method parameters:
  - `study_id` -> `research_space_id`
- [x] Ensure request context / auth scoping uses the renamed identifier everywhere.
- [x] Add a temporary compatibility layer only if needed:
  - accept `study_id` in some call sites but route it internally to `research_space_id`
  - remove compatibility once routes are migrated

Deliverable:

- No "study" naming remains in kernel APIs (except docs/history).

### 1.5.4 API + Frontend Consistency

Work:

- [x] Keep external URLs stable where possible:
  - recommend continuing with `/spaces/{spaceId}` in Next.js
  - backend path params can be named `{research_space_id}` even if the URL remains `/spaces/`
- [x] Update OpenAPI schema + TS types generation to reflect `research_space_id`.

Deliverable:

- Frontend builds and runs without needing a user-facing URL rename.

## Phase 2: Kernel Backend Services (Week 2-4) — [COMPLETED]

**Goal:** Generic CRUD and governance in the application layer.

Work:

- [x] Complete and harden:
  - `DictionaryService`
  - `KernelEntityService` (resolution-policy enforcement)
  - `KernelObservationService` (type/unit/constraint validation)
  - `KernelRelationService` (triple constraints + evidence requirements + curation workflow)
- [x] Ensure unit normalization is executed via the transform registry (no LLM codegen).
- [x] Ensure provenance is created for all ingestion writes.

Deliverable:

- We can create/search entities, record observations, create relations with constraint checks.

## Phase 3: Ingestion Pipeline Integration (Week 4-7) — [COMPLETED]

**Goal:** Map -> Normalize -> Resolve -> Validate pipeline writing kernel facts.

Work:

- [x] Implement a pipeline API that is safe and typed end-to-end.
- [x] Start with deterministic mapping (synonyms / exact match), ship it, then add:
  - vector search (pgvector) as a fast-follow
  - LLM "judge" only for ambiguous cases, with a "needs review" fallback path

### Type-Safe Plugin Contract (No `Any`)

Source plugins should return JSON using existing types (no `Any`):

```python
from typing import Protocol, TypedDict

from src.domain.entities.user_data_source import UserDataSource
from src.type_definitions.common import JSONObject


class KernelIngestorPlugin(Protocol):
    def ingest(self, source: UserDataSource) -> "IngestResult":
        ...


class IngestResult(TypedDict):
    raw_rows: list[JSONObject]
    suggested_mappings: dict[str, str]
    source_metadata: JSONObject
```

Deliverable:

- Ingest a small "clean" dataset into kernel tables with provenance + normalized units.

## Phase 4: Routes + API Adaptation (Week 7-9) — [~85% COMPLETE]

**Goal:** Replace entity-specific endpoints with generic kernel endpoints while keeping auth and route structure.

Work:

- [x] Introduce kernel endpoints:
  - dictionary (admin)
  - entities
  - observations
  - relations
  - provenance
- [x] Keep legacy endpoints temporarily only if needed for frontend transition.

Deliverable:

- The Next.js app can fetch "space-scoped" entities/observations/relations from kernel endpoints.

## Phase 5: Frontend Adaptation (Week 9-11) — [~60% COMPLETE]

**Goal:** Update API hooks + response types while keeping page structure.

Work:

- [x] Update hooks to use kernel endpoints and `research_space_id`.
- [ ] Add:
  - [x] dictionary management (admin)
  - [x] observations view
  - [x] ingestion page (upload + map preview + run)

Deliverable:

- Admin UI supports kernel workflows (dictionary editing + ingestion + curation).

## Phase 6: Cleanup + Verification (Week 11-12) — [~80% COMPLETE]

Work:

- [x] Delete legacy domain entities / services / repositories that are fully superseded.
- [ ] Rewrite tests to target kernel services + kernel routes.
- [ ] Manual verification smoke tests:
  - create space
  - add data source
  - ingest
  - see graph + curation updates

Deliverable:

- `make all` green
- end-to-end ingestion + curation workflows working on kernel tables

## Risks + Mitigations (Highlights)

| Risk                                            | Mitigation                                                                           |
| ----------------------------------------------- | ------------------------------------------------------------------------------------ |
| Terminology churn (`study` vs `research_space`) | **[RESOLVED]** Phase 1.5 executed early; enforced single canonical name in code + DB |
| Pipeline scope creep                            | **[MANAGED]** Shipped deterministic mapping first; vector/LLM are fast-follows       |
| Kernel EAV validation gaps                      | **[ADDRESSED]** Enforced via `KernelObservationService` application logic            |
| Type-safety regression during big refactor      | **[PREVENTED]** Phase 0 gate passed: MyPy strict + tests green before deleting       |
