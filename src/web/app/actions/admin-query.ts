"use server"

import { fetchCatalogAvailabilitySummaries } from '@/lib/api/data-source-activation'
import { fetchDataSourcesBySpace, type DataSourceListParams, type DataSourceListResponse } from '@/lib/api/data-sources'
import { fetchStorageConfigurations, fetchStorageOverview, type StorageConfigurationListParams } from '@/lib/api/storage'
import { fetchMaintenanceState } from '@/lib/api/system-status'
import { fetchUsers, fetchUserStatistics, type UserListParams, type UserListResponse, type UserStatisticsResponse } from '@/lib/api/users'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import { requireAccessToken } from '@/app/actions/action-utils'

export async function fetchUsersQueryAction(params: UserListParams = {}): Promise<UserListResponse> {
  const token = await requireAccessToken()
  return fetchUsers(params, token)
}

export async function fetchUserStatisticsQueryAction(): Promise<UserStatisticsResponse> {
  const token = await requireAccessToken()
  return fetchUserStatistics(token)
}

export async function fetchStorageConfigurationsQueryAction(
  params: StorageConfigurationListParams = {},
): Promise<StorageConfigurationListResponse> {
  const token = await requireAccessToken()
  return fetchStorageConfigurations(params, token)
}

export async function fetchStorageOverviewQueryAction(): Promise<StorageOverviewResponse> {
  const token = await requireAccessToken()
  return fetchStorageOverview(token)
}

export async function fetchMaintenanceStateQueryAction(): Promise<MaintenanceModeResponse> {
  const token = await requireAccessToken()
  return fetchMaintenanceState(token)
}

export async function fetchCatalogAvailabilitySummariesQueryAction(): Promise<DataSourceAvailability[]> {
  const token = await requireAccessToken()
  return fetchCatalogAvailabilitySummaries(token)
}

export async function fetchSpaceDataSourcesQueryAction(
  spaceId: string,
  params: Omit<DataSourceListParams, 'research_space_id'> = {},
): Promise<DataSourceListResponse> {
  const token = await requireAccessToken()
  return fetchDataSourcesBySpace(spaceId, params, token)
}
