# Kernel Graph Architecture

## Purpose

The kernel graph stores explainable, research-space-scoped knowledge.

Its implemented contract is:

```text
evidence -> claims -> projections -> canonical graph
```

Claims are the authoritative ledger.
Canonical relations are projections of resolved support claims.

## Core principles

1. All new knowledge enters the system as claims or observations.
2. Canonical `relations` are not an independent truth source.
3. Every canonical relation must be explainable by one or more support claims.
4. Canonical reads default to claim-backed projections only.
5. `relation_evidence` is a derived cache built from support-claim evidence.
6. `linked_relation_id` is a compatibility/read-model pointer, not authoritative lineage.

## Main graph stores

### Entities

`entities` are the canonical graph nodes.

They represent resolved subjects and objects such as genes, phenotypes,
variants, pathways, players, teams, or any other Dictionary-governed entity.

### Observations

`observations` are typed facts about entities.

They do not use the claim projection model. They are persisted through the
generic ingestion path after mapping, normalization, resolution, and validation.

### Relation claims

`relation_claims` are the authoritative relation ledger.

Each claim carries:

- relation triple intent
- polarity: `SUPPORT | REFUTE | UNCERTAIN | HYPOTHESIS`
- validation state
- persistability
- claim status
- optional `linked_relation_id` for navigation compatibility

### Claim participants

`claim_participants` are the authoritative structured endpoints for claim-based
relation logic.

Projection logic uses participants, not raw `metadata_payload`, to resolve the
subject and object entities for a claim.

### Claim evidence

`claim_evidence` is the authoritative evidence ledger for claims.

Each row stores the evidence sentence/span, source metadata, confidence, and
provenance context for one claim.

### Projection lineage

`relation_projection_sources` is the authoritative explainability table.

It links:

- one canonical relation
- to one source claim
- in one research space

This is the system of record for answering:

```text
Why does this canonical relation exist?
```

### Canonical relations

`relations` are the default read model for graph browsing, graph export,
subgraph assembly, neighborhood traversal, and graph search.

They exist only as claim-backed projections.

### Canonical relation evidence

`relation_evidence` is a derived cache.

It is rebuilt from support-claim evidence during projection materialization or
rebuild. It exists for read performance and response stability, not as an
independent truth store.

### Claim-to-claim relations

`claim_relations` model claim overlay topology such as contradiction,
refinement, mechanism, or support chains between claims.

They do not replace canonical `relations`; they enrich claim-space navigation.

## Write architecture

### Observation write path

Observation writes flow through the generic ingestion pipeline:

```text
map -> normalize -> resolve -> validate -> persist
```

### Relation write path

The implemented relation write path is claim-first.

1. Create or update a claim.
2. Create structured `claim_participants`.
3. Create `claim_evidence` if evidence is available.
4. If the claim is `SUPPORT + RESOLVED + PERSISTABLE`, materialize it through
   `KernelRelationProjectionMaterializationService`.
5. The materializer upserts or rebuilds the canonical relation.
6. The materializer writes or refreshes `relation_projection_sources`.
7. The materializer rebuilds derived `relation_evidence`.

## Materialization rules

Implemented rules:

1. Only `SUPPORT` claims can create or update canonical relations.
2. `REFUTE`, `UNCERTAIN`, and `HYPOTHESIS` claims never create canonical relations.
3. A support claim must have `SUBJECT` and `OBJECT` participants with entity anchors to materialize.
4. If a support claim becomes non-materializable, its projection lineage is detached and the affected canonical relation is rebuilt.
5. If a canonical relation loses all valid support sources, it is deleted.

## Read architecture

Canonical graph reads default to claim-backed relations only.

This includes:

- relation list/count
- graph export
- bounded subgraph
- neighborhood graph
- graph document assembly
- graph search
- graph query repository reads

Claim overlay and claim curation reads still operate directly on claims.

## Read-side domain views

The repo also exposes read-side graph views built from the same claim-first
stores.

These views do not create new truth tables. They assemble:

- one focal resource
- nearby canonical relations
- related claims
- claim-to-claim edges
- structured participants
- claim evidence

This is the intended way to support domain-specific UX such as:

- gene view
- variant view
- phenotype view
- paper view
- claim view

## Mechanism chains

Mechanistic reasoning is modeled as a claim-space traversal, not as a second
canonical graph.

The current implementation uses `claim_relations` for mechanism-style edges such
as:

- `CAUSES`
- `UPSTREAM_OF`
- `DOWNSTREAM_OF`
- `REFINES`
- `SUPPORTS`

This means mechanism exploration remains:

- claim-backed
- reviewable
- evidence-linked
- separate from canonical truth projection

## Main application services

### Canonical read and curation

- `KernelRelationService`
- `KernelRelationClaimService`
- `KernelRelationProjectionSourceService`
- `KernelClaimParticipantService`
- `KernelClaimEvidenceService`

### Canonical projection

- `KernelRelationProjectionMaterializationService`

This is the write owner for canonical relations.

### Projection invariants and rollout

- `KernelRelationProjectionInvariantService`
- `KernelClaimProjectionReadinessService`
- `KernelClaimParticipantBackfillService`

These services enforce:

- no orphan canonical relations
- no unexplained projections
- no active support claims missing structured endpoints
- no support projections missing usable claim evidence

## Operational guarantees

The implemented system enforces:

1. New canonical relations cannot survive without projection lineage.
2. Projection-lineage failure rolls back canonical relation writes.
3. Canonical graph responses are projection-backed by default.
4. Graph-document explainability prefers projection lineage over `linked_relation_id`.
5. Readiness can be checked globally through the operational script and `make graph-readiness`.

## Compatibility surfaces

These still exist intentionally:

### `linked_relation_id`

Kept for:

- UI navigation
- conflict views
- read-model convenience

Not used as authoritative lineage.

### `POST /relations`

Kept as an internal compatibility endpoint.

It is restricted to admin/system use and still creates a manual support claim
before materializing the canonical relation.

Public/manual creation is otherwise claim-first.
