import { apiDelete, apiGet, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type { PaginatedResponse } from '@/types/generated'
import type { Mechanism } from '@/types/mechanisms'
import type {
  Statement,
  StatementCreateRequest,
  StatementUpdateRequest,
} from '@/types/statements'

export interface StatementListParams {
  page?: number
  per_page?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export async function fetchStatements(
  spaceId: string,
  params: StatementListParams = {},
  token?: string,
): Promise<PaginatedResponse<Statement>> {
  if (!token) {
    throw new Error('Authentication token is required for fetchStatements')
  }

  const options: ApiRequestOptions<PaginatedResponse<Statement>> = {
    token,
    params: {
      page: params.page ?? 1,
      per_page: params.per_page ?? 50,
      ...(params.search ? { search: params.search } : {}),
      ...(params.sort_by ? { sort_by: params.sort_by } : {}),
      ...(params.sort_order ? { sort_order: params.sort_order } : {}),
    },
  }

  return apiGet<PaginatedResponse<Statement>>(`/research-spaces/${spaceId}/statements`, options)
}

export async function createStatement(
  spaceId: string,
  payload: StatementCreateRequest,
  token?: string,
): Promise<Statement> {
  if (!token) {
    throw new Error('Authentication token is required for createStatement')
  }
  return apiPost<Statement>(`/research-spaces/${spaceId}/statements`, payload, { token })
}

export async function updateStatement(
  spaceId: string,
  statementId: number,
  payload: StatementUpdateRequest,
  token?: string,
): Promise<Statement> {
  if (!token) {
    throw new Error('Authentication token is required for updateStatement')
  }
  return apiPut<Statement>(
    `/research-spaces/${spaceId}/statements/${statementId}`,
    payload,
    { token },
  )
}

export async function deleteStatement(
  spaceId: string,
  statementId: number,
  token?: string,
): Promise<{ message: string }> {
  if (!token) {
    throw new Error('Authentication token is required for deleteStatement')
  }
  return apiDelete<{ message: string }>(
    `/research-spaces/${spaceId}/statements/${statementId}`,
    { token },
  )
}

export async function promoteStatement(
  spaceId: string,
  statementId: number,
  token?: string,
): Promise<Mechanism> {
  if (!token) {
    throw new Error('Authentication token is required for promoteStatement')
  }
  return apiPost<Mechanism>(
    `/research-spaces/${spaceId}/statements/${statementId}/promote`,
    {},
    { token },
  )
}
