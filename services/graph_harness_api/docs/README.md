# Graph Harness API Docs

This folder contains the user-facing documentation for the `graph_harness_api`
service.

If you are new to the service, read these files in order:

1. [Getting Started](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/getting-started.md)
2. [Core Concepts](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/concepts.md)
3. [Run Transparency](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/transparency.md)
4. [API Reference](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/api-reference.md)
5. [Example Use Cases](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/use-cases.md)

Useful companion files:

- Service overview: [README.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/README.md)
- Interactive API docs when the service is running: `/docs`
- Raw OpenAPI spec: [openapi.json](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/openapi.json)

What this service does:

- Runs AI-assisted graph workflows such as search, chat, research bootstrap,
  continuous learning, mechanism discovery, claim curation, and supervisor
  orchestration.
- Stores run lifecycle state, artifacts, workspace snapshots, events, and
  progress through the Artana-backed runtime.
- Keeps domain state such as proposals, approvals, schedules, research state,
  graph snapshots, and chat sessions.
- Exposes an HTTP API that other services and UI clients can call directly.

What this docs set focuses on:

- how to start the service
- how authentication works
- what a run, artifact, proposal, approval, and schedule mean
- what was just added for run transparency
- how to inspect run transparency through capabilities and policy decisions
- every available endpoint
- realistic request examples for the most important workflows
