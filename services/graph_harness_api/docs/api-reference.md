# API Reference

Base URL examples in this file assume:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"
export SPACE_ID="11111111-1111-1111-1111-111111111111"
```

All examples use:

```bash
-H "Authorization: Bearer $TOKEN"
```

## Endpoint Groups

## 1. Health And Discovery

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health` | Returns service health status. |
| `GET` | `/v1/harnesses` | Lists all available harness templates. |
| `GET` | `/v1/harnesses/{harness_id}` | Returns one harness template. |

Example:

```bash
curl -s "$HARNESS_URL/v1/harnesses" \
  -H "Authorization: Bearer $TOKEN"
```

## 2. Generic Run Lifecycle

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/runs` | Creates a generic harness run by `harness_id`. |
| `GET` | `/v1/spaces/{space_id}/runs` | Lists runs in a space. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}` | Returns one run. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/progress` | Returns current run progress. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/events` | Returns lifecycle events. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/capabilities` | Returns the frozen tool/policy snapshot for the run. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/policy-decisions` | Returns observed tool decisions and manual review decisions for the run. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/resume` | Resumes a paused run. |

Generic run creation body:

```json
{
  "harness_id": "research-bootstrap",
  "title": "Bootstrap MED13 evidence map",
  "input_payload": {
    "objective": "Find the strongest evidence for MED13 in congenital heart disease",
    "source_type": "pubmed",
    "max_depth": 2
  }
}
```

Transparency endpoints answer:

- what tools a run was allowed to use
- what tools it actually executed
- whether a human review added a promote or reject decision later

### Transparency Endpoints In Practice

Use `GET /capabilities` first.

It is the frozen answer to:

- what tools could this run use?
- which tools were filtered out?
- what policy profile shaped the run?

Example:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

Important response areas:

- `visible_tools`
- `filtered_tools`
- `tool_groups`
- `policy_profile`
- `artifact_key`

Then use `GET /policy-decisions`.

It is the ordered answer to:

- what did the run actually execute?
- which tool steps succeeded or failed?
- did a later user promote or reject something tied to this run?

Example:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"
```

Important response areas:

- `declared_policy`
- `summary`
- `decisions`
- `artifact_key`

Each decision record can include:

- `decision_source`
- `tool_name`
- `decision`
- `reason`
- `status`
- `event_id`
- `approval_id`
- `started_at`
- `completed_at`

Read the full beginner guide here:
[Run Transparency](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/transparency.md).

## 3. Artifacts, Workspace, Intents, And Approvals

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/artifacts` | Lists artifact keys for one run. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/artifacts/{artifact_key}` | Returns one artifact. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/workspace` | Returns the latest workspace snapshot. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/intent` | Records an intent plan with proposed actions. |
| `GET` | `/v1/spaces/{space_id}/runs/{run_id}/approvals` | Lists approvals for a run. |
| `POST` | `/v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}` | Approves or rejects one gated action. |

Intent request body:

```json
{
  "summary": "Review the proposed graph mutations before applying them.",
  "proposed_actions": [
    {
      "approval_key": "claim-1",
      "title": "Promote candidate claim",
      "risk_level": "medium",
      "target_type": "claim",
      "target_id": "candidate-claim-1",
      "requires_approval": true,
      "metadata": {}
    }
  ],
  "metadata": {}
}
```

Approval decision request body:

```json
{
  "decision": "approved",
  "reason": "Evidence is sufficient"
}
```

## 4. Chat Sessions

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/chat-sessions` | Lists chat sessions. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions` | Creates a chat session. |
| `GET` | `/v1/spaces/{space_id}/chat-sessions/{session_id}` | Returns session state and message history. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/messages` | Sends a message and runs graph chat. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write` | Converts verified chat findings into staged graph-write proposals. |
| `POST` | `/v1/spaces/{space_id}/chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review` | Promotes or rejects one inline chat candidate directly. |

Create session body:

```json
{
  "title": "MED13 briefing"
}
```

Send message body:

```json
{
  "content": "What is the strongest evidence linking MED13 to congenital heart disease?",
  "model_id": "gpt-5",
  "max_depth": 2,
  "top_k": 10,
  "include_evidence_chains": true
}
```

Stage graph-write proposals body:

```json
{
  "candidates": null
}
```

Passing `null` or omitting `candidates` tells the service to reuse the ranked
candidate set already persisted on the latest verified chat run.

Direct inline review body:

```json
{
  "decision": "promote",
  "reason": "This relation is supported strongly enough to write to the graph",
  "metadata": {}
}
```

## 5. Proposals

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/proposals` | Lists proposals with optional filters. |
| `GET` | `/v1/spaces/{space_id}/proposals/{proposal_id}` | Returns one proposal. |
| `POST` | `/v1/spaces/{space_id}/proposals/{proposal_id}/promote` | Promotes a pending proposal. |
| `POST` | `/v1/spaces/{space_id}/proposals/{proposal_id}/reject` | Rejects a pending proposal. |

Supported proposal list filters:

- `status`
- `proposal_type`
- `run_id`

Decision request body:

```json
{
  "reason": "Approved after review",
  "metadata": {}
}
```

## 6. Schedules

These routes are for continuous-learning schedules.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/spaces/{space_id}/schedules` | Lists saved schedules. |
| `POST` | `/v1/spaces/{space_id}/schedules` | Creates a schedule. |
| `GET` | `/v1/spaces/{space_id}/schedules/{schedule_id}` | Returns one schedule and recent runs. |
| `PATCH` | `/v1/spaces/{space_id}/schedules/{schedule_id}` | Updates a schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/pause` | Pauses a schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/resume` | Resumes a schedule. |
| `POST` | `/v1/spaces/{space_id}/schedules/{schedule_id}/run-now` | Triggers an immediate run using the schedule configuration. |

Create schedule body:

```json
{
  "title": "Daily MED13 learning",
  "cadence": "daily",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_new_proposals": 20,
  "max_next_questions": 5,
  "model_id": "gpt-5",
  "run_budget": {
    "max_tool_calls": 20,
    "max_external_queries": 10,
    "max_new_proposals": 20,
    "max_runtime_seconds": 300,
    "max_cost_usd": 5.0
  },
  "metadata": {}
}
```

## 7. Graph Search

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/graph-search/runs` | Runs one AI-backed graph search request. |

Body:

```json
{
  "question": "Summarize the strongest MED13 evidence",
  "title": "MED13 graph search",
  "model_id": "gpt-5",
  "max_depth": 2,
  "top_k": 25,
  "curation_statuses": [
    "reviewed"
  ],
  "include_evidence_chains": true
}
```

## 8. Graph Connections

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/graph-connections/runs` | Discovers graph connection candidates from seed entities. |

Body:

```json
{
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "MED13 graph connections",
  "source_type": "pubmed",
  "source_id": null,
  "model_id": "gpt-5",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "shadow_mode": true,
  "pipeline_run_id": null
}
```

## 9. Hypothesis Exploration

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/hypotheses/runs` | Explores hypothesis candidates and stages candidate claims. |

Body:

```json
{
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "MED13 hypothesis exploration",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_hypotheses": 20,
  "model_id": "gpt-5"
}
```

## 10. Research Bootstrap

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/research-bootstrap/runs` | Builds an initial graph snapshot, research brief, and staged claim pack. |

Body:

```json
{
  "objective": "Map the strongest evidence around MED13 and congenital heart disease",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Research Bootstrap Harness",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_hypotheses": 20,
  "model_id": "gpt-5"
}
```

Notes:

- you must provide `objective`, or at least one `seed_entity_id`, or both
- this route returns graph snapshot and research state directly in the response

## 11. Continuous Learning

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/continuous-learning/runs` | Runs one learning cycle and stages net-new proposals. |

Body:

```json
{
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Continuous Learning Harness",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_new_proposals": 20,
  "max_next_questions": 5,
  "model_id": "gpt-5",
  "schedule_id": null,
  "run_budget": {
    "max_tool_calls": 20,
    "max_external_queries": 10,
    "max_new_proposals": 20,
    "max_runtime_seconds": 300,
    "max_cost_usd": 5.0
  }
}
```

## 12. Mechanism Discovery

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/mechanism-discovery/runs` | Ranks converging mechanisms and stages mechanism proposals. |

Body:

```json
{
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Mechanism Discovery Run",
  "max_candidates": 10,
  "max_reasoning_paths": 50,
  "max_path_depth": 4,
  "min_path_confidence": 0.0
}
```

## 13. Claim Curation

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/graph-curation/runs` | Starts a governed claim-curation run for selected proposals. |

Body:

```json
{
  "proposal_ids": [
    "33333333-3333-3333-3333-333333333333"
  ],
  "title": "Claim Curation Harness"
}
```

What to expect:

- the run often pauses for approval
- artifacts include `curation_packet`, `review_plan`, and `approval_intent`
- after approvals are resolved, resume the run with `/runs/{run_id}/resume`

## 14. Supervisor

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/v1/spaces/{space_id}/agents/supervisor/runs` | Starts a composed parent workflow. |
| `GET` | `/v1/spaces/{space_id}/agents/supervisor/runs` | Lists typed supervisor runs. |
| `GET` | `/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}` | Returns typed supervisor detail. |
| `GET` | `/v1/spaces/{space_id}/agents/supervisor/dashboard` | Returns typed dashboard summary and highlights. |
| `POST` | `/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}/chat-graph-write-candidates/{candidate_index}/review` | Promotes or rejects one supervisor briefing-chat graph-write candidate. |

Supervisor create body:

```json
{
  "objective": "Map the strongest evidence around MED13 and congenital heart disease",
  "seed_entity_ids": [
    "22222222-2222-2222-2222-222222222222"
  ],
  "title": "Supervisor Harness",
  "source_type": "pubmed",
  "relation_types": [
    "associated_with"
  ],
  "max_depth": 2,
  "max_hypotheses": 20,
  "model_id": "gpt-5",
  "include_chat": true,
  "include_curation": true,
  "curation_source": "bootstrap",
  "briefing_question": "What is the strongest evidence I should review first?",
  "chat_max_depth": 2,
  "chat_top_k": 10,
  "chat_include_evidence_chains": true,
  "curation_proposal_limit": 5
}
```

Supervisor list query parameters:

- `status`
- `curation_source`
- `has_chat_graph_write_reviews`
- `created_after`
- `created_before`
- `updated_after`
- `updated_before`
- `offset`
- `limit`
- `sort_by`
- `sort_direction`

Supervisor dashboard query parameters:

- `status`
- `curation_source`
- `has_chat_graph_write_reviews`
- `created_after`
- `created_before`
- `updated_after`
- `updated_before`

## Read Versus Write Access

Read endpoints:

- health
- harness discovery
- run list/detail/progress/events/artifacts/workspace
- chat session list/detail
- proposal list/detail
- schedule list/detail
- supervisor list/detail/dashboard

Write endpoints:

- all `POST` workflow routes
- proposal promote/reject
- approvals decision
- chat message send
- chat graph-write staging
- direct candidate review
- schedule create/update/pause/resume/run-now
- run resume

Write access requires a user role of researcher, curator, or admin.
