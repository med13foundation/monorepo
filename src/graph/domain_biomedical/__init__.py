"""Biomedical graph domain-pack boundary.

Phase-2 migration target:

- biomedical graph views and defaults
- biomedical connectors
- biomedical dictionary loading
- pack-specific heuristics and registration

Import rule:

- the biomedical pack may depend on `src.graph.core`
- graph-core may not depend on the biomedical pack

This package is intentionally minimal until biomedical behavior is moved into
it.
"""
