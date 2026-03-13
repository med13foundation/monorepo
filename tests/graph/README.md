# Graph Test Matrix

This checklist maps the graph architecture contract in `docs/graph/reference/architecture.md`
to direct tests in the suite.

Done criteria:

- Every invariant domain below has at least one direct test.
- PostgreSQL-backed hard guarantees run in CI.
- The claim-mutation to projection-rebuild consistency flow is directly tested.

| Domain | Primary coverage |
| --- | --- |
| Claim-ledger integrity | `tests/unit/application/services/test_kernel_relation_projection_materialization_service.py` |
| Projection materialization + rebuild | `tests/unit/application/services/test_kernel_relation_projection_materialization_service.py` |
| Claim evidence provenance | `tests/unit/application/services/test_kernel_relation_projection_materialization_service.py` |
| Participant resolution + backfill | `tests/unit/application/services/test_kernel_claim_projection_readiness_service.py`, `tests/integration/graph_service/test_graph_api.py` |
| Reasoning-path correctness | `tests/unit/application/services/test_kernel_reasoning_path_service.py`, `tests/unit/application/services/test_rebuild_reasoning_paths_script.py` |
| Hypothesis lineage + non-projection | `tests/unit/application/services/test_hypothesis_generation_service.py`, `tests/integration/graph_service/test_graph_api.py` |
| Graph read-model consistency | `tests/integration/graph_service/test_graph_api.py`, `tests/unit/application/services/test_kernel_relation_projection_materialization_service.py` |
| Conflict detection | `tests/integration/graph_service/test_graph_api.py` |
| Research-space isolation | `tests/unit/infrastructure/test_graph_query_repository.py`, `tests/integration/graph_service/test_graph_api.py`, `tests/integration/kernel/test_graph_dictionary_hard_guarantees.py` |
| Dictionary governance | `tests/integration/kernel/test_graph_dictionary_hard_guarantees.py` |
| Operational scripts | `tests/unit/application/services/test_check_claim_projection_readiness_script.py`, `tests/unit/application/services/test_rebuild_reasoning_paths_script.py` |
| Graph performance | `tests/performance/test_graph_query_performance.py` |
