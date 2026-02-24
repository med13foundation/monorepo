"use server"

import { revalidatePath } from 'next/cache'
import {
  runSpaceSourcePipeline,
  runAllActiveSpaceSourcesIngestion,
  runSingleSpaceSourceIngestion,
} from '@/lib/api/kernel'
import type {
  PipelineRunResponse,
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateSpaceKernelViews(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/ingest`)
  revalidatePath(`/spaces/${spaceId}/observations`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}/data-sources`)
  revalidatePath(`/spaces/${spaceId}`)
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
    source_type?: string | null
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
    const response = await runSpaceSourcePipeline(
      spaceId,
      {
        source_id: sourceId,
        source_type: options.source_type ?? undefined,
        model_id: options.model_id ?? undefined,
        enrichment_limit: smokeMode ? 5 : (options.enrichment_limit ?? 25),
        extraction_limit: smokeMode ? 5 : (options.extraction_limit ?? 25),
        graph_max_depth: options.graph_max_depth ?? 2,
      },
      token,
    )
    revalidateSpaceKernelViews(spaceId)
    revalidatePath(`/spaces/${spaceId}/data-sources/${sourceId}/workflow`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runSpaceSourcePipeline failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run full pipeline for source'),
    }
  }
}
