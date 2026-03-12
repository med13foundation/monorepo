# Graph Examples

## 1. Support claim materializes a canonical relation

### Claim-side state

```text
Claim:
  polarity=SUPPORT
  claim_status=RESOLVED
  persistability=PERSISTABLE

Participants:
  SUBJECT -> MED13
  OBJECT  -> Cardiomyopathy

Evidence:
  "MED13 variants were associated with cardiomyopathy."
```

### Materialized result

```text
relation_claims
  -> source claim row

relation_projection_sources
  -> relation_id = rel-123
  -> claim_id = claim-456

relations
  -> rel-123
  -> source = MED13
  -> type = ASSOCIATED_WITH
  -> target = Cardiomyopathy

relation_evidence
  -> derived from claim_evidence for claim-456
```

## 2. Refute claim stays claim-only

```text
Claim:
  polarity=REFUTE
  claim_status=RESOLVED
  persistability=PERSISTABLE
```

Allowed behavior:

- may link to an existing canonical relation through `linked_relation_id`
- does not create `relation_projection_sources`
- does not create a canonical relation

## 3. Graph-document edge metadata

A canonical graph-document edge can expose both authoritative and compatibility
claim references.

Example shape:

```json
{
  "kind": "CANONICAL_RELATION",
  "canonical_relation_id": "rel-123",
  "metadata": {
    "support_claim_count": 1,
    "refute_claim_count": 1,
    "projection_claim_ids": ["claim-support-1"],
    "linked_claim_ids": ["claim-support-1", "claim-refute-9"],
    "explainable_by_projection": true
  }
}
```

Interpretation:

- `projection_claim_ids` are the authoritative explainability set
- `linked_claim_ids` are broader UI/navigation context

## 4. Internal compatibility relation creation

`POST /relations` is still implemented, but the route is internal-only.

Behavior:

1. create a manual support claim
2. create structured participants
3. create claim evidence if provided
4. materialize through the projection service

This preserves the claim-first contract even for compatibility workflows.

## 5. Readiness output

Example clean result:

```text
ready=True
orphan_relations=0
missing_claim_participants=0
missing_claim_evidence=0
linked_relation_mismatches=0
invalid_projection_relations=0
```

Example unresolved interpretation:

- `orphan_relations > 0`
  canonical graph contains unexplained edges
- `missing_claim_participants > 0`
  support claims cannot be projected safely
- `missing_claim_evidence > 0`
  support projections cannot be explained fully
- `linked_relation_mismatches > 0`
  compatibility pointers drifted from authoritative lineage
- `invalid_projection_relations > 0`
  canonical relations have projection rows but no valid support source

## 6. Mechanism chain example

```text
Claim A: MED13 mutation disrupts mediator complex function
   CAUSES
Claim B: Mediator complex dysfunction perturbs transcription
   UPSTREAM_OF
Claim C: Transcription dysregulation contributes to neurodevelopmental disease
```

Mechanism-chain response includes:

- root claim
- traversed claims
- mechanism-style claim edges
- participants
- evidence
- any linked canonical relations already materialized from support claims

## 7. Gene view example

Example request:

```text
GET /research-spaces/{space_id}/graph/views/gene/{entity_id}
```

Typical response contents:

- focal `GENE` entity
- canonical relations touching that gene
- claims mentioning the gene through `claim_participants`
- claim-to-claim edges for overlay and mechanism context
- claim evidence rows for those claims

## 8. Paper view example

Example request:

```text
GET /research-spaces/{space_id}/graph/views/paper/{source_document_id}
```

Typical response contents:

- focal source document
- claims extracted from that paper
- structured participants for those claims
- claim evidence rows from that paper
- any claim-backed canonical relations materialized from those claims
