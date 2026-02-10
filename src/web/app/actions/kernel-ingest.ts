"use server"

import { revalidatePath } from 'next/cache'
import { ingestKernelRecords } from '@/lib/api/kernel'
import type { KernelIngestRequest, KernelIngestResponse } from '@/types/kernel'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateSpaceKernelViews(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/observations`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}`)
}

export async function ingestKernelRecordsAction(
  spaceId: string,
  payload: KernelIngestRequest,
): Promise<ActionResult<KernelIngestResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await ingestKernelRecords(spaceId, payload, token)
    revalidateSpaceKernelViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] ingestKernelRecords failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to ingest records'),
    }
  }
}
