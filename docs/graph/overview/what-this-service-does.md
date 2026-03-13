# What This Service Does

This document explains the graph service in plain language.

## Short Version

The graph service is the backend that turns MED13 research data into connected,
explainable knowledge.

Instead of only storing isolated rows such as "this paper mentioned X", it lets
the system store and query:

- entities
  the things in the graph, such as genes, variants, phenotypes, papers, and
  claims
- claims
  statements extracted or entered about those things
- canonical relations
  the stable graph edges that are allowed to appear in default graph views
- evidence and provenance
  why a claim or relation exists and where it came from
- reasoning paths and graph search
  reusable paths and search results over the graph

## Why It Exists

MED13 needs more than document storage. It needs a way to answer questions like:

- what connects this gene to this phenotype?
- which claims support or refute this relation?
- what evidence explains this graph edge?
- what mechanism path leads from A to B?
- what graph state is safe to show as canonical truth versus still-open claim
  space?

This service exists to answer those questions through one graph-specific API and
runtime instead of spreading graph logic across the main platform.

## What It Owns

The graph service owns:

- graph APIs for entities, claims, relations, graph views, graph documents,
  graph search, graph connections, reasoning paths, hypotheses, concepts, and
  dictionary governance
- graph-specific admin/control-plane APIs for graph spaces, memberships,
  readiness audits, repairs, rebuilds, and run history
- graph-service-local authz rules for graph spaces and graph admins
- graph-owned runtime metadata such as `graph_spaces`,
  `graph_space_memberships`, and `graph_operation_runs`

The graph service does not own:

- general platform membership and organization business rules
- the full MED13 admin UI
- the public website
- generic platform APIs outside the graph boundary

## How It Works In Simple Terms

1. Data comes in from ingestion, extraction, or manual curation.
2. The service stores claims, participants, and evidence about that data.
3. Resolved support claims can materialize canonical relations.
4. Canonical graph reads return stable, explainable edges by default.
5. Claim-space reads still preserve disagreement, uncertainty, and hypotheses.
6. Search, graph views, and reasoning-path reads use those explainable graph
   stores to answer user questions.

The key idea is:

- claims are the detailed ledger
- canonical relations are the stable graph projection
- evidence and provenance explain both

## What Different People Use It For

### Researchers and Curators

- browse the graph
- inspect claims and evidence
- review or resolve claim state
- inspect domain views such as gene, variant, phenotype, paper, and claim
- generate or record hypotheses

### Admins and Operators

- keep graph spaces and memberships in sync
- run readiness audits and repairs
- rebuild reasoning paths
- inspect operation-run history
- manage graph-specific dictionary governance

### Developers

- call the graph service over HTTP
- use the generated OpenAPI and TypeScript contracts
- add or change graph-service routes and runtime code
- validate graph boundaries and graph-specific deploy/runtime contracts

## Is It MED13-Specific?

Partly.

The service is graph-generic in structure:

- it works with entities, claims, relations, evidence, provenance, search,
  reasoning, and governance
- it has a clean service boundary and its own runtime contract

But it is currently MED13-shaped in content and defaults:

- many examples and view types are biomedical
- some source types and feature flags use MED13 naming
- the surrounding product and UI are MED13

So the service is not just a one-off MED13 script, but it is also not yet a
fully generic productized graph platform.

## What To Read Next

- If you operate the service: [../admins/admin-guide.md](../admins/admin-guide.md)
- If you develop against it: [../developers/developer-guide.md](../developers/developer-guide.md)
- If you need exact API routes: [../reference/endpoints.md](../reference/endpoints.md)
- If you need the graph model and invariants: [../reference/architecture.md](../reference/architecture.md)
