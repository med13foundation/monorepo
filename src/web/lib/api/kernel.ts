import { apiDelete, apiGet, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type {
  KernelEntityCreateRequest,
  KernelEntityListResponse,
  KernelEntityResponse,
  KernelEntityUpdateRequest,
  KernelEntityUpsertResponse,
  KernelGraphExportResponse,
  KernelGraphSubgraphRequest,
  KernelGraphSubgraphResponse,
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
  PipelineRunRequest,
  PipelineRunCancelResponse,
  PipelineRunResponse,
  SourcePipelineRunsResponse,
  SourceWorkflowEventsResponse,
  SourceWorkflowMonitorResponse,
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'

export interface KernelEntityListParams {
  type?: string
  q?: string
  ids?: string[]
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
      ...(params.ids && params.ids.length > 0 ? { ids: params.ids.join(',') } : {}),
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
  node_query?: string
  node_ids?: string[]
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
      ...(params.node_query ? { node_query: params.node_query } : {}),
      ...(params.node_ids && params.node_ids.length > 0
        ? { node_ids: params.node_ids.join(',') }
        : {}),
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

export async function fetchKernelSubgraph(
  spaceId: string,
  payload: KernelGraphSubgraphRequest,
  token?: string,
): Promise<KernelGraphSubgraphResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelSubgraph')
  }
  return apiPost<KernelGraphSubgraphResponse>(
    `/research-spaces/${spaceId}/graph/subgraph`,
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

export async function runSpaceSourcePipeline(
  spaceId: string,
  payload: PipelineRunRequest,
  token?: string,
): Promise<PipelineRunResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runSpaceSourcePipeline')
  }
  return apiPost<PipelineRunResponse>(
    `/research-spaces/${spaceId}/pipeline/run`,
    payload,
    {
      token,
      timeout: 0,
    },
  )
}

export async function cancelSpaceSourcePipelineRun(
  spaceId: string,
  sourceId: string,
  runId: string,
  token?: string,
): Promise<PipelineRunCancelResponse> {
  if (!token) {
    throw new Error('Authentication token is required for cancelSpaceSourcePipelineRun')
  }
  return apiPost<PipelineRunCancelResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${runId}/cancel`,
    {},
    { token },
  )
}

export interface SourcePipelineRunsParams {
  limit?: number
}

export async function fetchSourcePipelineRuns(
  spaceId: string,
  sourceId: string,
  params: SourcePipelineRunsParams = {},
  token?: string,
): Promise<SourcePipelineRunsResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourcePipelineRuns')
  }
  const options: ApiRequestOptions<SourcePipelineRunsResponse> = {
    token,
    params: {
      limit: params.limit ?? 50,
    },
  }
  return apiGet<SourcePipelineRunsResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs`,
    options,
  )
}

export interface SourceWorkflowMonitorParams {
  run_id?: string
  limit?: number
  include_graph?: boolean
}

export async function fetchSourceWorkflowMonitor(
  spaceId: string,
  sourceId: string,
  params: SourceWorkflowMonitorParams = {},
  token?: string,
): Promise<SourceWorkflowMonitorResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceWorkflowMonitor')
  }
  const options: ApiRequestOptions<SourceWorkflowMonitorResponse> = {
    token,
    params: {
      ...(params.run_id ? { run_id: params.run_id } : {}),
      limit: params.limit ?? 50,
      include_graph: params.include_graph ?? true,
    },
  }
  return apiGet<SourceWorkflowMonitorResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/workflow-monitor`,
    options,
  )
}

export interface SourceWorkflowEventsParams {
  run_id?: string
  limit?: number
  since?: string
}

export async function fetchSourceWorkflowEvents(
  spaceId: string,
  sourceId: string,
  params: SourceWorkflowEventsParams = {},
  token?: string,
): Promise<SourceWorkflowEventsResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceWorkflowEvents')
  }
  const options: ApiRequestOptions<SourceWorkflowEventsResponse> = {
    token,
    params: {
      ...(params.run_id ? { run_id: params.run_id } : {}),
      ...(params.since ? { since: params.since } : {}),
      limit: params.limit ?? 200,
    },
  }
  return apiGet<SourceWorkflowEventsResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/workflow-events`,
    options,
  )
}
