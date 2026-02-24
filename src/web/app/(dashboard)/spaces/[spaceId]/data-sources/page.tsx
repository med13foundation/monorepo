import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceDataSourcesClient from '../space-data-sources-client'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import { fetchSpaceDiscoveryState } from '@/app/actions/space-discovery'
import { fetchSourceWorkflowMonitor } from '@/lib/api/kernel'
import type { SourceWorkflowCardStatus } from '@/components/data-sources/DataSourcesList'

interface SpaceDataSourcesPageProps {
  params: Promise<{
    spaceId: string
  }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

function firstParam(value: string | string[] | undefined): string | undefined {
  if (typeof value === 'string') {
    return value
  }
  return Array.isArray(value) ? value[0] : undefined
}

function toNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

export default async function SpaceDataSourcesPage({
  params,
  searchParams,
}: SpaceDataSourcesPageProps) {
  const { spaceId } = await params
  const resolvedSearchParams = searchParams ? await searchParams : undefined
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
  const workflowMonitorEnabled = process.env.SPACE_WORKFLOW_MONITOR_ENABLED !== 'false'
  const onboarding = firstParam(resolvedSearchParams?.onboarding) === '1'
  let workflowStatusBySource: Record<string, SourceWorkflowCardStatus> = {}

  if (workflowMonitorEnabled && dataSources?.items && dataSources.items.length > 0) {
    const entries = await Promise.all(
      dataSources.items.map(async (source) => {
        try {
          const monitor = await fetchSourceWorkflowMonitor(
            spaceId,
            source.id,
            { limit: 5, include_graph: true },
            token,
          )
          const counters = monitor.operational_counters ?? {}
          return [
            source.id,
            {
              last_pipeline_status:
                typeof counters.last_pipeline_status === 'string'
                  ? counters.last_pipeline_status
                  : null,
              pending_paper_count: toNumber(counters.pending_paper_count),
              pending_relation_review_count: toNumber(counters.pending_relation_review_count),
              graph_edges_delta_last_run: toNumber(counters.graph_edges_delta_last_run),
              graph_edges_total: toNumber(counters.graph_edges_total),
            } satisfies SourceWorkflowCardStatus,
          ] as const
        } catch {
          return null
        }
      }),
    )
    workflowStatusBySource = Object.fromEntries(
      entries.filter((entry): entry is readonly [string, SourceWorkflowCardStatus] => entry !== null),
    )
  }

  return (
    <SpaceDataSourcesClient
      spaceId={spaceId}
      dataSources={dataSources}
      dataSourcesError={dataSourcesError}
      discoveryState={discoveryState}
      discoveryCatalog={discoveryCatalog}
      discoveryError={discoveryError}
      workflowStatusBySource={workflowStatusBySource}
      workflowMonitorEnabled={workflowMonitorEnabled}
      onboarding={onboarding}
    />
  )
}
