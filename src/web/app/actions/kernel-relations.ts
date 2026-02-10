"use server"

import { revalidatePath } from 'next/cache'
import { updateKernelRelationCurationStatus } from '@/lib/api/kernel'
import type { KernelRelationResponse } from '@/types/kernel'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateCuration(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
}

export async function updateKernelRelationStatusAction(
  spaceId: string,
  relationId: string,
  curationStatus: string,
): Promise<ActionResult<KernelRelationResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await updateKernelRelationCurationStatus(
      spaceId,
      relationId,
      { curation_status: curationStatus },
      token,
    )
    revalidateCuration(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateKernelRelationStatus failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update relation status'),
    }
  }
}
