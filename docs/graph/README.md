# Graph Docs

This folder explains the standalone graph service from different points of view.
The same service is used by different layers of users:

- curious readers who want to understand what the graph service is
- admins and operators who need to run or troubleshoot it
- developers who need to build against it or change it
- maintainers who need exact contract and architecture references

In simple terms, this service is the backend that stores and serves MED13's
connected knowledge: entities, claims, canonical relations, evidence,
reasoning-paths, graph search, and graph-specific operational workflows.

## Choose Your Path

### I want the simple explanation

Read [overview/what-this-service-does.md](overview/what-this-service-does.md).

### I administer or operate the service

Read [admins/admin-guide.md](admins/admin-guide.md).

### I build against the service or change its code

Read [developers/developer-guide.md](developers/developer-guide.md).

### I need exact technical reference

Read [reference/README.md](reference/README.md).

### I need migration history and extraction context

Read [history/README.md](history/README.md).

## What The Service Owns

- the graph HTTP API under `/health` and `/v1/...`
- graph-space-scoped entities, observations, provenance, claims, claim
  relations, canonical relations, graph views, graph documents, reasoning
  paths, search, connection discovery, hypotheses, concepts, and graph-specific
  admin/control-plane operations
- graph-service-local authentication and authorization checks
- graph-space registry and graph-space membership state used by the standalone
  graph runtime
- graph-specific maintenance workflows such as projection readiness audits,
  repairs, participant backfill, reasoning-path rebuilds, and operation-run
  history
- graph-specific deployment and runtime configuration

The platform app no longer owns graph routes. Platform callers use this service
over HTTP.

## Folder Layout

- [overview/](overview/)
  Plain-language docs for understanding what the service does and why it exists.
- [admins/](admins/)
  Admin/operator guides and task-oriented operational documentation.
- [developers/](developers/)
  Developer onboarding, runtime model, contracts, and local workflow guidance.
- [reference/](reference/)
  Exact reference docs: architecture, endpoints, deployment topology, examples,
  use cases, and inventory.
- [history/](history/)
  Historical extraction and migration planning documents.

## Source Of Truth

- `services/graph_api/openapi.json`
  Generated request/response contract for the running service.
- [reference/endpoints.md](reference/endpoints.md)
  Human-readable route inventory with access expectations.
- `services/graph_api/routers/`
  Route implementation source.
- [reference/service-inventory.md](reference/service-inventory.md)
  Current runtime/module/caller/tooling inventory.
- `src/web/types/graph-service.generated.ts`
  Generated TypeScript contract for web/admin clients.

If a prose document drifts from the generated contract, treat
`services/graph_api/openapi.json` as authoritative and update the prose docs.
