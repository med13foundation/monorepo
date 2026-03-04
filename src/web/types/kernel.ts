import type { JSONValue, JSONObject } from '@/types/generated'

export interface KernelEntityCreateRequest {
  entity_type: string
  display_label?: string | null
  metadata?: JSONObject
  identifiers?: Record<string, string>
}

export interface KernelEntityUpdateRequest {
  display_label?: string | null
  metadata?: JSONObject | null
  identifiers?: Record<string, string> | null
}

export interface KernelEntityResponse {
  id: string
  research_space_id: string
  entity_type: string
  display_label: string | null
  metadata: JSONObject
  created_at: string
  updated_at: string
}

export interface KernelEntityUpsertResponse {
  entity: KernelEntityResponse
  created: boolean
}

export interface KernelEntityListResponse {
  entities: KernelEntityResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelObservationCreateRequest {
  subject_id: string
  variable_id: string
  value: JSONValue
  unit?: string | null
  observed_at?: string | null
  provenance_id?: string | null
  confidence?: number
}

export interface KernelObservationResponse {
  id: string
  research_space_id: string
  subject_id: string
  variable_id: string

  value_numeric: number | null
  value_text: string | null
  value_date: string | null
  value_coded: string | null
  value_boolean: boolean | null
  value_json: JSONValue | null

  unit: string | null
  observed_at: string | null
  provenance_id: string | null
  confidence: number

  created_at: string
  updated_at: string
}

export interface KernelObservationListResponse {
  observations: KernelObservationResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelRelationCreateRequest {
  source_id: string
  relation_type: string
  target_id: string
  confidence?: number
  evidence_summary?: string | null
  evidence_sentence?: string | null
  evidence_sentence_source?: string | null
  evidence_sentence_confidence?: string | null
  evidence_sentence_rationale?: string | null
  evidence_tier?: string | null
  provenance_id?: string | null
}

export interface KernelRelationCurationUpdateRequest {
  curation_status: string
}

export interface KernelRelationPaperLink {
  label: string
  url: string
  source: string
}

export interface KernelRelationResponse {
  id: string
  research_space_id: string
  source_id: string
  relation_type: string
  target_id: string

  confidence?: number
  evidence_summary?: string | null
  evidence_sentence?: string | null
  evidence_sentence_source?: string | null
  evidence_sentence_confidence?: string | null
  evidence_sentence_rationale?: string | null
  paper_links?: KernelRelationPaperLink[]
  evidence_tier?: string | null
  aggregate_confidence?: number
  source_count?: number
  highest_evidence_tier?: string | null
  curation_status: string

  provenance_id: string | null
  reviewed_by: string | null
  reviewed_at: string | null

  created_at: string
  updated_at: string
}

export interface KernelRelationListResponse {
  relations: KernelRelationResponse[]
  total: number
  offset: number
  limit: number
}

export interface RelationClaimResponse {
  id: string
  research_space_id: string
  source_document_id: string | null
  agent_run_id: string | null
  source_type: string
  relation_type: string
  target_type: string
  source_label: string | null
  target_label: string | null
  confidence: number
  validation_state: string
  validation_reason: string | null
  persistability: 'PERSISTABLE' | 'NON_PERSISTABLE'
  claim_status: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
  linked_relation_id: string | null
  metadata: JSONObject
  triaged_by: string | null
  triaged_at: string | null
  created_at: string
  updated_at: string
}

export interface RelationClaimListResponse {
  claims: RelationClaimResponse[]
  total: number
  offset: number
  limit: number
}

export interface RelationClaimTriageRequest {
  claim_status: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
}

export interface KernelProvenanceResponse {
  id: string
  research_space_id: string
  source_type: string
  source_ref: string | null
  extraction_run_id: string | null
  mapping_method: string | null
  mapping_confidence: number | null
  agent_model: string | null
  raw_input: JSONObject | null
  created_at: string
  updated_at: string
}

export interface KernelProvenanceListResponse {
  provenance: KernelProvenanceResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelGraphExportResponse {
  nodes: KernelEntityResponse[]
  edges: KernelRelationResponse[]
}

export type KernelGraphSubgraphMode = 'starter' | 'seeded'

export interface KernelGraphSubgraphRequest {
  mode: KernelGraphSubgraphMode
  seed_entity_ids: string[]
  depth?: number
  top_k?: number
  relation_types?: string[] | null
  curation_statuses?: string[] | null
  max_nodes?: number
  max_edges?: number
}

export interface KernelGraphSubgraphMeta {
  mode: KernelGraphSubgraphMode
  seed_entity_ids: string[]
  requested_depth: number
  requested_top_k: number
  pre_cap_node_count: number
  pre_cap_edge_count: number
  truncated_nodes: boolean
  truncated_edges: boolean
}

export interface KernelGraphSubgraphResponse {
  nodes: KernelEntityResponse[]
  edges: KernelRelationResponse[]
  meta: KernelGraphSubgraphMeta
}

export interface PipelineRunRequest {
  source_id: string
  run_id?: string | null
  resume_from_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  force_recover_lock?: boolean
  enrichment_limit?: number
  extraction_limit?: number
  source_type?: string | null
  model_id?: string | null
  shadow_mode?: boolean | null
  graph_seed_entity_ids?: string[] | null
  graph_max_depth?: number
  graph_relation_types?: string[] | null
}

export interface PipelineRunResponse {
  run_id: string
  source_id: string
  research_space_id: string
  started_at: string
  completed_at: string
  status: string
  resume_from_stage: string | null
  ingestion_status: string
  enrichment_status: string
  extraction_status: string
  graph_status: string
  fetched_records: number
  parsed_publications: number
  created_publications: number
  updated_publications: number
  enrichment_processed: number
  enrichment_enriched: number
  enrichment_failed: number
  extraction_processed: number
  extraction_extracted: number
  extraction_failed: number
  graph_requested: number
  graph_processed: number
  graph_persisted_relations: number
  executed_query: string | null
  errors: string[]
  metadata: JSONObject | null
}

export interface PipelineRunCancelResponse {
  run_id: string
  source_id: string
  status: string
  cancelled: boolean
}

export interface SourcePipelineRunsResponse {
  source_id: string
  runs: JSONObject[]
  total: number
}

export interface ArtanaStageProgressSnapshot {
  stage: string
  run_id: string | null
  status: string | null
  percent: number | null
  current_stage: string | null
  completed_stages: string[]
  started_at: string | null
  updated_at: string | null
  eta_seconds: number | null
  candidate_run_ids: string[]
}

export interface SourceWorkflowMonitorResponse {
  source_snapshot: JSONObject
  last_run: JSONObject | null
  pipeline_runs: JSONObject[]
  documents: JSONObject[]
  document_status_counts: Record<string, number>
  extraction_queue: JSONObject[]
  extraction_queue_status_counts: Record<string, number>
  publication_extractions: JSONObject[]
  publication_extraction_status_counts: Record<string, number>
  relation_review: JSONObject
  graph_summary: JSONObject | null
  operational_counters: JSONObject
  artana_progress?: Record<string, ArtanaStageProgressSnapshot>
  warnings: string[]
}

export type SourceWorkflowEventCategory =
  | 'run'
  | 'stage'
  | 'document'
  | 'queue'
  | 'extraction'
  | 'review'
  | 'graph'

export interface SourceWorkflowEvent {
  event_id: string
  source_id: string
  run_id: string | null
  occurred_at: string
  category: SourceWorkflowEventCategory
  stage: string | null
  status: string | null
  message: string
  payload: JSONObject
}

export interface SourceWorkflowEventsResponse {
  source_id: string
  run_id: string | null
  generated_at: string
  events: SourceWorkflowEvent[]
  total: number
  has_more: boolean
}

export interface SourceWorkflowCardStatusPayload {
  last_pipeline_status: string | null
  last_failed_stage: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  pending_paper_count: number
  pending_relation_review_count: number
  extraction_extracted_count: number
  extraction_failed_count: number
  extraction_skipped_count: number
  extraction_timeout_failed_count: number
  graph_edges_delta_last_run: number
  graph_edges_total: number
  artana_progress?: Record<string, ArtanaStageProgressSnapshot>
}

export interface WorkflowEventCardItem {
  event_id: string
  occurred_at: string | null
  category: string | null
  stage: string | null
  status: string | null
  message: string
}

export interface SourceWorkflowStreamBootstrapPayload {
  monitor: SourceWorkflowMonitorResponse
  events: SourceWorkflowEvent[]
  generated_at: string
  run_id: string | null
}

export interface SourceWorkflowStreamSnapshotPayload {
  monitor: SourceWorkflowMonitorResponse
  generated_at: string
  run_id: string | null
}

export interface SourceWorkflowStreamEventsPayload {
  events: SourceWorkflowEvent[]
  generated_at: string
  run_id: string | null
}

export interface SpaceWorkflowSourceCardPayload {
  source_id: string
  workflow_status: SourceWorkflowCardStatusPayload
  events: WorkflowEventCardItem[]
  generated_at: string
}

export interface SpaceWorkflowBootstrapPayload {
  sources: SpaceWorkflowSourceCardPayload[]
  generated_at: string
}

export interface GraphSearchRequest {
  question: string
  max_depth?: number
  top_k?: number
  curation_statuses?: string[] | null
  include_evidence_chains?: boolean
  force_agent?: boolean
}

export interface GraphSearchEvidenceItem {
  source_type: 'tool' | 'db' | 'paper' | 'web' | 'note' | 'api'
  locator: string
  excerpt: string
  relevance: number
}

export interface GraphSearchEvidenceChainItem {
  provenance_id: string | null
  relation_id: string | null
  observation_id: string | null
  evidence_tier: string | null
  confidence: number | null
  evidence_sentence: string | null
  source_ref: string | null
}

export interface GraphSearchResultEntry {
  entity_id: string
  entity_type: string
  display_label: string | null
  relevance_score: number
  matching_observation_ids: string[]
  matching_relation_ids: string[]
  evidence_chain: GraphSearchEvidenceChainItem[]
  explanation: string
  support_summary: string
}

export type GraphSearchDecision = 'generated' | 'fallback' | 'escalate'
export type GraphSearchExecutedPath = 'deterministic' | 'agent' | 'agent_fallback'

export interface GraphSearchResponse {
  confidence_score: number
  rationale: string
  evidence: GraphSearchEvidenceItem[]
  decision: GraphSearchDecision
  research_space_id: string
  original_query: string
  interpreted_intent: string
  query_plan_summary: string
  total_results: number
  results: GraphSearchResultEntry[]
  executed_path: GraphSearchExecutedPath
  warnings: string[]
  agent_run_id: string | null
}

export type SpaceSourceRunStatus = 'completed' | 'skipped' | 'failed'

export interface SpaceSourceIngestionRunResponse {
  source_id: string
  source_name: string
  status: SpaceSourceRunStatus
  message?: string | null
  fetched_records: number
  parsed_publications: number
  created_publications: number
  updated_publications: number
  executed_query?: string | null
}

export interface SpaceRunActiveSourcesResponse {
  total_sources: number
  active_sources: number
  runnable_sources: number
  completed_sources: number
  skipped_sources: number
  failed_sources: number
  runs: SpaceSourceIngestionRunResponse[]
}
