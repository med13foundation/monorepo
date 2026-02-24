# Engineering Specification

# Multi-Paper Knowledge Ingestion + Ontology Governance System (Artana)

Audience: Backend + AI engineers
Goal: Build a scalable, ontology-governed, multi-paper knowledge graph ingestion system
Architecture Model: Dictionary / Kernel Graph / Operational Tables
Runtime: Artana Kernel + deterministic application persistence

Decision lock:

- Legacy runtime is fully removed (no backward compatibility layer).
- Runtime configuration source is `artana.toml` only.
- Artana dependency source:
  - `artana @ git+https://github.com/aandresalvarez/artana-kernel.git@main`
- Production replay mode is `strict` globally.
- Paper search/query AI is also migrated to Artana (no legacy query pipeline retained).

---

# 1. What We Are Building

We are building a semantic ingestion platform that:

1. Processes many scientific papers.
2. Extracts structured biomedical claims.
3. Normalizes entities and relations through controlled ontology rules.
4. Stores canonical knowledge in a graph.
5. Tracks provenance and audit trail.
6. Evolves ontology safely over time.

Paper ingestion is atomic and replay-safe per document.
Ontology governance is long-lived and version-controlled.

---

# 2. High-Level Architecture

```text
Paper -> Extraction Engine -> Ontology Validation -> Deterministic Persistence -> Audit/Review
```

System layers:

| Layer | Responsibility |
| --- | --- |
| Dictionary | Canonical entity/relation taxonomy + constraints + versions |
| Kernel Graph | Canonical persisted entities/relations/evidence/provenance |
| Operational | Ingestion jobs, review queue, governance/audit history |

---

# 3. Components to Build

## A0. Paper Search AI (Discovery/Query Generation)

This migration includes the paper-search AI path, not only extraction.

Scope:

1. Query generation for PubMed/ClinVar runs on Artana.
2. Query review/normalization runs on Artana.
3. Search result filtering and selection remain deterministic application logic.
4. Search-stage outputs are persisted with run/step traceability and replay safety.

Requirements:

- No legacy runtime calls in query generation path.
- Deterministic `step_key` convention for search stages.
- Search AI outputs recorded under same audit/replay model as extraction.

## A. Extraction Engine (Paper-Level, Artana Workflow)

Per paper:

1. Extract pass (LLM)
2. Review/synthesis pass (LLM)
3. Local normalization pass (deterministic)
4. Structured contract emission

Output contract:

```json
{
  "entities": {},
  "fact_edges": [["src", "relation", "dst"]],
  "derived_edges": [],
  "contradicted_edges": [],
  "hypothesis_only": []
}
```

Requirements:

- Idempotent.
- Deterministic `run_id`.
- Replay-safe.
- Must not write dictionary directly.
- Must call ontology validation before graph writes.

## B. Ontology Manager (Dictionary Layer)

Responsibilities:

1. Validate relation labels.
2. Normalize aliases/synonyms.
3. Map relation labels to canonical relation types.
4. Evaluate relation constraints for `(source_type, relation_type, target_type)`.
5. Emit governance proposals for unknown patterns.
6. Maintain dictionary version history.

### Validation Contract (No Side Effects)

`POST /ontology/validate_relation`

Input:

```json
{
  "research_space_id": "uuid",
  "src_type": "GENE",
  "relation_label": "ACTIVATION",
  "dst_type": "PATHWAY",
  "context": "optional evidence"
}
```

Output:

```json
{
  "validation_state": "ALLOWED",
  "canonical_relation_type_id": "ACTIVATES",
  "mapped_from_label": "ACTIVATION",
  "constraint_id": "GENE:ACTIVATES:PATHWAY",
  "dictionary_version": 42,
  "reason": "matched canonical relation and active allowed constraint"
}
```

Validation states:

- `ALLOWED`: persist.
- `FORBIDDEN`: reject with explicit reason.
- `UNDEFINED`: do not reject silently; persist as pending review and enqueue governance.

### Proposal Contract (Controlled Mutation)

`POST /ontology/propose_relation_constraint`

Purpose:

- Create proposal records only.
- Never auto-activate constraints in validation path.

---

# 4. Database Model

All tables below must include:

- `research_space_id` (or `tenant_id`) for isolation.
- timestamps (`created_at`, optional `updated_at`).

## A. Dictionary Tables

### `dictionary_entity_types`

- `id` (canonical key, e.g. `GENE`)
- `display_name`
- `is_active`
- `version_introduced`

Unique:

- `(research_space_id, id)`

### `dictionary_relation_types`

- `id` (canonical key, e.g. `ACTIVATES`)
- `display_name`
- `relation_category` (`FACT | DERIVED | HYPOTHESIS`)
- `is_active`
- `version_introduced`

Unique:

- `(research_space_id, id)`

### `dictionary_relation_constraints`

- `id` (or computed key)
- `source_type`
- `relation_type`
- `target_type`
- `is_allowed`
- `requires_evidence`
- `status` (`ACTIVE | PENDING_REVIEW | REJECTED`)
- `version_introduced`

Unique:

- `(research_space_id, source_type, relation_type, target_type)`

### `relation_aliases`

- `alias_label`
- `canonical_relation_type`
- `confidence`
- `status` (`ACTIVE | PENDING_REVIEW`)

Unique:

- `(research_space_id, alias_label)`

### `dictionary_versions`

- `version_number`
- `change_summary`
- `created_by`

Unique:

- `(research_space_id, version_number)`

### `dictionary_change_log`

- `version_number`
- `change_type`
- `target_table`
- `target_key`
- `before_json`
- `after_json`

## B. Kernel Graph Tables

### `entities`

- `id` (UUID)
- `canonical_name`
- `entity_type_id`

Unique:

- `(research_space_id, canonical_name, entity_type_id)`

### `entity_identifiers`

- `entity_id`
- `identifier_type`
- `identifier_value`

Unique:

- `(research_space_id, identifier_type, identifier_value)`

### `relations`

- `id` (UUID)
- `src_entity_id`
- `dst_entity_id`
- `relation_type_id`
- `confidence`
- `derived_flag`
- `status` (`ACTIVE | PENDING_REVIEW`)

Unique:

- `(research_space_id, src_entity_id, relation_type_id, dst_entity_id, derived_flag, status)`

### `relation_evidence`

- `relation_id`
- `snippet`
- `confidence`
- `extraction_model`
- `ingestion_job_id`

### `provenance`

- `relation_id`
- `source_document_id`
- `extraction_run_id`
- `dictionary_version_used`

## C. Operational Tables

### `source_documents`

- `id`
- `source_type` (`PUBMED`, `CLINVAR`, etc.)
- `external_id` (e.g. PMID, ClinVar ID)
- `fetch_uri`
- `checksum`
- `ingestion_status`

Unique:

- `(research_space_id, source_type, external_id)`

### `ingestion_jobs`

- `id`
- `source_document_id`
- `run_id`
- `extraction_model`
- `review_model`
- `dictionary_version_used`
- `replay_policy`
- `status`
- `start_time`
- `end_time`

Unique:

- `(research_space_id, run_id)`

### `review_queue`

- `id`
- `entity_type`
- `entity_id`
- `reason`
- `priority`
- `status`
- `assigned_to`
- `sla_due_at`

### `audit_log`

- `actor`
- `action_type`
- `target_table`
- `target_id`
- `metadata_json`
- `timestamp`

---

# 5. Deterministic Graph Insertion Pipeline

For each predicted edge:

1. Upsert source entity.
2. Upsert target entity.
3. Validate relation via ontology (pure read path).
4. If `ALLOWED`: insert relation + evidence + provenance in one transaction.
5. If `FORBIDDEN`: record rejection with explicit reason.
6. If `UNDEFINED`: insert `PENDING_REVIEW` relation/proposal and enqueue review.

Rules:

- LLM never writes graph tables directly.
- LLM never writes active dictionary constraints directly.
- Every persisted relation has provenance and dictionary version.
- No silent drops.

---

# 6. Artana Runtime Invariants (Required)

## Run Identity

- Deterministic `run_id` per paper:
- `hash(research_space_id, source_type, external_id, extraction_config_version)`

## Step Keys

Use deterministic `step_key`s, for example:

- `paper.extract.chunk.<n>`
- `paper.review.chunk.<n>`
- `paper.normalize.entities`
- `paper.validate.edge.<edge_hash>`
- `paper.persist.edge.<edge_hash>`

Never reuse a `step_key` for different logic.

## Replay Policy

- Production and staging: `strict` globally.
- Development defaults to `strict` as well.
- `allow_prompt_drift` is allowed only when explicitly set for local experiments.
- `fork_on_drift` is allowed only for controlled experiment runs.

## Middleware/Policy Baseline

- `PIIScrubberMiddleware`
- `QuotaMiddleware`
- `CapabilityGuardMiddleware`
- Tool input/output hooks enabled for policy checks

## Tenant Isolation

- Every Artana call must carry tenant/research-space context.
- No cross-space reads or writes in ingestion path.

---

# 7. Governance Rules

- Constraint creation is proposal-based by default.
- Auto-activation allowed only if policy thresholds are met (confidence, recurrence, allowed source patterns).
- All dictionary changes must:
- increment dictionary version,
- write immutable change log entries,
- emit audit log records.

---

# 8. End-to-End Flow

```text
for each paper:
  1. create ingestion_job
  2. run extraction workflow (Artana)
  3. normalize entities (deterministic)
  4. for each relation:
       validate via ontology
       branch on ALLOWED/FORBIDDEN/UNDEFINED
  5. persist outputs transactionally
  6. enqueue pending-review items where needed
  7. mark ingestion_job complete/failed
```

---

# 9. Scaling Strategy

- Extraction is stateless and parallelizable by paper.
- Ontology activation writes are serialized per research space/version.
- Graph insertion is transactional and idempotent.
- Operational logs and review queue are append-oriented.

---

# 10. Non-Goals

Do not:

- Hardcode relation sets in extraction logic.
- Allow direct LLM writes to dictionary active constraints.
- Use long-running debate-style harnesses for single-paper ingestion.
- Mix governance mutation with extraction pipeline execution path.

---

# 11. Implementation Phases

## Phase 1 (Foundational, must be internally complete)

- Introduce `artana.toml` and remove legacy config/runtime references.
- Replace legacy runtime dependency with Artana dependency source in project config.
- Migrate paper search/query-generation AI path to Artana.
- Artana paper ingestion workflow (extract/review/normalize).
- Ontology `validate_relation` API (pure read path).
- Dictionary tables: relation types + constraints + versions.
- Graph + operational tables with research-space scoping.
- Tri-state relation handling (`ALLOWED|FORBIDDEN|UNDEFINED`).
- Deterministic insertion and rejection/proposal logging.

## Phase 2 (Governance hardening)

- `propose_relation_constraint` endpoint and review queue integration.
- Alias management and canonical mapping workflows.
- Automated version/change-log tooling and approval flow.

## Phase 3 (Advanced operations)

- Governance dashboards and SLA reporting.
- Cross-paper contradiction and drift analytics.
- Confidence calibration across corpus.

---

# 12. Acceptance Criteria

System is production-ready when:

- Paper search/query AI runs fully on Artana with deterministic replay-safe tracing.
- Same paper with same dictionary version run twice yields identical persisted graph outputs.
- Every ingestion job records dictionary version used.
- No duplicate active relations under retries/parallel execution.
- Unknown relations are never silently discarded.
- Rejections always include explicit machine-readable reasons.
- Review queue receives all `UNDEFINED` outcomes.
- Replay behavior does not corrupt graph state.

---

# 13. Developer Mental Model

- Extraction = parser
- Ontology = type checker + policy engine
- Graph = compiled canonical knowledge
- Operational layer = build logs + review/audit ledger
