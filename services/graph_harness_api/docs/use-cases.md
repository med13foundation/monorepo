# Example Use Cases

These examples are written for new users.

Assume:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"
export SPACE_ID="11111111-1111-1111-1111-111111111111"
export SEED_ENTITY_ID="22222222-2222-2222-2222-222222222222"
```

## Use Case 1: Bootstrap A New Research Space

Goal:

- create a first graph snapshot
- generate a research brief
- stage initial claim proposals

Start the bootstrap run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/research-bootstrap/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"objective\": \"Map the strongest evidence around MED13 and congenital heart disease\",
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"source_type\": \"pubmed\",
    \"max_depth\": 2,
    \"max_hypotheses\": 10
  }"
```

What to look for in the response:

- `run.id`
- `graph_snapshot.id`
- `research_brief`
- `proposal_count`

List the artifacts for the run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/artifacts" \
  -H "Authorization: Bearer $TOKEN"
```

Common bootstrap artifacts:

- `graph_context_snapshot`
- `graph_summary`
- `source_inventory`
- `candidate_claim_pack`
- `research_brief`

List staged proposals:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/proposals" \
  -H "Authorization: Bearer $TOKEN"
```

Promote one staged proposal:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/proposals/<proposal_id>/promote" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Approved after bootstrap review",
    "metadata": {}
  }'
```

## Use Case 2: Ask A Grounded Chat Question

Goal:

- ask a question against current graph and memory state
- inspect verification and evidence
- optionally promote one inline graph-write candidate

Create a chat session:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/chat-sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "MED13 briefing chat"
  }'
```

Send a message:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/chat-sessions/<session_id>/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the strongest evidence linking MED13 to congenital heart disease?",
    "max_depth": 2,
    "top_k": 10,
    "include_evidence_chains": true
  }'
```

Read the result:

- `result.answer`
- `result.verification.status`
- `result.evidence`
- `assistant_message.metadata`

If the answer is verified and includes ranked graph-write candidates, promote the
first one directly:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/chat-sessions/<session_id>/graph-write-candidates/0/review" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "promote",
    "reason": "Supported strongly enough to write to the graph",
    "metadata": {}
  }'
```

If you prefer staged proposals instead of immediate review:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/chat-sessions/<session_id>/proposals/graph-write" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidates": null
  }'
```

Inspect the transparency snapshot for the chat run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

This tells you:

- which tools were visible to the run
- which tools were filtered out

Then inspect the ordered decision log:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"
```

This tells you:

- what tools the run actually executed
- whether the run paused for approval
- whether a later human review promoted or rejected something tied to this run

For a fuller explanation of what those two endpoints mean, read
[Run Transparency](/Users/alvaro1/Documents/med13/foundation/resource_library/services/graph_harness_api/docs/transparency.md).

## Use Case 3: Create A Continuous-Learning Schedule

Goal:

- save a recurring learning configuration
- run it immediately once
- inspect the `delta_report`

Create a schedule:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/schedules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"Daily MED13 learning\",
    \"cadence\": \"daily\",
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"source_type\": \"pubmed\",
    \"max_depth\": 2,
    \"max_new_proposals\": 20,
    \"max_next_questions\": 5,
    \"run_budget\": {
      \"max_tool_calls\": 20,
      \"max_external_queries\": 10,
      \"max_new_proposals\": 20,
      \"max_runtime_seconds\": 300,
      \"max_cost_usd\": 5.0
    },
    \"metadata\": {}
  }"
```

Trigger an immediate run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/schedules/<schedule_id>/run-now" \
  -H "Authorization: Bearer $TOKEN" \
  -X POST
```

Open the delta report artifact:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/artifacts/delta_report" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 4: Run Mechanism Discovery

Goal:

- search reasoning paths
- rank converging mechanisms
- stage mechanism proposals

Start the run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/mechanism-discovery/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"max_candidates\": 10,
    \"max_reasoning_paths\": 50,
    \"max_path_depth\": 4,
    \"min_path_confidence\": 0.0
  }"
```

What to inspect:

- `candidate_count`
- `proposal_count`
- `candidates[].ranking_score`

List the staged mechanism proposals:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/proposals?proposal_type=mechanism_candidate" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 5: Curate Staged Claims With Approval

Goal:

- turn staged proposals into a governed curation run
- review approvals
- resume the run

Start claim curation:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/graph-curation/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "proposal_ids": [
      "33333333-3333-3333-3333-333333333333"
    ]
  }'
```

The run will usually pause. Check approvals:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/approvals" \
  -H "Authorization: Bearer $TOKEN"
```

Approve one action:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/approvals/<approval_key>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approved",
    "reason": "Ready to apply"
  }'
```

Resume the paused run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/resume" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "All approvals resolved",
    "metadata": {}
  }'
```

Inspect final curation artifacts:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/artifacts/curation_summary" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 6: Run A Full Supervisor Workflow

Goal:

- bootstrap a space
- ask a briefing question
- start governed curation
- resume the parent workflow after approval

Start the supervisor:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/supervisor/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"objective\": \"Map the strongest evidence around MED13 and congenital heart disease\",
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"include_chat\": true,
    \"include_curation\": true,
    \"curation_source\": \"bootstrap\",
    \"briefing_question\": \"What is the strongest evidence I should review first?\",
    \"chat_max_depth\": 2,
    \"chat_top_k\": 10,
    \"curation_proposal_limit\": 5
  }"
```

Read typed supervisor detail:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/supervisor/runs/<run_id>" \
  -H "Authorization: Bearer $TOKEN"
```

What to inspect:

- `run.status`
- `bootstrap`
- `chat`
- `curation`
- `steps`
- `artifact_keys`

If the parent paused on child curation approval:

1. read `curation_run_id` from supervisor detail
2. list child approvals:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<curation_run_id>/approvals" \
  -H "Authorization: Bearer $TOKEN"
```

3. approve or reject each pending action
4. resume the parent:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/resume" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Child approvals complete",
    "metadata": {}
  }'
```

5. fetch supervisor detail again and confirm it is completed

## Use Case 7: Build A Dashboard For Supervisor Runs

Goal:

- show recent supervisor activity
- highlight paused approval queues
- deep-link into the most important runs

Fetch the dashboard summary:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/supervisor/dashboard" \
  -H "Authorization: Bearer $TOKEN"
```

Useful query examples:

Only paused runs:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/supervisor/dashboard?status=paused" \
  -H "Authorization: Bearer $TOKEN"
```

Only chat-derived curation:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/supervisor/dashboard?curation_source=chat_graph_write" \
  -H "Authorization: Bearer $TOKEN"
```

You can also page through typed supervisor rows:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/supervisor/runs?limit=20&offset=0&sort_by=updated_at&sort_direction=desc" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 8: Audit What A Run Could Do And What It Actually Did

Goal:

- inspect a run safely without reading raw internal traces first
- understand allowed tools versus executed tools
- confirm whether later human review changed the final outcome

This works for any run type:

- `research-bootstrap`
- `graph-chat`
- `continuous-learning`
- `mechanism-discovery`
- `claim-curation`
- `supervisor`

Start with the run id you want to inspect.

Read the capability snapshot:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

Start with these fields:

- `harness_id`
- `policy_profile`
- `visible_tools`
- `filtered_tools`

Then read the decision timeline:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"
```

Start with these fields:

- `summary`
- `declared_policy`
- `decisions`

How to read the result:

- if a tool is in `visible_tools` but never appears in `decisions`, the run was
  allowed to use it but did not need it
- if a decision has `decision_source = "tool"`, it came from harness execution
- if a decision has `decision_source = "manual_review"`, a later user action
  changed the outcome for something tied to this run

If you need the lower-level trace after that, open the raw event stream:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/events" \
  -H "Authorization: Bearer $TOKEN"
```

If you need the actual output content, open the artifacts:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/artifacts" \
  -H "Authorization: Bearer $TOKEN"
```

This is the recommended inspection order for operators and UI clients:

1. `capabilities`
2. `policy-decisions`
3. `events`
4. `artifacts`
