import { apiGet, apiPatch, apiPost, type ApiRequestOptions } from '@/lib/api/client'
import type {
  DictionaryEntityTypeListResponse,
  DictionaryEntityTypeResponse,
  DictionaryMergeRequest,
  DictionaryRelationTypeListResponse,
  DictionaryRelationTypeResponse,
  DictionaryRevokeRequest,
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

export async function fetchDictionaryEntityTypes(
  params: { domain_context?: string } = {},
  token?: string,
): Promise<DictionaryEntityTypeListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDictionaryEntityTypes')
  }

  const options: ApiRequestOptions<DictionaryEntityTypeListResponse> = {
    token,
    params: {
      ...(params.domain_context ? { domain_context: params.domain_context } : {}),
    },
  }

  return apiGet<DictionaryEntityTypeListResponse>('/admin/dictionary/entity-types', options)
}

export async function fetchDictionaryRelationTypes(
  params: { domain_context?: string } = {},
  token?: string,
): Promise<DictionaryRelationTypeListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDictionaryRelationTypes')
  }

  const options: ApiRequestOptions<DictionaryRelationTypeListResponse> = {
    token,
    params: {
      ...(params.domain_context ? { domain_context: params.domain_context } : {}),
    },
  }

  return apiGet<DictionaryRelationTypeListResponse>('/admin/dictionary/relation-types', options)
}

export async function revokeDictionaryVariable(
  variableId: string,
  payload: DictionaryRevokeRequest,
  token?: string,
): Promise<VariableDefinitionResponse> {
  if (!token) {
    throw new Error('Authentication token is required for revokeDictionaryVariable')
  }

  return apiPost<VariableDefinitionResponse>(
    `/admin/dictionary/variables/${variableId}/revoke`,
    payload,
    { token },
  )
}

export async function mergeDictionaryVariable(
  variableId: string,
  payload: DictionaryMergeRequest,
  token?: string,
): Promise<VariableDefinitionResponse> {
  if (!token) {
    throw new Error('Authentication token is required for mergeDictionaryVariable')
  }

  return apiPost<VariableDefinitionResponse>(
    `/admin/dictionary/variables/${variableId}/merge`,
    payload,
    { token },
  )
}

export async function setDictionaryVariableReviewStatus(
  variableId: string,
  payload: { review_status: 'ACTIVE' | 'PENDING_REVIEW' | 'REVOKED'; revocation_reason?: string },
  token?: string,
): Promise<VariableDefinitionResponse> {
  if (!token) {
    throw new Error('Authentication token is required for setDictionaryVariableReviewStatus')
  }

  return apiPatch<VariableDefinitionResponse>(
    `/admin/dictionary/variables/${variableId}/review-status`,
    payload,
    { token },
  )
}

export async function revokeDictionaryEntityType(
  entityTypeId: string,
  payload: DictionaryRevokeRequest,
  token?: string,
): Promise<DictionaryEntityTypeResponse> {
  if (!token) {
    throw new Error('Authentication token is required for revokeDictionaryEntityType')
  }

  return apiPost<DictionaryEntityTypeResponse>(
    `/admin/dictionary/entity-types/${entityTypeId}/revoke`,
    payload,
    { token },
  )
}

export async function mergeDictionaryEntityType(
  entityTypeId: string,
  payload: DictionaryMergeRequest,
  token?: string,
): Promise<DictionaryEntityTypeResponse> {
  if (!token) {
    throw new Error('Authentication token is required for mergeDictionaryEntityType')
  }

  return apiPost<DictionaryEntityTypeResponse>(
    `/admin/dictionary/entity-types/${entityTypeId}/merge`,
    payload,
    { token },
  )
}

export async function revokeDictionaryRelationType(
  relationTypeId: string,
  payload: DictionaryRevokeRequest,
  token?: string,
): Promise<DictionaryRelationTypeResponse> {
  if (!token) {
    throw new Error('Authentication token is required for revokeDictionaryRelationType')
  }

  return apiPost<DictionaryRelationTypeResponse>(
    `/admin/dictionary/relation-types/${relationTypeId}/revoke`,
    payload,
    { token },
  )
}

export async function mergeDictionaryRelationType(
  relationTypeId: string,
  payload: DictionaryMergeRequest,
  token?: string,
): Promise<DictionaryRelationTypeResponse> {
  if (!token) {
    throw new Error('Authentication token is required for mergeDictionaryRelationType')
  }

  return apiPost<DictionaryRelationTypeResponse>(
    `/admin/dictionary/relation-types/${relationTypeId}/merge`,
    payload,
    { token },
  )
}
