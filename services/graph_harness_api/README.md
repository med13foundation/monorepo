# Graph Harness API Service

This service is the AI control layer for graph-backed research workflows.

Current intent:

- host the canonical Artana runtime for harness lifecycle and model orchestration
- expose harness discovery, run lifecycle, artifact, and approval APIs
- host harness-owned AI graph-search orchestration
- host harness-owned AI graph-connection orchestration
- host harness-owned AI hypothesis exploration
- host harness-owned research-bootstrap runs with durable research state and
  graph-context snapshots
- verify grounded graph-chat answers before allowing chat-derived graph-write
  proposals
- surface and persist reviewable graph-write candidates directly on verified
  graph-chat runs so callers can inspect them before staging proposals
- rank and cap verified chat graph-write candidates so chat surfaces only the
  top deterministic suggestions instead of every raw relation suggestion
- append a compact review section for those ranked graph-write candidates
  directly into verified chat answers
- let chat callers promote or reject those inline graph-write candidates
  directly from the chat session flow
- let the public chat graph-write endpoint reuse the latest verified chat run's
  stored graph-write candidates when callers omit an explicit candidate list
- refresh PubMed literature automatically for graph-chat answers that still
  need review or remain unverified
- synthesize fresh-literature leads back into non-verified graph-chat answers
  so the user gets immediate papers to review, not only metadata
- host harness-owned continuous-learning cycles and schedule definitions
- host harness-owned mechanism-discovery runs and reviewable hypothesis staging
- host governed claim-curation runs with graph-backed duplicate/conflict preflight
- host a supervisor workflow that composes bootstrap, briefing chat, and
  governed claim-curation into one parent run while preserving child runs,
  pausing/resuming the parent across the child approval gate, and optionally
  curating auto-derived, verified chat-backed graph-write proposals instead of
  only bootstrap-staged proposals
- let supervisor callers directly promote or reject briefing-chat graph-write
  candidates unless that review has already been delegated to child curation
- keep direct supervisor briefing-chat review history in the parent
  `supervisor_summary` artifact so orchestration and manual review stay in one
  canonical snapshot
- expose that supervisor briefing-chat review history directly in typed
  supervisor API responses
- expose a typed supervisor detail endpoint so callers can reload canonical
  composed state, progress, nested child bootstrap/chat/curation summaries,
  curation outcome, and briefing-chat review history without stitching
  together generic run and artifact reads
- expose a typed supervisor list endpoint that filters to supervisor workflows
  and returns the same child summaries plus parent/child artifact keys for
  list views
- support typed supervisor list filters for parent status, curation source,
  and whether briefing-chat graph-write reviews exist
- support typed supervisor list sorting and pagination so larger UI views can
  order by creation/update time or review count and page through typed
  supervisor workflow rows
- expose aggregate supervisor list summary counts so list responses include
  paused, completed, reviewed, unreviewed, and curation-source totals for
  dashboard cards without client-side reduction
- support typed supervisor list time-window filters over parent `created_at`
  and `updated_at` so recent orchestration activity can be segmented without a
  separate reporting endpoint
- expose a typed supervisor dashboard endpoint that returns only the canonical
  supervisor summary/trends for the same filtered set, without paginated run
  rows, plus deep-link highlights for latest completed, latest reviewed, and
  oldest paused runs, plus latest `bootstrap` and latest
  `chat_graph_write` runs, plus approval-focused highlights for the latest run
  paused at approval, the run with the largest pending review backlog, and the
  largest pending review backlog within `bootstrap` vs `chat_graph_write`,
  including child curation run ids plus approval artifact keys for direct
  deep-links
- expose typed supervisor trend buckets so list responses include recent-24h,
  recent-7d, recent completed, and recent reviewed counts, plus daily created,
  completed, reviewed, and unreviewed counts plus daily
  bootstrap-vs-chat-graph-write curation source counts from the same filtered
  supervisor set
- enforce explicit run budgets for continuous-learning schedules and runs
- call `services/graph_api` over typed HTTP boundaries
- keep `services/graph_api` deterministic and free of AI runtime concerns
- package as a standalone AI-capable service via
  `services/graph_harness_api/Dockerfile`
- install service-local runtime dependencies from
  `services/graph_harness_api/requirements.txt`
- load model/runtime defaults from the repo `artana.toml`

Greenfield mode applies to this service:

- no compatibility shims
- no fallback service boundary
- no legacy migration paths unless explicitly requested

Run locally with:

```bash
python -m services.graph_harness_api
```

Run the schedule queueing loop with:

```bash
python -m services.graph_harness_api.scheduler
```

Run the leased worker loop with:

```bash
python -m services.graph_harness_api.worker
```

User-facing service docs live in:

- [docs/README.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/README.md)
- [docs/getting-started.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/getting-started.md)
- [docs/concepts.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/concepts.md)
- [docs/api-reference.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/api-reference.md)
- [docs/use-cases.md](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/use-cases.md)

Required runtime environment:

- `GRAPH_API_URL`
- `GRAPH_HARNESS_SERVICE_HOST`
- `GRAPH_HARNESS_SERVICE_PORT`
- optional `GRAPH_HARNESS_SERVICE_RELOAD`
- optional `GRAPH_HARNESS_GRAPH_API_TIMEOUT_SECONDS`
- `GRAPH_JWT_SECRET` or `JWT_SECRET`
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- `OPENAI_API_KEY` or `ARTANA_OPENAI_API_KEY`
- `DATABASE_URL` or `ARTANA_STATE_URI`
- optional `GRAPH_HARNESS_SCHEDULER_POLL_SECONDS`
- optional `GRAPH_HARNESS_SCHEDULER_RUN_ONCE`
- optional `GRAPH_HARNESS_WORKER_ID`
- optional `GRAPH_HARNESS_WORKER_POLL_SECONDS`
- optional `GRAPH_HARNESS_WORKER_RUN_ONCE`
- optional `GRAPH_HARNESS_WORKER_LEASE_TTL_SECONDS`

Deployment/runtime notes:

- container packaging uses `services/graph_harness_api/Dockerfile`
- the image copies `artana.toml` into `/app/artana.toml` for model/runtime config
- the harness service remains the only graph-side runtime that should install
  Artana/OpenAI dependencies
- run lifecycle, artifacts, workspace state, progress, and events now default
  to Artana-backed adapters; the obsolete SQLAlchemy lifecycle tables have been
  dropped, and SQLAlchemy now retains only the durable run catalog plus
  harness-domain state that is not kernel-owned
- recurring schedules now queue kernel-backed runs, and the separate worker
  loop acquires Artana leases before executing those runs
- manual workflow routes and `POST /runs/{run_id}/resume` now use the same
  queue + leased-worker execution path as scheduled runs instead of maintaining
  a separate route-local orchestration flow
- the aligned runtime currently passes repo-wide `make type-check`,
  repo-wide `make test`, and `python scripts/export_graph_harness_openapi.py
  --output services/graph_harness_api/openapi.json --check`
- dedicated acceptance coverage for the aligned runtime now lives in
  `tests/integration/graph_harness_api/test_runtime_paths.py` and
  `tests/e2e/graph_harness_api/test_user_flows.py`, covering lifecycle/resume,
  bootstrap proposal staging and promotion, schedule `run-now` to
  `delta_report`, mechanism-discovery candidate staging, chat graph-write
  review, claim-curation approval/resume, supervisor bootstrap/chat/
  curation pause-resume flows, and the transparency endpoints that expose run
  capabilities plus observed tool/manual-review policy decisions
