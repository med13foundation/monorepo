# RFC: Claim Graph Overlay

**Status:** Draft
**Author:** MED13 Engineering
**Date:** 2026-03-04
**Scope:** Kernel schema evolution, extraction pipeline, search, curation UI

---

## 1. Problem Statement

The kernel knowledge graph stores scientific knowledge as binary edges:

```
Entity (source_id) --[relation_type]--> Entity (target_id)
```

This is enforced by the `uq_relations_canonical_edge` unique constraint on
`(source_id, relation_type, target_id, research_space_id)` in the `relations` table.

Scientific statements are rarely binary. A claim like *"Variant Thr326Ala in MED13
reduces FBW7 binding in human cells"* involves five entities (gene, variant, protein,
mechanism, model system), but the current schema can only capture one binary slice
per relation.

The `relation_claims` table (migrations 024, 029, 030) introduced a claim-first
curation ledger with polarity, evidence, and lifecycle tracking. This was the right
architectural bet. However, claims today have two structural limitations:

1. **They reference exactly two entities** via `source_label` / `target_label`
   string fields. Entity IDs are stored in `metadata_payload` JSONB, not as
   indexed foreign keys.

2. **They are isolated records** with no edges between them. Contradictions are
   detected at query time by grouping claims by canonical relation and comparing
   polarities. Mechanistic chains (claim A causes claim B) have no representation.

This RFC proposes two additive tables that promote claims from a curation ledger
to a traversable statement graph, without modifying any existing schema.

---

## 2. Current Architecture

### 2.1 What exists and stays unchanged

| Table | Purpose | Key fields |
|---|---|---|
| `entities` | Graph nodes | `id`, `entity_type`, `name`, `research_space_id` |
| `entity_identifiers` | PHI-isolated lookup keys | `entity_id`, `identifier_type`, `identifier_value` |
| `relations` | Canonical binary edges | `source_id`, `relation_type`, `target_id` |
| `relation_evidence` | Evidence per canonical edge | `relation_id`, `evidence_sentence`, `evidence_tier` |
| `relation_claims` | Extracted candidate triples | `source_label`, `target_label`, `polarity`, `claim_text` |
| `claim_evidence` | Evidence per claim | `claim_id`, `sentence`, `sentence_source`, `confidence` |
| `provenance` | Ingestion lineage | `source_type`, `source_ref`, `extraction_run_id` |

### 2.2 How claims are created today

The extraction write flow in `_extraction_relation_candidate_write_flow.py`
creates claims via `KernelRelationClaimRepository.create()`:

```python
created_claim = context.helper._relation_claims.create(
    research_space_id=context.research_space_id,
    source_document_id=str(context.document.id),
    agent_run_id=context.run_id,
    source_type=candidate.source_type,       # e.g. "GENE"
    relation_type=candidate.relation_type,   # e.g. "ASSOCIATED_WITH"
    target_type=candidate.target_type,       # e.g. "PHENOTYPE"
    source_label=candidate.source_label,     # string, e.g. "MED13"
    target_label=candidate.target_label,     # string, e.g. "FBW7"
    confidence=candidate.confidence,
    validation_state=candidate.validation_state,
    persistability=candidate.persistability,
    polarity=candidate.polarity,
    claim_text=candidate.claim_text,
    linked_relation_id=None,
    metadata=payload,
)
```

Entity IDs, when known, are written to `metadata_payload` JSONB:

```python
if candidate.source_entity_id is not None:
    payload["source_entity_id"] = candidate.source_entity_id
if candidate.target_entity_id is not None:
    payload["target_entity_id"] = candidate.target_entity_id
```

### 2.3 How contradictions are detected today

`KernelRelationClaimRepository.find_conflicts_by_research_space()` loads all
non-rejected claims with `linked_relation_id IS NOT NULL`, groups them by
canonical relation, and intersects the SUPPORT and REFUTE sets in memory.
This only detects conflicts between claims already resolved to the same
canonical edge. Unresolved claim-to-claim contradictions are invisible.

### 2.4 How hypothesis claims are created

`HypothesisGenerationService.generate_hypotheses()` runs the Graph Connection
agent per seed entity, collects `ProposedRelation` candidates (binary:
`source_id`, `relation_type`, `target_id`), and persists them as claims with
`polarity="HYPOTHESIS"`.

Manual hypotheses (via `POST /{space_id}/hypotheses/manual`) store free-text
statements as claims with `source_type="HYPOTHESIS"`, `relation_type="PROPOSES"`,
`target_type="HYPOTHESIS"`, and `seed_entity_ids` in metadata.

---

## 3. Proposed Schema Changes

Two new tables. No modifications to existing tables.

### 3.1 `claim_participants`

Links claims to entities with semantic roles. Replaces the implicit binary
`source_label` / `target_label` pair with an N-ary, indexed, FK-backed model.

```sql
CREATE TABLE claim_participants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id        UUID NOT NULL REFERENCES relation_claims(id) ON DELETE CASCADE,
    research_space_id UUID NOT NULL REFERENCES research_spaces(id) ON DELETE CASCADE,

    -- Entity reference: label-first, ID-later (matches extraction flow)
    label           VARCHAR(512) NOT NULL,
    entity_id       UUID REFERENCES entities(id) ON DELETE SET NULL,

    -- Semantic role in the statement (not entity type — entity already carries that)
    role            VARCHAR(32) NOT NULL,
    position        SMALLINT,

    -- Optional qualifiers (residue, dosage, tissue, cell line, timepoint)
    qualifiers      JSONB NOT NULL DEFAULT '{}',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_participant_role CHECK (
        role IN ('SUBJECT', 'OBJECT', 'CONTEXT', 'QUALIFIER', 'MODIFIER')
    )
);
```

**Design decisions:**

- **`label` is NOT NULL, `entity_id` is nullable.** Claims arrive with labels
  from extraction. Entity resolution populates `entity_id` later. This matches
  the existing two-stage flow where `metadata_payload` carries optional entity
  IDs.

- **`role` is a small structural enum, not entity types.** The entity's type
  (GENE, VARIANT, PROTEIN) is already stored on the `entities` table via
  `entity_type` FK to `dictionary_entity_types`. Duplicating it here would
  couple the participant table to the biomedical domain. The five structural
  roles describe the entity's function *within the statement*:
  - `SUBJECT` — the entity being described or acting
  - `OBJECT` — the entity affected or targeted
  - `CONTEXT` — experimental context (species, tissue, cell line, method)
  - `QUALIFIER` — modifying detail (dosage, residue, timepoint, allele)
  - `MODIFIER` — additional entity that refines the claim semantics

- **`qualifiers` JSONB** stores domain-specific detail (residue position, allele,
  concentration) without requiring schema changes per domain. Keeps the table
  domain-agnostic.

- **`research_space_id`** is denormalized from the parent claim for RLS policy
  enforcement without requiring a join.

**Indexes:**

```sql
CREATE INDEX idx_cp_claim       ON claim_participants(claim_id);
CREATE INDEX idx_cp_entity      ON claim_participants(entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX idx_cp_space_entity ON claim_participants(research_space_id, entity_id)
    WHERE entity_id IS NOT NULL;
CREATE INDEX idx_cp_space_role  ON claim_participants(research_space_id, role);
```

### 3.2 `claim_relations`

Directed edges between claims. Enables stored contradictions, mechanistic
chains, and support/refinement links.

```sql
CREATE TABLE claim_relations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_space_id UUID NOT NULL REFERENCES research_spaces(id) ON DELETE CASCADE,
    source_claim_id   UUID NOT NULL REFERENCES relation_claims(id) ON DELETE CASCADE,
    target_claim_id   UUID NOT NULL REFERENCES relation_claims(id) ON DELETE CASCADE,

    relation_type     VARCHAR(32) NOT NULL,
    confidence        FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- Provenance
    created_by        VARCHAR(255),  -- user UUID or agent run ID
    evidence_summary  TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_claim_rel_type CHECK (
        relation_type IN (
            'SUPPORTS', 'CONTRADICTS', 'REFINES',
            'CAUSES', 'UPSTREAM_OF', 'DOWNSTREAM_OF',
            'SAME_AS', 'GENERALIZES', 'INSTANCE_OF'
        )
    ),
    CONSTRAINT ck_claim_rel_no_self_loop CHECK (source_claim_id != target_claim_id)
);
```

**Design decisions:**

- **Relation types are a fixed CHECK constraint for V1**, not Dictionary-backed.
  The set is small and stable. Dictionary governance can be added later if the
  set grows beyond these nine types.

- **`research_space_id`** is denormalized for RLS, consistent with
  `claim_participants`.

- **No unique constraint on `(source_claim_id, relation_type, target_claim_id)`.**
  Multiple agents or curators may independently propose the same link. Deduplication
  is an application-layer concern.

**Indexes:**

```sql
CREATE INDEX idx_cr_source  ON claim_relations(source_claim_id);
CREATE INDEX idx_cr_target  ON claim_relations(target_claim_id);
CREATE INDEX idx_cr_space   ON claim_relations(research_space_id);
CREATE INDEX idx_cr_type    ON claim_relations(relation_type);
```

### 3.3 RLS Policies

Both tables follow the established pattern from migration `030_claim_evidence_table`:

```sql
ALTER TABLE "claim_participants" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "claim_participants" FORCE ROW LEVEL SECURITY;

CREATE POLICY rls_claim_participants_access ON claim_participants
    USING (
        COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)
        OR COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)
        OR (
            NULLIF(current_setting('app.current_user_id', true), '') IS NOT NULL
            AND research_space_id IN (
                SELECT rsm.research_space_id
                FROM research_space_memberships rsm
                WHERE rsm.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                UNION
                SELECT rs.id
                FROM research_spaces rs
                WHERE rs.owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
            )
        )
    )
    WITH CHECK (/* same expression */);
```

Same policy for `claim_relations`.

---

## 4. Domain Model Changes

### 4.1 New domain entities

```
src/domain/entities/kernel/claim_participant.py
src/domain/entities/kernel/claim_relation.py
```

Pydantic models following the `KernelClaimEvidence` pattern (frozen, `from_attributes`).

### 4.2 New repository interfaces

```
src/domain/repositories/kernel/claim_participant_repository.py
src/domain/repositories/kernel/claim_relation_repository.py
```

ABC classes following the `KernelRelationClaimRepository` pattern.

### 4.3 New SQLAlchemy models

```
src/models/database/kernel/claim_participants.py
src/models/database/kernel/claim_relations.py
```

### 4.4 Extraction contract update

`ExtractedRelation` in `src/domain/agents/contracts/extraction.py` gains an
optional participants field:

```python
class ExtractedParticipant(BaseModel):
    label: str = Field(..., min_length=1, max_length=512)
    role: Literal["SUBJECT", "OBJECT", "CONTEXT", "QUALIFIER", "MODIFIER"]
    qualifiers: JSONObject = Field(default_factory=dict)

class ExtractedRelation(BaseModel):
    # ... existing fields unchanged ...
    participants: list[ExtractedParticipant] = Field(default_factory=list)
```

The field defaults to an empty list, so existing extraction prompts that do not
emit participants continue to work without breaking the contract.

---

## 5. Traversal Patterns Unlocked

### 5.1 Entity to claims (structured search)

```sql
SELECT rc.*, ce.sentence, ce.confidence AS evidence_confidence
FROM claim_participants cp
JOIN relation_claims rc ON rc.id = cp.claim_id
LEFT JOIN claim_evidence ce ON ce.claim_id = rc.id
WHERE cp.entity_id = :entity_id
  AND cp.research_space_id = :space_id
ORDER BY rc.confidence DESC, rc.created_at DESC;
```

Replaces the current approach of scanning `source_label` / `target_label` strings
or parsing `metadata_payload` JSONB for entity IDs.

### 5.2 Entity co-occurrence within a single claim

```sql
SELECT rc.*
FROM relation_claims rc
WHERE rc.id IN (
    SELECT cp1.claim_id
    FROM claim_participants cp1
    JOIN claim_participants cp2 ON cp1.claim_id = cp2.claim_id
    WHERE cp1.entity_id = :entity_a
      AND cp2.entity_id = :entity_b
      AND cp1.research_space_id = :space_id
);
```

### 5.3 Claim chain traversal (mechanism paths)

```sql
WITH RECURSIVE chain AS (
    SELECT cr.target_claim_id AS claim_id, 1 AS depth,
           ARRAY[cr.source_claim_id] AS path
    FROM claim_relations cr
    JOIN claim_participants cp ON cp.claim_id = cr.source_claim_id
    WHERE cp.entity_id = :start_entity_id
      AND cr.relation_type IN ('CAUSES', 'UPSTREAM_OF')
      AND cr.research_space_id = :space_id

    UNION ALL

    SELECT cr.target_claim_id, chain.depth + 1,
           chain.path || cr.source_claim_id
    FROM claim_relations cr
    JOIN chain ON chain.claim_id = cr.source_claim_id
    WHERE chain.depth < :max_depth
      AND NOT cr.target_claim_id = ANY(chain.path)
)
SELECT rc.*, chain.depth, chain.path
FROM chain
JOIN relation_claims rc ON rc.id = chain.claim_id;
```

Available in Phase 2 after `claim_relations` is populated.

---

## 6. Implementation Phases

### Phase 1 — Claim participants (weeks 1-3)

**Goal:** Make claims N-ary and traversable by entity.

| Task | Layer | Effort |
|---|---|---|
| Alembic migration `032_claim_participants` | Infrastructure | S |
| `KernelClaimParticipant` Pydantic entity | Domain | S |
| `ClaimParticipantModel` SQLAlchemy model | Infrastructure | S |
| `ClaimParticipantRepository` interface + implementation | Domain / Infra | M |
| Backfill: extract SUBJECT/OBJECT from existing `source_label`/`target_label` and `metadata_payload` entity IDs | Infrastructure | M |
| Add `participants` field to `ExtractedRelation` contract | Domain | S |
| Update `_create_relation_claim` to write participant rows | Application | M |
| Update manual hypothesis route to write `seed_entity_ids` as participants | Application | S |
| `GET /{space_id}/claims/by-entity/{entity_id}` route | Presentation | M |
| Unit + integration tests | Tests | M |

**Backfill details:** For each existing claim:
- Create one SUBJECT participant from `source_label` (+ `source_entity_id` from
  `metadata_payload` if present)
- Create one OBJECT participant from `target_label` (+ `target_entity_id` from
  `metadata_payload` if present)

This yields 2 participants per existing claim. Richer N-ary data arrives only
from new extractions with updated prompts.

**Quick win:** Manual hypotheses already carry `seed_entity_ids`. Writing these
as SUBJECT participants in Phase 1 proves the model end-to-end with zero prompt
changes.

### Phase 2 — Claim relations (weeks 4-5)

**Goal:** Enable stored contradictions and mechanistic chains.

| Task | Layer | Effort |
|---|---|---|
| Alembic migration `033_claim_relations` | Infrastructure | S |
| `KernelClaimRelation` Pydantic entity | Domain | S |
| `ClaimRelationModel` SQLAlchemy model | Infrastructure | S |
| `ClaimRelationRepository` interface + implementation | Domain / Infra | M |
| Manual linking UI: curator draws SUPPORTS/CONTRADICTS/CAUSES edges between claims | Presentation | L |
| Replace computed conflict detection with stored CONTRADICTS edges (optional) | Application | M |
| Unit + integration tests | Tests | M |

**Population strategy for `claim_relations`:**
1. **Manual curation (Phase 2):** Curators create edges in the curation UI
2. **Post-extraction linker agent (Phase 3+):** Background service proposes
   claim-to-claim links for curator review
3. **Context-aware extraction (future):** Extraction agent receives recent
   claims as context and emits links directly

### Phase 3 — Extraction prompt enrichment (weeks 5-7)

**Goal:** Extraction agent emits N-ary participant data.

This is the **critical path item** and the highest-risk phase. Extraction prompt
changes require iteration to ensure:
- The LLM reliably emits structured participant data
- Existing extraction quality does not regress
- Participants are correctly typed by semantic role

| Task | Layer | Effort |
|---|---|---|
| Update ClinVar extraction prompt to emit participants | Infrastructure (LLM) | L |
| Update PubMed extraction prompt to emit participants | Infrastructure (LLM) | L |
| Validation: participant role + label parsing in write flow | Application | M |
| Regression testing against existing extraction benchmarks | Tests | L |

**Start small:** Begin with VARIANT and CONTEXT participants (the two most
commonly lost entities in binary extraction). Expand to QUALIFIER/MODIFIER after
validating quality.

### Phase 4 — Search and UI integration (weeks 7-9)

**Goal:** Entity-first, claim-first search experience in the curation UI.

| Task | Layer | Effort |
|---|---|---|
| "Claims mentioning this entity" panel in existing curation page | Presentation | M |
| Entity co-occurrence search (entity A + entity B → claims) | Application + Presentation | M |
| Edge drill-down: click canonical edge → see supporting claims with participants | Presentation | M |
| Claim chain visualization (when `claim_relations` edges exist) | Presentation | L |

Integrates into the existing curation route at
`src/web/app/(dashboard)/spaces/[spaceId]/curation/` and the existing graph
search endpoint at `POST /{space_id}/graph/search`.

---

## 7. What This Does NOT Change

- **Canonical relations remain the "current belief state."** The `relations`
  table with its binary `(source_id, relation_type, target_id)` structure stays
  intact. It serves fast traversal, simple graph visualization, and the
  materialized consensus view.

- **The claim → canonical relation flow is unchanged.** `linked_relation_id`
  continues to link resolved claims to canonical edges.

- **Evidence tables are unchanged.** `claim_evidence` and `relation_evidence`
  already handle provenance well.

- **The Graph Connection agent stays binary.** It proposes entity-to-entity
  relations, not claim-level structure. Participants are added at the claim
  layer by the extraction pipeline.

The design principle: **claims are the truth layer; canonical relations are
the convenience layer.** Claims are many, contradictory, contextual, and
evidence-heavy. Canonical relations are fewer, curated, and optimized for
fast traversal.

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Extraction prompts fail to produce reliable participant data | Search quality depends on participant completeness | Phase 3 starts with two roles only (VARIANT, CONTEXT); quality gate before expanding |
| Backfill yields only 2 participants per existing claim | N-ary benefits delayed for historical data | Acceptable: backfill unlocks entity→claims traversal immediately; richer data arrives from new extractions |
| `claim_relations` stays empty without a linker agent | Mechanism search is unavailable | Manual curation covers V1; linker agent is Phase 3+ |
| Performance of multi-hop joins on large claim sets | Slow queries on active research spaces | Composite indexes on `(research_space_id, entity_id)` and `(claim_id)`; pagination in all query paths |
| Role enum is too coarse for specialized domains | Biomedical users want VARIANT, PHENOTYPE as roles | Entity type (from Dictionary) is already on the entity; roles can be refined via `qualifiers` JSONB or future Dictionary governance |

---

## 9. Success Criteria

**Phase 1 complete when:**
- `claim_participants` table exists with RLS
- Existing claims backfilled with SUBJECT/OBJECT participants
- New extraction claims write participant rows
- `GET /{space_id}/claims/by-entity/{entity_id}` returns claims with participants

**Phase 2 complete when:**
- `claim_relations` table exists with RLS
- Curators can create SUPPORTS/CONTRADICTS/CAUSES edges in the UI
- Contradiction detection optionally reads from stored edges

**Phase 3 complete when:**
- Extraction prompts for ClinVar and PubMed emit VARIANT and CONTEXT participants
- Participant extraction does not regress relation extraction quality (measured
  against existing test fixtures)

**Phase 4 complete when:**
- Curation UI shows "claims mentioning entity" panel
- Entity co-occurrence search works
- Edge drill-down shows supporting claims with participant detail
