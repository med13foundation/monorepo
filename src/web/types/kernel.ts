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

export interface KernelIngestRecordRequest {
  source_id: string
  data: JSONObject
  metadata?: JSONObject
}

export interface KernelIngestRequest {
  entity_type?: string | null
  record_type?: string | null
  records: KernelIngestRecordRequest[]
}

export interface KernelIngestResponse {
  success: boolean
  entities_created: number
  observations_created: number
  errors: string[]
}
