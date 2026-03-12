# Graph Endpoints

All routes below are research-space scoped unless noted otherwise.

Base prefix:

```text
/research-spaces/{space_id}
```

## Entities

### `GET /entities`

List kernel entities.

### `POST /entities`

Create or resolve a kernel entity.

### `GET /entities/{entity_id}`

Get one entity.

### `PATCH /entities/{entity_id}`

Update one entity.

### `DELETE /entities/{entity_id}`

Delete one entity.

### `GET /entities/{entity_id}/similar`

Find similar entities using hybrid graph and embeddings.

### `POST /entities/embeddings/refresh`

Refresh entity embeddings for one research space.

## Observations

### `POST /observations`

Record one observation.

### `GET /observations`

List observations.

### `GET /observations/{observation_id}`

Get one observation.

## Canonical relations

### `GET /relations`

List canonical relations.

Reads return claim-backed projected relations by default.

### `POST /relations`

Create a canonical relation through the internal compatibility path.

Important:

- admin/system only
- not a normal public workflow
- creates a manual support claim and materializes through the projection service

### `PATCH /relations/{relation_id}`

Update canonical relation curation status.

### `GET /relations/conflicts`

List mixed-polarity canonical relation conflicts derived from claims.

## Relation claims

### `GET /relation-claims`

List extraction relation claims.

### `PATCH /relation-claims/{claim_id}`

Update relation-claim triage status.

This is the key curator path for moving support claims toward or away from
materialization.

### `GET /relation-claims/{claim_id}/evidence`

List claim evidence for one relation claim.

## Claim graph and claim participants

### `GET /claims/by-entity/{entity_id}`

List claims linked to one entity through structured participants.

### `GET /claims/{claim_id}/participants`

List structured participants for one claim.

### `POST /claim-participants/backfill`

Backfill structured participants for existing claims in one research space.

### `GET /claim-participants/coverage`

Return participant coverage summary for one research space.

### `GET /claim-relations`

List claim-to-claim relation edges.

### `POST /claim-relations`

Create one claim-to-claim relation edge.

### `PATCH /claim-relations/{relation_id}`

Update claim relation review status.

### `GET /claims/{claim_id}/mechanism-chain`

Traverse a claim-rooted mechanism-style chain using reviewed `claim_relations`.

### `GET /graph/reasoning-paths`

List persisted derived reasoning paths.

Supported filters:

- `start_entity_id`
- `end_entity_id`
- `status`
- `path_kind`

### `GET /graph/reasoning-paths/{path_id}`

Get one fully expanded reasoning path.

The response includes:

- the path row
- ordered path steps
- linked claims
- claim-to-claim edges
- participants
- claim evidence
- any linked canonical relations

## Graph rendering and export

### `GET /graph/export`

Export the canonical graph.

### `POST /graph/subgraph`

Build a bounded subgraph for interactive graph rendering.

### `GET /graph/neighborhood/{entity_id}`

Get one entity neighborhood subgraph.

### `POST /graph/document`

Build one unified graph document containing:

- canonical edges
- projection-backed claim overlays
- evidence elements

### `GET /graph/views/{view_type}/{resource_id}`

Build one domain-specific graph view.

Supported `view_type` values:

- `gene`
- `variant`
- `phenotype`
- `paper`
- `claim`

The response bundles:

- the focal resource
- claim-backed canonical relations
- related claims
- claim-to-claim edges
- participants
- claim evidence

## Search and discovery

### `POST /graph/search`

Run natural-language graph search.

### `POST /graph/connections/discover`

Discover graph connections for one or more seed entities.

### `POST /entities/{entity_id}/connections`

Discover graph connections for one entity.

### `POST /graph/relation-suggestions`

Suggest constrained missing relations using hybrid graph plus embeddings.

## Operational graph tooling

These are not public API endpoints.

### `scripts/check_claim_projection_readiness.py`

Audit global claim-backed projection readiness.

### `make graph-readiness`

Run the operational readiness check through the configured local Postgres
environment.

### `scripts/rebuild_reasoning_paths.py`

Rebuild persisted reasoning paths for one space or globally.

### `make graph-reasoning-rebuild`

Run the reasoning-path rebuild through the configured local Postgres
environment.
