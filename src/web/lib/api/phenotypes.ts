import { apiGet, type ApiRequestOptions } from '@/lib/api/client'
import type { PhenotypeResponse, PhenotypeSearchResult } from '@/types/generated'

export async function searchPhenotypes(
  spaceId: string,
  query: string,
  limit = 10,
  token?: string,
): Promise<PhenotypeResponse[]> {
  if (!token) {
    throw new Error('Authentication token is required for searchPhenotypes')
  }

  const options: ApiRequestOptions<PhenotypeSearchResult> = {
    token,
    params: {
      query,
      limit,
    },
  }

  const response = await apiGet<PhenotypeSearchResult>(
    `/research-spaces/${spaceId}/phenotypes/search`,
    options,
  )
  return response.results
}

export async function lookupPhenotypes(
  spaceId: string,
  phenotypeIds: number[],
  token?: string,
): Promise<PhenotypeResponse[]> {
  if (!token) {
    throw new Error('Authentication token is required for lookupPhenotypes')
  }
  if (phenotypeIds.length === 0) {
    return []
  }
  const options: ApiRequestOptions<PhenotypeResponse[]> = {
    token,
    params: {
      ids: phenotypeIds.join(','),
    },
  }
  return apiGet<PhenotypeResponse[]>(
    `/research-spaces/${spaceId}/phenotypes/lookup`,
    options,
  )
}
