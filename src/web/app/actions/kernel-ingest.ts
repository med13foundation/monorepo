"use server"

import { revalidatePath } from 'next/cache'
import {
  cancelSpaceSourcePipelineRun,
  fetchSourceWorkflowMonitor,
  runSpaceSourcePipeline,
  runAllActiveSpaceSourcesIngestion,
  runSingleSpaceSourceIngestion,
} from '@/lib/api/kernel'
import type {
  PipelineRunCancelResponse,
  PipelineRunResponse,
  SourceWorkflowMonitorResponse,
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

export interface WorkflowCardStatusPayload {
  last_pipeline_status: string | null
  last_failed_stage: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  pending_paper_count: number
  pending_relation_review_count: number
  graph_edges_delta_last_run: number
  graph_edges_total: number
}

function toNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

function revalidateSpaceKernelViews(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/ingest`)
  revalidatePath(`/spaces/${spaceId}/observations`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}/data-sources`)
  revalidatePath(`/spaces/${spaceId}`)
}

const PIPELINE_STAGE_ORDER = [
  'ingestion',
  'enrichment',
  'extraction',
  'graph',
] as const

type PipelineStage = (typeof PIPELINE_STAGE_ORDER)[number]

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function extractLastFailedStage(monitor: SourceWorkflowMonitorResponse): PipelineStage | null {
  const lastRun = asObject(monitor.last_run)
  const runStatus = typeof lastRun.status === 'string' ? lastRun.status : null
  if (runStatus !== 'failed') {
    return null
  }
  const stageStatuses = asObject(lastRun.stage_statuses)
  for (const stage of PIPELINE_STAGE_ORDER) {
    if (stageStatuses[stage] === 'failed') {
      return stage
    }
  }
  const stageErrors = asObject(lastRun.stage_errors)
  for (const stage of PIPELINE_STAGE_ORDER) {
    if (typeof stageErrors[stage] === 'string' && stageErrors[stage].trim().length > 0) {
      return stage
    }
  }
  return 'ingestion'
}

export async function runAllActiveSpaceSourcesIngestionAction(
  spaceId: string,
): Promise<ActionResult<SpaceRunActiveSourcesResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await runAllActiveSpaceSourcesIngestion(spaceId, token)
    revalidateSpaceKernelViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runAllActiveSpaceSourcesIngestion failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run ingestion for active sources'),
    }
  }
}

export async function runSingleSpaceSourceIngestionAction(
  spaceId: string,
  sourceId: string,
): Promise<ActionResult<SpaceSourceIngestionRunResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await runSingleSpaceSourceIngestion(spaceId, sourceId, token)
    revalidateSpaceKernelViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runSingleSpaceSourceIngestion failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run ingestion for source'),
    }
  }
}

export async function runSpaceSourcePipelineAction(
  spaceId: string,
  sourceId: string,
  options: {
    resume_from_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
    force_recover_lock?: boolean
    source_type?: string | null
    run_id?: string | null
    model_id?: string | null
    enrichment_limit?: number
    extraction_limit?: number
    graph_max_depth?: number
    smoke_mode?: boolean
  } = {},
): Promise<ActionResult<PipelineRunResponse>> {
  try {
    const token = await requireAccessToken()
    const smokeMode = options.smoke_mode === true
    const payload = {
      source_id: sourceId,
      run_id: options.run_id ?? undefined,
      resume_from_stage: options.resume_from_stage ?? undefined,
      force_recover_lock: options.force_recover_lock === true ? true : undefined,
      source_type: options.source_type ?? undefined,
      model_id: options.model_id ?? undefined,
      enrichment_limit: smokeMode ? 5 : (options.enrichment_limit ?? 25),
      extraction_limit: smokeMode ? 5 : (options.extraction_limit ?? 25),
      graph_max_depth: options.graph_max_depth ?? 2,
    }
    if (process.env.NODE_ENV !== 'test') {
      console.info('[ServerAction] runSpaceSourcePipeline payload', {
        spaceId,
        sourceIdType: typeof sourceId,
        sourceId,
        payload,
      })
    }
    const response = await runSpaceSourcePipeline(
      spaceId,
      payload,
      token,
    )
    revalidateSpaceKernelViews(spaceId)
    revalidatePath(`/spaces/${spaceId}/data-sources/${sourceId}/workflow`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runSpaceSourcePipeline failed:', {
        error,
        spaceId,
        sourceId,
      })
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run full pipeline for source'),
    }
  }
}

export async function cancelSpaceSourcePipelineRunAction(
  spaceId: string,
  sourceId: string,
  runId: string,
): Promise<ActionResult<PipelineRunCancelResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await cancelSpaceSourcePipelineRun(
      spaceId,
      sourceId,
      runId,
      token,
    )
    revalidateSpaceKernelViews(spaceId)
    revalidatePath(`/spaces/${spaceId}/data-sources/${sourceId}/workflow`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] cancelSpaceSourcePipelineRun failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to cancel pipeline run for source'),
    }
  }
}

export async function fetchSourceWorkflowCardStatusAction(
  spaceId: string,
  sourceId: string,
): Promise<ActionResult<WorkflowCardStatusPayload>> {
  try {
    const token = await requireAccessToken()
    const monitor: SourceWorkflowMonitorResponse = await fetchSourceWorkflowMonitor(
      spaceId,
      sourceId,
      { limit: 5, include_graph: true },
      token,
    )
    const counters = monitor.operational_counters ?? {}
    return {
      success: true,
      data: {
        last_pipeline_status:
          typeof counters.last_pipeline_status === 'string'
            ? counters.last_pipeline_status
            : null,
        last_failed_stage: extractLastFailedStage(monitor),
        pending_paper_count: toNumber(counters.pending_paper_count),
        pending_relation_review_count: toNumber(counters.pending_relation_review_count),
        graph_edges_delta_last_run: toNumber(counters.graph_edges_delta_last_run),
        graph_edges_total: toNumber(counters.graph_edges_total),
      },
    }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchSourceWorkflowCardStatus failed:', {
        error,
        spaceId,
        sourceId,
      })
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to fetch source workflow counters'),
    }
  }
}
