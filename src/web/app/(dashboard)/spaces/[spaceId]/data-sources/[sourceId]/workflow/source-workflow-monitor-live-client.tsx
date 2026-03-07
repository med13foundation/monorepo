"use client"

import { startTransition, useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { useSourceWorkflowStream } from '@/hooks/use-source-workflow-stream'
import type { ArtanaRunTraceResponse } from '@/types/artana'
import type {
  SourcePipelineRunsResponse,
  SourceWorkflowMonitorResponse,
  SourceWorkflowStreamBootstrapPayload,
  SourceWorkflowStreamSnapshotPayload,
} from '@/types/kernel'

import { SourceWorkflowMonitorView } from './source-workflow-monitor-view'
import type { WorkflowTabKey } from './source-workflow-monitor-tab-sections'

const WORKFLOW_SSE_ENABLED = process.env.NEXT_PUBLIC_WORKFLOW_SSE_ENABLED !== 'false'

interface SourceWorkflowMonitorLiveClientProps {
  spaceId: string
  sourceId: string
  selectedRunId?: string
  initialTab: WorkflowTabKey
  initialMonitor: SourceWorkflowMonitorResponse | null
  initialMonitorError: string | null
  initialPipelineRuns: SourcePipelineRunsResponse | null
  initialTrace: ArtanaRunTraceResponse | null
  initialTraceError: string | null
}

function resolveSourceIdFromMonitor(
  fallbackSourceId: string,
  monitor: SourceWorkflowMonitorResponse,
): string {
  const sourceSnapshot = monitor.source_snapshot
  if (
    typeof sourceSnapshot === 'object' &&
    sourceSnapshot !== null &&
    !Array.isArray(sourceSnapshot)
  ) {
    const rawSourceId = sourceSnapshot.source_id
    if (typeof rawSourceId === 'string' && rawSourceId.trim().length > 0) {
      return rawSourceId
    }
  }
  return fallbackSourceId
}

function mapMonitorToPipelineRuns(
  sourceId: string,
  monitor: SourceWorkflowMonitorResponse,
): SourcePipelineRunsResponse {
  const runs = Array.isArray(monitor.pipeline_runs) ? monitor.pipeline_runs : []
  return {
    source_id: sourceId,
    runs,
    total: runs.length,
  }
}

function applyMonitorSnapshot(
  sourceId: string,
  payload: SourceWorkflowStreamBootstrapPayload | SourceWorkflowStreamSnapshotPayload,
): {
  monitor: SourceWorkflowMonitorResponse
  pipelineRuns: SourcePipelineRunsResponse
} {
  const resolvedSourceId = resolveSourceIdFromMonitor(sourceId, payload.monitor)
  return {
    monitor: payload.monitor,
    pipelineRuns: mapMonitorToPipelineRuns(resolvedSourceId, payload.monitor),
  }
}

export function SourceWorkflowMonitorLiveClient({
  spaceId,
  sourceId,
  selectedRunId,
  initialTab,
  initialMonitor,
  initialMonitorError,
  initialPipelineRuns,
  initialTrace,
  initialTraceError,
}: SourceWorkflowMonitorLiveClientProps) {
  const router = useRouter()
  const [monitor, setMonitor] = useState<SourceWorkflowMonitorResponse | null>(
    initialMonitor,
  )
  const [monitorError, setMonitorError] = useState<string | null>(initialMonitorError)
  const [pipelineRuns, setPipelineRuns] = useState<SourcePipelineRunsResponse | null>(
    initialPipelineRuns,
  )
  const [trace, setTrace] = useState<ArtanaRunTraceResponse | null>(initialTrace)
  const [traceError, setTraceError] = useState<string | null>(initialTraceError)
  const streamEnabled = useMemo(() => WORKFLOW_SSE_ENABLED, [])

  const refreshTrace = useCallback(async (runId: string) => {
    const response = await fetch(
      `/api/research-spaces/${spaceId}/artana-runs/${encodeURIComponent(runId)}`,
      {
        cache: 'no-store',
      },
    )
    const responseText = await response.text()
    if (!response.ok) {
      let detail = 'Unable to load Artana trace.'
      if (responseText) {
        try {
          const parsed = JSON.parse(responseText) as { detail?: string }
          if (typeof parsed.detail === 'string' && parsed.detail.trim().length > 0) {
            detail = parsed.detail
          }
        } catch {
          detail = responseText
        }
      }
      throw new Error(detail)
    }
    const parsed = JSON.parse(responseText) as ArtanaRunTraceResponse
    startTransition(() => {
      setTrace(parsed)
      setTraceError(null)
    })
  }, [spaceId])

  const {
    isFallbackActive: isSseFallbackActive,
    lastError: streamError,
  } = useSourceWorkflowStream({
    spaceId,
    sourceId,
    runId: selectedRunId,
    enabled: streamEnabled,
    onBootstrap: (payload) => {
      const nextState = applyMonitorSnapshot(sourceId, payload)
      setMonitor(nextState.monitor)
      setPipelineRuns(nextState.pipelineRuns)
      setMonitorError(null)
      if (selectedRunId) {
        void refreshTrace(selectedRunId).catch((error: unknown) => {
          setTraceError(error instanceof Error ? error.message : 'Unable to load Artana trace.')
        })
      }
    },
    onSnapshot: (payload) => {
      const nextState = applyMonitorSnapshot(sourceId, payload)
      setMonitor(nextState.monitor)
      setPipelineRuns(nextState.pipelineRuns)
      setMonitorError(null)
      if (selectedRunId) {
        void refreshTrace(selectedRunId).catch((error: unknown) => {
          setTraceError(error instanceof Error ? error.message : 'Unable to load Artana trace.')
        })
      }
    },
  })

  useEffect(() => {
    if (streamError !== null) {
      setMonitorError((previous) => previous ?? streamError)
    }
  }, [streamError])

  useEffect(() => {
    if (!streamEnabled || !isSseFallbackActive) {
      return
    }
    const intervalId = window.setInterval(() => {
      router.refresh()
    }, 4000)
    return () => {
      window.clearInterval(intervalId)
    }
  }, [isSseFallbackActive, router, streamEnabled])

  useEffect(() => {
    if (!selectedRunId) {
      setTrace(null)
      setTraceError(null)
      return
    }
    void refreshTrace(selectedRunId).catch((error: unknown) => {
      setTrace(null)
      setTraceError(error instanceof Error ? error.message : 'Unable to load Artana trace.')
    })
  }, [refreshTrace, selectedRunId])

  return (
    <SourceWorkflowMonitorView
      spaceId={spaceId}
      selectedRunId={selectedRunId}
      monitor={monitor}
      monitorError={monitorError}
      pipelineRuns={pipelineRuns}
      trace={trace}
      traceError={traceError}
      initialTab={initialTab}
    />
  )
}
