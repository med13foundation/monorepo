"use server"

import { revalidatePath } from 'next/cache'
import {
  runAllActiveSpaceSourcesIngestion,
  runSingleSpaceSourceIngestion,
} from '@/lib/api/kernel'
import type {
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
