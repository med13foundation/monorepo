import { apiGet, apiPost, type ApiRequestOptions } from '@/lib/api/client'
import type {
  EntityResolutionPolicyListResponse,
  RelationConstraintListResponse,
  TransformRegistryListResponse,
  VariableDefinitionCreateRequest,
  VariableDefinitionListResponse,
  VariableDefinitionResponse,
} from '@/types/dictionary'

export interface DictionaryVariablesListParams {
  domain_context?: string
  data_type?: string
}

export async function fetchDictionaryVariables(
  params: DictionaryVariablesListParams = {},
  token?: string,
): Promise<VariableDefinitionListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDictionaryVariables')
  }

  const options: ApiRequestOptions<VariableDefinitionListResponse> = {
    token,
    params: {
      ...(params.domain_context ? { domain_context: params.domain_context } : {}),
      ...(params.data_type ? { data_type: params.data_type } : {}),
    },
  }

  return apiGet<VariableDefinitionListResponse>('/admin/dictionary/variables', options)
}

export async function createDictionaryVariable(
  payload: VariableDefinitionCreateRequest,
  token?: string,
): Promise<VariableDefinitionResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createDictionaryVariable')
  }
  return apiPost<VariableDefinitionResponse>('/admin/dictionary/variables', payload, { token })
}

export async function fetchDictionaryTransforms(
  params: { status?: string } = {},
  token?: string,
): Promise<TransformRegistryListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDictionaryTransforms')
  }

  const options: ApiRequestOptions<TransformRegistryListResponse> = {
    token,
    params: {
      status: params.status ?? 'ACTIVE',
    },
  }

  return apiGet<TransformRegistryListResponse>('/admin/dictionary/transforms', options)
}

export async function fetchDictionaryResolutionPolicies(
  token?: string,
): Promise<EntityResolutionPolicyListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDictionaryResolutionPolicies')
  }
  return apiGet<EntityResolutionPolicyListResponse>('/admin/dictionary/resolution-policies', { token })
}

export async function fetchDictionaryRelationConstraints(
  params: { source_type?: string; relation_type?: string } = {},
  token?: string,
): Promise<RelationConstraintListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDictionaryRelationConstraints')
  }

  const options: ApiRequestOptions<RelationConstraintListResponse> = {
    token,
    params: {
      ...(params.source_type ? { source_type: params.source_type } : {}),
      ...(params.relation_type ? { relation_type: params.relation_type } : {}),
    },
  }

  return apiGet<RelationConstraintListResponse>('/admin/dictionary/relation-constraints', options)
}
