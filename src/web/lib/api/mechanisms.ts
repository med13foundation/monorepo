import { apiDelete, apiGet, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type { PaginatedResponse } from '@/types/generated'
import type {
  Mechanism,
  MechanismCreateRequest,
  MechanismUpdateRequest,
} from '@/types/mechanisms'

export interface MechanismListParams {
  page?: number
  per_page?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export async function fetchMechanisms(
  spaceId: string,
  params: MechanismListParams = {},
  token?: string,
): Promise<PaginatedResponse<Mechanism>> {
  if (!token) {
    throw new Error('Authentication token is required for fetchMechanisms')
  }

  const options: ApiRequestOptions<PaginatedResponse<Mechanism>> = {
    token,
    params: {
      page: params.page ?? 1,
      per_page: params.per_page ?? 50,
      ...(params.search ? { search: params.search } : {}),
      ...(params.sort_by ? { sort_by: params.sort_by } : {}),
      ...(params.sort_order ? { sort_order: params.sort_order } : {}),
    },
  }

  return apiGet<PaginatedResponse<Mechanism>>(`/research-spaces/${spaceId}/mechanisms`, options)
}

export async function createMechanism(
  spaceId: string,
  payload: MechanismCreateRequest,
  token?: string,
): Promise<Mechanism> {
  if (!token) {
    throw new Error('Authentication token is required for createMechanism')
  }
  return apiPost<Mechanism>(`/research-spaces/${spaceId}/mechanisms`, payload, { token })
}

export async function updateMechanism(
  spaceId: string,
  mechanismId: number,
  payload: MechanismUpdateRequest,
  token?: string,
): Promise<Mechanism> {
  if (!token) {
    throw new Error('Authentication token is required for updateMechanism')
  }
  return apiPut<Mechanism>(
    `/research-spaces/${spaceId}/mechanisms/${mechanismId}`,
    payload,
    { token },
  )
}

export async function deleteMechanism(
  spaceId: string,
  mechanismId: number,
  token?: string,
): Promise<{ message: string }> {
  if (!token) {
    throw new Error('Authentication token is required for deleteMechanism')
  }
  return apiDelete<{ message: string }>(
    `/research-spaces/${spaceId}/mechanisms/${mechanismId}`,
    { token },
  )
}
