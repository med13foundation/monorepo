# Getting Started

## What This Service Is

`graph_harness_api` is the orchestration layer for graph-backed research
workflows.

It gives you one API for:

- graph search
- graph chat
- research bootstrap
- continuous learning
- mechanism discovery
- governed claim curation
- supervisor workflows that compose several steps together

The service does not replace the graph service. It sits on top of
`services/graph_api` and calls it through typed HTTP boundaries.

## Default Local Ports

- Harness API: `http://localhost:8091`
- Graph API: `http://localhost:8080`

## Run The Service

From the repository root:

```bash
source venv/bin/activate
python -m services.graph_harness_api
```

Open:

- Interactive docs: `http://localhost:8091/docs`
- OpenAPI JSON: `http://localhost:8091/openapi.json`
- Health check: `http://localhost:8091/health`

## Run The Background Loops

The API can create runs inline for synchronous user requests, but the service
also has dedicated queueing and execution loops.

Run the schedule queueing loop:

```bash
source venv/bin/activate
python -m services.graph_harness_api.scheduler
```

Run the worker loop:

```bash
source venv/bin/activate
python -m services.graph_harness_api.worker
```

## Run The Container

The service container is defined in
[Dockerfile](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/Dockerfile).

Build it from the repository root:

```bash
docker build -f services/graph_harness_api/Dockerfile -t graph-harness-api .
```

Run it:

```bash
docker run --rm -p 8091:8091 \
  -e GRAPH_API_URL=http://host.docker.internal:8080 \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/med13 \
  -e GRAPH_JWT_SECRET=change-me \
  -e OPENAI_API_KEY=change-me \
  graph-harness-api
```

## Required Environment Variables

These are the main runtime settings.

Required:

- `GRAPH_API_URL`
- `DATABASE_URL` or `ARTANA_STATE_URI`
- `GRAPH_JWT_SECRET` or `JWT_SECRET`
- `OPENAI_API_KEY` or `ARTANA_OPENAI_API_KEY`

Common optional settings:

- `GRAPH_HARNESS_SERVICE_HOST`
- `GRAPH_HARNESS_SERVICE_PORT`
- `GRAPH_HARNESS_SERVICE_RELOAD`
- `GRAPH_HARNESS_GRAPH_API_TIMEOUT_SECONDS`
- `GRAPH_HARNESS_SCHEDULER_POLL_SECONDS`
- `GRAPH_HARNESS_SCHEDULER_RUN_ONCE`
- `GRAPH_HARNESS_WORKER_ID`
- `GRAPH_HARNESS_WORKER_POLL_SECONDS`
- `GRAPH_HARNESS_WORKER_RUN_ONCE`
- `GRAPH_HARNESS_WORKER_LEASE_TTL_SECONDS`
- `GRAPH_ALLOW_TEST_AUTH_HEADERS`

## Authentication

All API routes use the same auth model as the rest of the repository.

Normal usage:

- send `Authorization: Bearer <token>`

Example:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"

curl -s "$HARNESS_URL/health" \
  -H "Authorization: Bearer $TOKEN"
```

## Local Test Auth Shortcut

For local non-production smoke testing, the repository supports test headers
when `GRAPH_ALLOW_TEST_AUTH_HEADERS=1`.

Example:

```bash
export HARNESS_URL="http://localhost:8091"

curl -s "$HARNESS_URL/v1/harnesses" \
  -H "X-TEST-USER-ID: 11111111-1111-1111-1111-111111111111" \
  -H "X-TEST-USER-EMAIL: researcher@example.com" \
  -H "X-TEST-USER-ROLE: researcher"
```

Use this only for local development and tests.

## First Five Calls To Make

If you are new to the service, this is the easiest way to learn it.

1. Check health:

```bash
curl -s "$HARNESS_URL/health" -H "Authorization: Bearer $TOKEN"
```

2. List available harnesses:

```bash
curl -s "$HARNESS_URL/v1/harnesses" -H "Authorization: Bearer $TOKEN"
```

3. Start a research bootstrap run:

```bash
curl -s "$HARNESS_URL/v1/spaces/11111111-1111-1111-1111-111111111111/agents/research-bootstrap/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Map the strongest evidence around MED13 and congenital heart disease",
    "source_type": "pubmed",
    "max_depth": 2,
    "max_hypotheses": 10
  }'
```

4. Inspect the run artifacts:

```bash
curl -s "$HARNESS_URL/v1/spaces/11111111-1111-1111-1111-111111111111/runs/<run_id>/artifacts" \
  -H "Authorization: Bearer $TOKEN"
```

5. List staged proposals:

```bash
curl -s "$HARNESS_URL/v1/spaces/11111111-1111-1111-1111-111111111111/proposals" \
  -H "Authorization: Bearer $TOKEN"
```

## What Was Just Added: Run Transparency

The newest addition to the service is run transparency.

Every run now gives you two extra views:

- `capabilities`
  what the run was allowed to use when it started
- `policy-decisions`
  what the run actually executed, plus later human review decisions that can be
  tied back to the run

If you only want one quick learning exercise after your first run, do this:

1. start any run
2. copy the returned `run.id`
3. fetch `capabilities`
4. fetch `policy-decisions`

Example:

```bash
export SPACE_ID="11111111-1111-1111-1111-111111111111"
export RUN_ID="<run_id>"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/capabilities" \
  -H "Authorization: Bearer $TOKEN"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"
```

Use these endpoints to answer three simple questions:

- what could the run do?
- what did it actually do?
- did a later human review change the final outcome?

For the full guide, read
[Run Transparency](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/transparency.md).

## Which Workflow Should I Use?

Use:

- `graph-search` when you want one grounded answer against the graph
- `chat-sessions` when you want a conversational workflow with memory
- `research-bootstrap` when a space is empty and needs an initial evidence map
- `continuous-learning` when you want recurring refresh cycles
- `mechanism-discovery` when you want ranked candidate mechanisms
- `graph-curation` when you already have staged proposals and need approval-gated review
- `supervisor` when you want one parent workflow that can bootstrap, chat, and curate
