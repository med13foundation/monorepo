import { apiDelete, apiGet, apiPatch, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type {
  KernelEntityEmbeddingRefreshRequest,
  KernelEntityEmbeddingRefreshResponse,
  KernelEntityCreateRequest,
  KernelEntityListResponse,
  KernelEntityResponse,
  KernelEntitySimilarityListResponse,
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
  ClaimEvidenceListResponse,
  CreateManualHypothesisRequest,
  GenerateHypothesesRequest,
  GenerateHypothesesResponse,
  HypothesisListResponse,
  HypothesisResponse,
  KernelProvenanceListResponse,
  KernelProvenanceResponse,
  KernelRelationCreateRequest,
  KernelRelationSuggestionListResponse,
  KernelRelationSuggestionRequest,
  RelationConflictListResponse,
  RelationClaimListResponse,
  RelationClaimResponse,
  RelationClaimTriageRequest,
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

export interface KernelEntitySimilarParams {
  limit?: number
  min_similarity?: number
  target_entity_types?: string[]
}

export async function fetchKernelSimilarEntities(
  spaceId: string,
  entityId: string,
  params: KernelEntitySimilarParams = {},
  token?: string,
): Promise<KernelEntitySimilarityListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelSimilarEntities')
  }

  const options: ApiRequestOptions<KernelEntitySimilarityListResponse> = {
    token,
    params: {
      limit: params.limit ?? 20,
      min_similarity: params.min_similarity ?? 0.72,
      ...(params.target_entity_types && params.target_entity_types.length > 0
        ? { target_entity_types: params.target_entity_types.join(',') }
        : {}),
    },
  }

  return apiGet<KernelEntitySimilarityListResponse>(
    `/research-spaces/${spaceId}/entities/${entityId}/similar`,
    options,
  )
}

export async function refreshKernelEntityEmbeddings(
  spaceId: string,
  payload: KernelEntityEmbeddingRefreshRequest,
  token?: string,
): Promise<KernelEntityEmbeddingRefreshResponse> {
  if (!token) {
    throw new Error('Authentication token is required for refreshKernelEntityEmbeddings')
  }
  return apiPost<KernelEntityEmbeddingRefreshResponse>(
    `/research-spaces/${spaceId}/entities/embeddings/refresh`,
    payload,
    { token },
  )
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
  validation_state?: string
  source_document_id?: string
  certainty_band?: 'HIGH' | 'MEDIUM' | 'LOW'
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
      ...(params.validation_state ? { validation_state: params.validation_state } : {}),
      ...(params.source_document_id ? { source_document_id: params.source_document_id } : {}),
      ...(params.certainty_band ? { certainty_band: params.certainty_band } : {}),
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

export async function suggestKernelRelations(
  spaceId: string,
  payload: KernelRelationSuggestionRequest,
  token?: string,
): Promise<KernelRelationSuggestionListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for suggestKernelRelations')
  }
  return apiPost<KernelRelationSuggestionListResponse>(
    `/research-spaces/${spaceId}/graph/relation-suggestions`,
    payload,
    { token },
  )
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

export interface RelationClaimListParams {
  claim_status?: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
  validation_state?: string
  persistability?: 'PERSISTABLE' | 'NON_PERSISTABLE'
  polarity?: 'SUPPORT' | 'REFUTE' | 'UNCERTAIN' | 'HYPOTHESIS'
  source_document_id?: string
  relation_type?: string
  linked_relation_id?: string
  certainty_band?: 'HIGH' | 'MEDIUM' | 'LOW'
  offset?: number
  limit?: number
}

export async function fetchRelationClaims(
  spaceId: string,
  params: RelationClaimListParams = {},
  token?: string,
): Promise<RelationClaimListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRelationClaims')
  }

  const options: ApiRequestOptions<RelationClaimListResponse> = {
    token,
    params: {
      ...(params.claim_status ? { claim_status: params.claim_status } : {}),
      ...(params.validation_state ? { validation_state: params.validation_state } : {}),
      ...(params.persistability ? { persistability: params.persistability } : {}),
      ...(params.polarity ? { polarity: params.polarity } : {}),
      ...(params.source_document_id ? { source_document_id: params.source_document_id } : {}),
      ...(params.relation_type ? { relation_type: params.relation_type } : {}),
      ...(params.linked_relation_id ? { linked_relation_id: params.linked_relation_id } : {}),
      ...(params.certainty_band ? { certainty_band: params.certainty_band } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<RelationClaimListResponse>(
    `/research-spaces/${spaceId}/relation-claims`,
    options,
  )
}

export interface HypothesisListParams {
  offset?: number
  limit?: number
}

export async function fetchHypotheses(
  spaceId: string,
  params: HypothesisListParams = {},
  token?: string,
): Promise<HypothesisListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchHypotheses')
  }
  const options: ApiRequestOptions<HypothesisListResponse> = {
    token,
    params: {
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }
  return apiGet<HypothesisListResponse>(
    `/research-spaces/${spaceId}/hypotheses`,
    options,
  )
}

export async function createManualHypothesis(
  spaceId: string,
  payload: CreateManualHypothesisRequest,
  token?: string,
): Promise<HypothesisResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createManualHypothesis')
  }
  return apiPost<HypothesisResponse>(
    `/research-spaces/${spaceId}/hypotheses/manual`,
    payload,
    { token },
  )
}

export async function generateHypotheses(
  spaceId: string,
  payload: GenerateHypothesesRequest,
  token?: string,
): Promise<GenerateHypothesesResponse> {
  if (!token) {
    throw new Error('Authentication token is required for generateHypotheses')
  }
  return apiPost<GenerateHypothesesResponse>(
    `/research-spaces/${spaceId}/hypotheses/generate`,
    payload,
    { token, timeout: 0 },
  )
}

export async function fetchRelationClaimEvidence(
  spaceId: string,
  claimId: string,
  token?: string,
): Promise<ClaimEvidenceListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRelationClaimEvidence')
  }
  return apiGet<ClaimEvidenceListResponse>(
    `/research-spaces/${spaceId}/relation-claims/${claimId}/evidence`,
    { token },
  )
}

export interface RelationConflictListParams {
  offset?: number
  limit?: number
}

export async function fetchRelationConflicts(
  spaceId: string,
  params: RelationConflictListParams = {},
  token?: string,
): Promise<RelationConflictListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRelationConflicts')
  }
  const options: ApiRequestOptions<RelationConflictListResponse> = {
    token,
    params: {
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }
  return apiGet<RelationConflictListResponse>(
    `/research-spaces/${spaceId}/relations/conflicts`,
    options,
  )
}

export async function updateRelationClaimStatus(
  spaceId: string,
  claimId: string,
  payload: RelationClaimTriageRequest,
  token?: string,
): Promise<RelationClaimResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateRelationClaimStatus')
  }
  return apiPatch<RelationClaimResponse>(
    `/research-spaces/${spaceId}/relation-claims/${claimId}`,
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
