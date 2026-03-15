# Graph API Docs

This folder explains the standalone `graph_api` service in plain language.

If you are new to the service, read these files in order:

1. [Getting Started](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/docs/getting-started.md)
2. [Core Concepts](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/docs/concepts.md)
3. [Data Model](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/docs/data-model.md)
4. [API Reference](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/docs/api-reference.md)

Useful companion files:

- Service overview: [README.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/README.md)
- Container definition: [Dockerfile](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/Dockerfile)
- Interactive API docs when the service is running: `/docs`
- Raw OpenAPI spec: [openapi.json](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_api/openapi.json)

What this service is:

- A standalone FastAPI service for graph storage, graph reads, graph curation, and graph governance.
- The HTTP boundary around the graph kernel tables such as `entities`, `observations`, `relations`, `relation_claims`, and `provenance`.
- The owner of graph-space registry and graph-space membership state used for service-local authorization.
- A service that reuses shared graph domain and application code from `src/`, but runs in its own process, with its own container image and its own database configuration.

What this service is not:

- It is not the AI orchestration layer. That lives in `services/graph_harness_api`.
- It is not the platform monolith API.
- It is not a background worker system by itself. Maintenance actions are exposed as explicit admin endpoints.

What this docs set focuses on:

- what runs inside the graph container
- how the graph service is separated from the rest of the platform
- what the main database tables mean
- the simplest mental model for claims, canonical relations, projections, and reasoning paths
- every HTTP route exposed by the service
