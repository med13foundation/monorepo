import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import type { Session } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SystemSettingsClient from './system-settings-client'
import {
  fetchUsers,
  fetchUserStatistics,
  type UserListResponse,
  type UserStatisticsResponse,
} from '@/lib/api/users'
import { fetchStorageConfigurations, fetchStorageOverview } from '@/lib/api/storage'
import { fetchMaintenanceState } from '@/lib/api/system-status'
import { fetchResearchSpaces } from '@/lib/api/research-spaces'
import {
  fetchAdminCatalogEntries,
  fetchCatalogAvailabilitySummaries,
  type DataSourceAvailability,
} from '@/lib/api/data-source-activation'
import { INITIAL_USER_PARAMS } from './constants'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { ResearchSpace } from '@/types/research-space'

type AdminSession = Session & {
  user?: Session['user'] & {
    role?: string
    access_token?: string
  }
}

export default async function SystemSettingsPage() {
  const isE2ETestMode = process.env.E2E_TEST_MODE === 'playwright'
  let session = (await getServerSession(authOptions)) as AdminSession | null

  if (isE2ETestMode) {
    session = {
      user: {
        id: 'playwright-admin',
        role: 'admin',
        email: 'playwright@med13.dev',
        username: 'playwright-admin',
        full_name: 'Playwright Admin',
        email_verified: true,
        name: 'Playwright Admin',
        access_token: ['playwright', 'token'].join('-'),
        expires_at: Math.floor(Date.now() / 1000) + 3600,
      },
      expires: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    }
  }

  if (!session) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user?.role !== 'admin') {
    redirect('/dashboard?error=AdminOnly')
  }

  const token = session.user?.access_token
  if (!token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let users: UserListResponse | null = null
  let userStats: UserStatisticsResponse | null = null
  let storageConfigurations: StorageConfigurationListResponse | null = null
  let storageOverview: StorageOverviewResponse | null = null
  let maintenanceState: MaintenanceModeResponse | null = null
  let catalogEntries: SourceCatalogEntry[] = []
  let availabilitySummaries: DataSourceAvailability[] = []
  let spaces: ResearchSpace[] = []
  const [
    usersResult,
    userStatsResult,
    storageConfigurationsResult,
    storageOverviewResult,
    maintenanceStateResult,
    catalogEntriesResult,
    availabilitySummariesResult,
    researchSpacesResult,
  ] = await Promise.allSettled([
    fetchUsers(INITIAL_USER_PARAMS, token),
    fetchUserStatistics(token),
    fetchStorageConfigurations(
      { page: 1, per_page: 100, include_disabled: true },
      token,
    ),
    fetchStorageOverview(token),
    fetchMaintenanceState(token),
    fetchAdminCatalogEntries(token),
    fetchCatalogAvailabilitySummaries(token),
    fetchResearchSpaces({ limit: 100 }, token),
  ])

  if (usersResult.status === 'fulfilled') {
    users = usersResult.value
  } else {
    console.error('[SystemSettingsPage] Failed to fetch users:', usersResult.reason)
  }

  if (userStatsResult.status === 'fulfilled') {
    userStats = userStatsResult.value
  } else {
    console.error('[SystemSettingsPage] Failed to fetch user stats:', userStatsResult.reason)
  }

  if (storageConfigurationsResult.status === 'fulfilled') {
    storageConfigurations = storageConfigurationsResult.value
  } else {
    console.error(
      '[SystemSettingsPage] Failed to fetch storage configurations:',
      storageConfigurationsResult.reason,
    )
  }

  if (storageOverviewResult.status === 'fulfilled') {
    storageOverview = storageOverviewResult.value
  } else {
    console.error('[SystemSettingsPage] Failed to fetch storage overview:', storageOverviewResult.reason)
  }

  if (maintenanceStateResult.status === 'fulfilled') {
    maintenanceState = maintenanceStateResult.value
  } else {
    console.error(
      '[SystemSettingsPage] Failed to fetch maintenance state:',
      maintenanceStateResult.reason,
    )
  }

  if (catalogEntriesResult.status === 'fulfilled') {
    catalogEntries = catalogEntriesResult.value
  } else {
    console.error(
      '[SystemSettingsPage] Failed to fetch catalog entries:',
      catalogEntriesResult.reason,
    )
  }

  if (availabilitySummariesResult.status === 'fulfilled') {
    availabilitySummaries = availabilitySummariesResult.value
  } else {
    console.error(
      '[SystemSettingsPage] Failed to fetch catalog availability:',
      availabilitySummariesResult.reason,
    )
  }

  if (researchSpacesResult.status === 'fulfilled') {
    spaces = researchSpacesResult.value.spaces
  } else {
    console.error(
      '[SystemSettingsPage] Failed to fetch research spaces:',
      researchSpacesResult.reason,
    )
  }

  return (
    <SystemSettingsClient
      initialParams={INITIAL_USER_PARAMS}
      users={users}
      userStats={userStats}
      storageConfigurations={storageConfigurations}
      storageOverview={storageOverview}
      maintenanceState={maintenanceState}
      catalogEntries={catalogEntries}
      availabilitySummaries={availabilitySummaries}
      spaces={spaces}
      currentUserId={session.user?.id ?? ''}
      isAdmin={session.user?.role === 'admin'}
    />
  )
}
