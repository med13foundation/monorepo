import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'

import { fetchSourcePipelineRuns, fetchSourceWorkflowMonitor } from '@/lib/api/kernel'
import { authOptions } from '@/lib/auth'
import type { SourcePipelineRunsResponse, SourceWorkflowMonitorResponse } from '@/types/kernel'

import { SourceWorkflowMonitorView } from './source-workflow-monitor-view'

interface SourceWorkflowMonitorPageProps {
  params: Promise<{
    spaceId: string
    sourceId: string
  }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

function firstParam(value: string | string[] | undefined): string | undefined {
  if (typeof value === 'string') {
    return value
  }
  return Array.isArray(value) ? value[0] : undefined
}

export default async function SourceWorkflowMonitorPage({
  params,
  searchParams,
}: SourceWorkflowMonitorPageProps) {
  const { spaceId, sourceId } = await params
  const resolvedSearchParams = searchParams ? await searchParams : undefined
  const selectedRunId = firstParam(resolvedSearchParams?.run_id)
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let monitor: SourceWorkflowMonitorResponse | null = null
  let monitorError: string | null = null
  let pipelineRuns: SourcePipelineRunsResponse | null = null

  try {
    monitor = await fetchSourceWorkflowMonitor(
      spaceId,
      sourceId,
      {
        run_id: selectedRunId,
        limit: 50,
        include_graph: true,
      },
      token,
    )
  } catch (error) {
    monitorError = error instanceof Error ? error.message : 'Unable to load workflow monitor.'
  }

  try {
    pipelineRuns = await fetchSourcePipelineRuns(spaceId, sourceId, { limit: 50 }, token)
  } catch {
    pipelineRuns = null
  }

  return (
    <SourceWorkflowMonitorView
      spaceId={spaceId}
      selectedRunId={selectedRunId}
      monitor={monitor}
      monitorError={monitorError}
      pipelineRuns={pipelineRuns}
    />
  )
}
