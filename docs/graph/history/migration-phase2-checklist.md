# Migration Phase 2 Checklist

Progress tracker for [`migration-phase2.md`](migration-phase2.md).

Use this file to track implementation progress without changing the main design
document.

## How To Use

- Check items as work lands.
- Add links to PRs, ADRs, scripts, or benchmark results next to completed items.
- Keep phase completion tied to validation gates, not just code changes.
- Do not mark a phase complete until its validation gate is satisfied.

## Overall Progress

- [ ] Phase 0 complete
- [ ] Phase 1 complete
- [ ] Phase 2 complete
- [ ] Phase 3 complete
- [ ] Phase 4 complete
- [ ] Phase 5 complete
- [ ] Phase 6 complete
- [ ] Phase 7 complete

## Phase 0: Baseline And Guardrails

Reference:
[`migration-phase2.md#phase-0-baseline-and-guardrails`](migration-phase2.md#phase-0-baseline-and-guardrails)

Scope and deliverables:

- [ ] Current route contract is recorded
- [ ] Generated client outputs are captured
- [ ] Current auth and access expectations are documented
- [ ] Representative graph-read benchmarks exist
- [ ] Dependency boundaries are documented
- [ ] Core versus domain-pack validation approach is defined
- [ ] OpenAPI baseline snapshot exists
- [ ] TypeScript client baseline exists
- [ ] Benchmark set covers graph reads and evidence drilldown
- [ ] Dependency-boundary rules are written
- [ ] ADRs exist for naming, packaging, and read-model ownership

Validation gate:

- [ ] `make graph-service-checks` passes
- [ ] Benchmark suite produces repeatable numbers
- [ ] Boundary-validation script exists or is clearly scoped
- [ ] Current auth and role expectations are reviewed

Notes:

-

## Phase 1: Runtime Neutralization

Reference:
[`migration-phase2.md#phase-1-runtime-neutralization`](migration-phase2.md#phase-1-runtime-neutralization)

Scope and deliverables:

- [ ] MED13-prefixed graph env names are replaced with neutral graph names
- [ ] Graph runtime naming is isolated from MED13 application naming
- [ ] Domain defaults are moved out of generic runtime config
- [ ] Temporary compatibility aliases are minimized
- [ ] Neutral graph runtime env contract is documented
- [ ] Config docs and deploy references are updated
- [ ] Alias policy and removal intent are documented
- [ ] Runtime configuration and auth startup tests exist

Validation gate:

- [ ] Graph service boots with neutral env names only
- [ ] Any temporary aliases are documented with removal intent
- [ ] No new MED13-specific graph env vars were introduced
- [ ] Contract generation still passes unchanged
- [ ] Client generation still passes unchanged

Notes:

-

## Phase 2: Core And Domain-Pack Separation

Reference:
[`migration-phase2.md#phase-2-core-and-domain-pack-separation`](migration-phase2.md#phase-2-core-and-domain-pack-separation)

Scope and deliverables:

- [ ] Graph-core module boundary is defined
- [ ] Biomedical domain-pack boundary is defined
- [ ] Biomedical view defaults are moved out of graph-core
- [ ] Connector defaults are moved out of graph-core
- [ ] Pack-local heuristics are moved out of graph-core
- [ ] MED13 application wiring sits on top of the biomedical pack
- [ ] Graph-core package or module boundary exists
- [ ] Biomedical pack package or module boundary exists
- [ ] Import-direction rules enforce core independence
- [ ] Biomedical defaults and pack registrations are migrated

Validation gate:

- [ ] Graph-core has no compile-time dependency on biomedical modules
- [ ] Biomedical behavior loads through the pack boundary
- [ ] MED13 functionality still works through the biomedical pack
- [ ] Architecture validation blocks reverse imports from core to domain packs

Notes:

-

## Phase 3: Extension And Access Platformization

Reference:
[`migration-phase2.md#phase-3-extension-and-access-platformization`](migration-phase2.md#phase-3-extension-and-access-platformization)

Scope and deliverables:

- [ ] Extension interfaces for views are defined
- [ ] Extension interfaces for search are defined
- [ ] Extension interfaces for relation suggestions are defined
- [ ] Extension interfaces for connectors are defined
- [ ] Extension interfaces for dictionary loading are defined
- [ ] Extension interfaces for pack registration are defined
- [ ] Startup pack registration flow is defined
- [ ] Graph-core auth abstractions are defined
- [ ] Graph-core tenancy abstractions are defined
- [ ] Application integration contract for JWT, roles, and tenant membership exists
- [ ] Domain-pack registration lifecycle is documented

Validation gate:

- [ ] Graph service can start with pack registration through explicit interfaces
- [ ] Auth and tenancy abstractions remain domain-neutral
- [ ] Service and RLS-aware behavior still produce the same authorization results
- [ ] No pack overrides core invariants or projection logic

Notes:

-

## Phase 4: Query Index Foundation

Reference:
[`migration-phase2.md#phase-4-query-index-foundation`](migration-phase2.md#phase-4-query-index-foundation)

Scope and deliverables:

- [ ] Generic read-model framework exists in graph-core
- [ ] Incremental index updates attach to projection events
- [ ] Incremental index updates attach to claim events
- [ ] First bottleneck-driven read models are implemented
- [ ] Full rebuild path exists for repair and backfill
- [ ] Read-model schema and ownership rules are documented
- [ ] Rebuild job for query indexes exists
- [ ] Benchmark comparison exists for before and after index introduction

Initial read models:

- [ ] `entity_neighbors`
- [ ] `entity_relation_summary`
- [ ] `entity_claim_summary`

Validation gate:

- [ ] New read models are derived only from authoritative stores
- [ ] Event-driven updates keep indexes fresh for target workflows
- [ ] Full rebuild restores indexes correctly from source truth
- [ ] Selected workloads show better benchmarked query latency

Notes:

-

## Phase 5: Reasoning Index Hardening

Reference:
[`migration-phase2.md#phase-5-reasoning-index-hardening`](migration-phase2.md#phase-5-reasoning-index-hardening)

Scope and deliverables:

- [ ] Mechanism-oriented read models are added
- [ ] Invalidation rules for reasoning indexes are defined
- [ ] Rebuild behavior for reasoning indexes is defined
- [ ] Reasoning paths remain derived from grounded claim structures
- [ ] Advanced ranking and pruning remain deferred unless justified by metrics
- [ ] Reasoning index schema exists
- [ ] Invalidation hooks tie to claim and projection changes
- [ ] Rebuild workflow for mechanism indexes exists
- [ ] Mechanism-query benchmarks and correctness checks exist

Initial reasoning indexes:

- [ ] `entity_mechanism_paths`

Validation gate:

- [ ] Mechanism indexes are rebuildable
- [ ] Reasoning reads are materially faster for supported workflows
- [ ] No reasoning index becomes a truth source
- [ ] Hypothesis generation still depends on claim-backed reasoning inputs

Notes:

-

## Phase 6: Product Boundary Hardening

Reference:
[`migration-phase2.md#phase-6-product-boundary-hardening`](migration-phase2.md#phase-6-product-boundary-hardening)

Scope and deliverables:

- [ ] API versioning policy is defined
- [ ] Deprecation policy is defined
- [ ] Generated-client ownership is defined
- [ ] Generated-client release process is defined
- [ ] Runtime-to-client compatibility expectations are defined
- [ ] Operator upgrade workflow is documented
- [ ] Release checklist exists
- [ ] Upgrade guide exists

Validation gate:

- [ ] OpenAPI remains the release contract
- [ ] Contract checks run before release
- [ ] Generated clients are treated as versioned artifacts
- [ ] Breaking changes require explicit release intent and migration notes

Notes:

-

## Phase 7: Cross-Domain Proof

Reference:
[`migration-phase2.md#phase-7-cross-domain-proof`](migration-phase2.md#phase-7-cross-domain-proof)

Scope and deliverables:

- [ ] Biomedical remains the primary production pack
- [ ] At least one non-biomedical pack is implemented
- [ ] Shared extension model is validated across packs
- [ ] Shared auth model is validated across packs
- [ ] Shared contract-generation model is validated across packs
- [ ] Shared query-index model is validated across packs
- [ ] Cross-domain validation matrix results are recorded
- [ ] Shared graph-core examples across domains are documented
- [ ] Pack-boundary leakage findings are documented

Candidate non-biomedical packs:

- [ ] Sports analytics
- [ ] Policy or enterprise knowledge

Validation gate:

- [ ] Non-biomedical pack runs without core forks
- [ ] Auth and tenancy model works unchanged
- [ ] Contract-generation and release workflow works unchanged
- [ ] Query-index framework supports both domains without special-casing core logic

Notes:

-

## Cross-Phase Workstreams

### Workstream A: Architecture And Packaging

- [ ] Core/module split is tracked
- [ ] Dependency validation is tracked
- [ ] Pack lifecycle is tracked

### Workstream B: Auth And Access

- [ ] Portable auth abstractions are tracked
- [ ] Application identity integration is tracked
- [ ] RLS-aware behavior validation is tracked

### Workstream C: Query Performance

- [ ] Benchmark design is tracked
- [ ] Read-model implementation is tracked
- [ ] Event-driven updates are tracked
- [ ] Rebuild workflows are tracked

### Workstream D: Product Boundary

- [ ] OpenAPI ownership is tracked
- [ ] Client generation is tracked
- [ ] Versioning is tracked
- [ ] Release and upgrade policy is tracked

### Workstream E: Domain Proof

- [ ] Biomedical-pack stabilization is tracked
- [ ] Non-biomedical-pack implementation is tracked
- [ ] Cross-domain validation matrix is tracked

## Final Exit Criteria

Reference:
[`migration-phase2.md#exit-criteria`](migration-phase2.md#exit-criteria)

- [ ] Graph-core runs without biomedical modules in its dependency chain
- [ ] Neutral graph naming replaces MED13-specific runtime naming
- [ ] Domain-specific defaults are removed from graph-core
- [ ] Biomedical behavior loads through explicit extension points
- [ ] The MED13 application uses the biomedical pack without core changes
- [ ] Read-model strategy is implemented or clearly deferred with no ambiguity
- [ ] Auth, tenancy, and RLS behavior are documented as part of the product boundary
- [ ] API versioning, deprecation, and generated-client policy are documented
- [ ] At least one non-biomedical domain pack proves the architecture without core forks
