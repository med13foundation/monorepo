"use server"

import { revalidatePath } from 'next/cache'
import {
  createStatement,
  deleteStatement,
  promoteStatement,
  updateStatement,
} from '@/lib/api/statements'
import type { Mechanism } from '@/types/mechanisms'
import type {
  Statement,
  StatementCreateRequest,
  StatementUpdateRequest,
} from '@/types/statements'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateStatements(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
}

export async function createStatementAction(
  spaceId: string,
  payload: StatementCreateRequest,
): Promise<ActionResult<Statement>> {
  try {
    const token = await requireAccessToken()
    const response = await createStatement(spaceId, payload, token)
    revalidateStatements(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createStatement failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create statement'),
    }
  }
}

export async function updateStatementAction(
  spaceId: string,
  statementId: number,
  payload: StatementUpdateRequest,
): Promise<ActionResult<Statement>> {
  try {
    const token = await requireAccessToken()
    const response = await updateStatement(spaceId, statementId, payload, token)
    revalidateStatements(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateStatement failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update statement'),
    }
  }
}

export async function deleteStatementAction(
  spaceId: string,
  statementId: number,
): Promise<ActionResult<{ message: string }>> {
  try {
    const token = await requireAccessToken()
    const response = await deleteStatement(spaceId, statementId, token)
    revalidateStatements(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteStatement failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete statement'),
    }
  }
}

export async function promoteStatementAction(
  spaceId: string,
  statementId: number,
): Promise<ActionResult<Mechanism>> {
  try {
    const token = await requireAccessToken()
    const response = await promoteStatement(spaceId, statementId, token)
    revalidateStatements(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] promoteStatement failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to promote statement'),
    }
  }
}
