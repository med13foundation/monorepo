"""Graph platform package boundaries for phase-2 platformization.

This package is the forward-looking home for the graph platform split
described in `docs/graph/history/migration-phase2.md`.

Current intent:

- `src.graph.core`
  Domain-neutral graph platform code.
- `src.graph.domain_biomedical`
  Biomedical domain-pack code layered on top of graph core.
- `src.graph.domain_sports`
  Sports domain-pack code layered on top of graph core.

The existing graph runtime still primarily lives under `src/...` and
`services/graph_api/...`. These packages define the target ownership boundary
before behavior is migrated.
"""
