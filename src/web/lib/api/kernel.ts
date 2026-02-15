import { apiDelete, apiGet, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type {
  KernelEntityCreateRequest,
  KernelEntityListResponse,
  KernelEntityResponse,
  KernelEntityUpdateRequest,
  KernelEntityUpsertResponse,
  KernelGraphExportResponse,
  GraphSearchRequest,
  GraphSearchResponse,
  KernelObservationCreateRequest,
  KernelObservationListResponse,
  KernelObservationResponse,
  KernelProvenanceListResponse,
  KernelProvenanceResponse,
  KernelRelationCreateRequest,
  KernelRelationCurationUpdateRequest,
  KernelRelationListResponse,
  KernelRelationResponse,
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'

export interface KernelEntityListParams {
  type?: string
  q?: string
  offset?: number
  limit?: number
}

export async function fetchKernelEntities(
  spaceId: string,
  params: KernelEntityListParams,
  token?: string,
): Promise<KernelEntityListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelEntities')
  }

  const options: ApiRequestOptions<KernelEntityListResponse> = {
    token,
    params: {
      ...(params.type ? { type: params.type } : {}),
      ...(params.q ? { q: params.q } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelEntityListResponse>(`/research-spaces/${spaceId}/entities`, options)
}

export async function createKernelEntity(
  spaceId: string,
  payload: KernelEntityCreateRequest,
  token?: string,
): Promise<KernelEntityUpsertResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createKernelEntity')
  }
  return apiPost<KernelEntityUpsertResponse>(
    `/research-spaces/${spaceId}/entities`,
    payload,
    { token },
  )
}

export async function fetchKernelEntity(
  spaceId: string,
  entityId: string,
  token?: string,
): Promise<KernelEntityResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelEntity')
  }
  return apiGet<KernelEntityResponse>(`/research-spaces/${spaceId}/entities/${entityId}`, { token })
}

export async function updateKernelEntity(
  spaceId: string,
  entityId: string,
  payload: KernelEntityUpdateRequest,
  token?: string,
): Promise<KernelEntityResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateKernelEntity')
  }
  return apiPut<KernelEntityResponse>(
    `/research-spaces/${spaceId}/entities/${entityId}`,
    payload,
    { token },
  )
}

export async function deleteKernelEntity(
  spaceId: string,
  entityId: string,
  token?: string,
): Promise<void> {
  if (!token) {
    throw new Error('Authentication token is required for deleteKernelEntity')
  }
  await apiDelete<void>(`/research-spaces/${spaceId}/entities/${entityId}`, { token })
}

export interface KernelObservationListParams {
  subject_id?: string
  variable_id?: string
  offset?: number
  limit?: number
}

export async function fetchKernelObservations(
  spaceId: string,
  params: KernelObservationListParams = {},
  token?: string,
): Promise<KernelObservationListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelObservations')
  }

  const options: ApiRequestOptions<KernelObservationListResponse> = {
    token,
    params: {
      ...(params.subject_id ? { subject_id: params.subject_id } : {}),
      ...(params.variable_id ? { variable_id: params.variable_id } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelObservationListResponse>(
    `/research-spaces/${spaceId}/observations`,
    options,
  )
}

export async function createKernelObservation(
  spaceId: string,
  payload: KernelObservationCreateRequest,
  token?: string,
): Promise<KernelObservationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createKernelObservation')
  }
  return apiPost<KernelObservationResponse>(
    `/research-spaces/${spaceId}/observations`,
    payload,
    { token },
  )
}

export async function fetchKernelObservation(
  spaceId: string,
  observationId: string,
  token?: string,
): Promise<KernelObservationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelObservation')
  }
  return apiGet<KernelObservationResponse>(
    `/research-spaces/${spaceId}/observations/${observationId}`,
    { token },
  )
}

export interface KernelRelationListParams {
  relation_type?: string
  curation_status?: string
  offset?: number
  limit?: number
}

export async function fetchKernelRelations(
  spaceId: string,
  params: KernelRelationListParams = {},
  token?: string,
): Promise<KernelRelationListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelRelations')
  }

  const options: ApiRequestOptions<KernelRelationListResponse> = {
    token,
    params: {
      ...(params.relation_type ? { relation_type: params.relation_type } : {}),
      ...(params.curation_status ? { curation_status: params.curation_status } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelRelationListResponse>(`/research-spaces/${spaceId}/relations`, options)
}

export async function createKernelRelation(
  spaceId: string,
  payload: KernelRelationCreateRequest,
  token?: string,
): Promise<KernelRelationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createKernelRelation')
  }
  return apiPost<KernelRelationResponse>(`/research-spaces/${spaceId}/relations`, payload, { token })
}

export async function updateKernelRelationCurationStatus(
  spaceId: string,
  relationId: string,
  payload: KernelRelationCurationUpdateRequest,
  token?: string,
): Promise<KernelRelationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateKernelRelationCurationStatus')
  }
  return apiPut<KernelRelationResponse>(
    `/research-spaces/${spaceId}/relations/${relationId}`,
    payload,
    { token },
  )
}

export async function fetchKernelGraphExport(
  spaceId: string,
  token?: string,
): Promise<KernelGraphExportResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelGraphExport')
  }
  return apiGet<KernelGraphExportResponse>(`/research-spaces/${spaceId}/graph/export`, { token })
}

export async function searchKernelGraph(
  spaceId: string,
  payload: GraphSearchRequest,
  token?: string,
): Promise<GraphSearchResponse> {
  if (!token) {
    throw new Error('Authentication token is required for searchKernelGraph')
  }
  return apiPost<GraphSearchResponse>(
    `/research-spaces/${spaceId}/graph/search`,
    payload,
    { token },
  )
}

export async function fetchKernelNeighborhood(
  spaceId: string,
  entityId: string,
  depth: number,
  token?: string,
): Promise<KernelGraphExportResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelNeighborhood')
  }
  const options: ApiRequestOptions<KernelGraphExportResponse> = {
    token,
    params: { depth },
  }
  return apiGet<KernelGraphExportResponse>(
    `/research-spaces/${spaceId}/graph/neighborhood/${entityId}`,
    options,
  )
}

export interface KernelProvenanceListParams {
  source_type?: string
  offset?: number
  limit?: number
}

export async function fetchKernelProvenance(
  spaceId: string,
  params: KernelProvenanceListParams = {},
  token?: string,
): Promise<KernelProvenanceListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelProvenance')
  }

  const options: ApiRequestOptions<KernelProvenanceListResponse> = {
    token,
    params: {
      ...(params.source_type ? { source_type: params.source_type } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelProvenanceListResponse>(`/research-spaces/${spaceId}/provenance`, options)
}

export async function fetchKernelProvenanceRecord(
  spaceId: string,
  provenanceId: string,
  token?: string,
): Promise<KernelProvenanceResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelProvenanceRecord')
  }
  return apiGet<KernelProvenanceResponse>(
    `/research-spaces/${spaceId}/provenance/${provenanceId}`,
    { token },
  )
}

export async function runAllActiveSpaceSourcesIngestion(
  spaceId: string,
  token?: string,
): Promise<SpaceRunActiveSourcesResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runAllActiveSpaceSourcesIngestion')
  }
  return apiPost<SpaceRunActiveSourcesResponse>(
    `/research-spaces/${spaceId}/ingest/run`,
    {},
    { token },
  )
}

export async function runSingleSpaceSourceIngestion(
  spaceId: string,
  sourceId: string,
  token?: string,
): Promise<SpaceSourceIngestionRunResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runSingleSpaceSourceIngestion')
  }
  return apiPost<SpaceSourceIngestionRunResponse>(
    `/research-spaces/${spaceId}/ingest/sources/${sourceId}/run`,
    {},
    { token },
  )
}
