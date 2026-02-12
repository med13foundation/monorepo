import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceDataSourcesClient from '../space-data-sources-client'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import { fetchSpaceDiscoveryState } from '@/app/actions/space-discovery'

interface SpaceDataSourcesPageProps {
  params: Promise<{
    spaceId: string
  }>
}

export default async function SpaceDataSourcesPage({ params }: SpaceDataSourcesPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let dataSources: DataSourceListResponse | null = null
  let dataSourcesError: string | null = null

  try {
    dataSources = await fetchDataSourcesBySpace(spaceId, {}, token)
  } catch (error) {
    dataSourcesError =
      error instanceof Error ? error.message : 'Unable to load data sources for this space.'
    console.error('[SpaceDataSourcesPage] Failed to fetch data sources', error)
  }

  const discoveryResult = await fetchSpaceDiscoveryState(spaceId)
  const discoveryState = discoveryResult.success ? discoveryResult.data.orchestratedState : null
  const discoveryCatalog = discoveryResult.success ? discoveryResult.data.catalog : []
  const discoveryError = discoveryResult.success ? null : discoveryResult.error

  return (
    <SpaceDataSourcesClient
      spaceId={spaceId}
      dataSources={dataSources}
      dataSourcesError={dataSourcesError}
      discoveryState={discoveryState}
      discoveryCatalog={discoveryCatalog}
      discoveryError={discoveryError}
    />
  )
}
