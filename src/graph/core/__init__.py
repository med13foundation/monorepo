"""Domain-neutral graph-core package boundary.

Phase-2 migration target:

- claim-first graph invariants
- domain-neutral graph services and abstractions
- read-model and query infrastructure
- auth and tenancy abstractions

Import rule:

- graph-core may not import `src.graph.domain_biomedical`

This package is intentionally minimal until graph behavior is moved into it.
"""
