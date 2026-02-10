"use server"

import { revalidatePath } from 'next/cache'
import {
  createMechanism,
  deleteMechanism,
  updateMechanism,
} from '@/lib/api/mechanisms'
import type {
  Mechanism,
  MechanismCreateRequest,
  MechanismUpdateRequest,
} from '@/types/mechanisms'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateMechanisms(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
}

export async function createMechanismAction(
  spaceId: string,
  payload: MechanismCreateRequest,
): Promise<ActionResult<Mechanism>> {
  try {
    const token = await requireAccessToken()
    const response = await createMechanism(spaceId, payload, token)
    revalidateMechanisms(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createMechanism failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create mechanism'),
    }
  }
}

export async function updateMechanismAction(
  spaceId: string,
  mechanismId: number,
  payload: MechanismUpdateRequest,
): Promise<ActionResult<Mechanism>> {
  try {
    const token = await requireAccessToken()
    const response = await updateMechanism(spaceId, mechanismId, payload, token)
    revalidateMechanisms(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateMechanism failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update mechanism'),
    }
  }
}

export async function deleteMechanismAction(
  spaceId: string,
  mechanismId: number,
): Promise<ActionResult<{ message: string }>> {
  try {
    const token = await requireAccessToken()
    const response = await deleteMechanism(spaceId, mechanismId, token)
    revalidateMechanisms(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteMechanism failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete mechanism'),
    }
  }
}
