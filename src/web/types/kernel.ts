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
  evidence_tier?: string | null
  provenance_id?: string | null
}

export interface KernelRelationCurationUpdateRequest {
  curation_status: string
}

export interface KernelRelationResponse {
  id: string
  research_space_id: string
  source_id: string
  relation_type: string
  target_id: string

  confidence: number
  evidence_summary: string | null
  evidence_tier: string | null
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

export interface GraphSearchRequest {
  question: string
  max_depth?: number
  top_k?: number
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
