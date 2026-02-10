import type { JSONObject } from '@/types/generated'

export type KernelDataType =
  | 'INTEGER'
  | 'FLOAT'
  | 'STRING'
  | 'DATE'
  | 'CODED'
  | 'BOOLEAN'
  | 'JSON'

export type KernelSensitivity = 'PUBLIC' | 'INTERNAL' | 'PHI'

export interface VariableDefinitionCreateRequest {
  id: string
  canonical_name: string
  display_name: string
  data_type: KernelDataType
  domain_context?: string
  sensitivity?: KernelSensitivity
  preferred_unit?: string | null
  constraints?: JSONObject
  description?: string | null
}

export interface VariableDefinitionResponse {
  id: string
  canonical_name: string
  display_name: string
  data_type: KernelDataType
  preferred_unit: string | null
  constraints: JSONObject
  domain_context: string
  sensitivity: KernelSensitivity
  description: string | null
  created_at: string
  updated_at: string
}

export interface VariableDefinitionListResponse {
  variables: VariableDefinitionResponse[]
  total: number
}

export interface TransformRegistryResponse {
  id: string
  input_unit: string
  output_unit: string
  implementation_ref: string
  status: string
  created_at: string
  updated_at: string
}

export interface TransformRegistryListResponse {
  transforms: TransformRegistryResponse[]
  total: number
}

export interface EntityResolutionPolicyResponse {
  entity_type: string
  policy_strategy: string
  required_anchors: string[]
  auto_merge_threshold: number
  created_at: string
  updated_at: string
}

export interface EntityResolutionPolicyListResponse {
  policies: EntityResolutionPolicyResponse[]
  total: number
}

export interface RelationConstraintResponse {
  id: number
  source_type: string
  relation_type: string
  target_type: string
  is_allowed: boolean
  requires_evidence: boolean
  created_at: string
  updated_at: string
}

export interface RelationConstraintListResponse {
  constraints: RelationConstraintResponse[]
  total: number
}
