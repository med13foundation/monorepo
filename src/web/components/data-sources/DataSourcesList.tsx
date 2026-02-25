"use client"

import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  deleteDataSourceAction,
  updateDataSourceAction,
} from '@/app/actions/data-sources'
import {
  cancelSpaceSourcePipelineRunAction,
  fetchSourceWorkflowCardStatusAction,
  runSpaceSourcePipelineAction,
} from '@/app/actions/kernel-ingest'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Database,
  Loader2,
  Play,
  Square,
  ChevronDown,
  ChevronsUpDown,
  Info,
  Search,
  MoreVertical,
  Trash2,
  ShieldCheck,
  Settings2,
} from 'lucide-react'
import { DataSourceConfigurationDialog } from './DataSourceConfigurationDialog'
import { DataSourceIngestionDetailsDialog } from './DataSourceIngestionDetailsDialog'
import { DiscoverSourcesDialog } from './DiscoverSourcesDialog'
import { getSourceAgentConfigSnapshot } from './sourceAgentConfig'
import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'
import type { DataSource } from '@/types/data-source'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { cn } from '@/lib/utils'

interface DataSourcesListProps {
  spaceId: string
  dataSources: DataSourceListResponse | null
  dataSourcesError?: string | null
  discoveryState: OrchestratedSessionState | null
  discoveryCatalog: SourceCatalogEntry[]
  discoveryError?: string | null
  workflowStatusBySource?: Record<string, SourceWorkflowCardStatus>
}

export interface SourceWorkflowCardStatus {
  last_pipeline_status: string | null
  last_failed_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  pending_paper_count: number
  pending_relation_review_count: number
  graph_edges_delta_last_run: number
  graph_edges_total: number
}

export function DataSourcesList({
  spaceId,
  dataSources,
  dataSourcesError,
  discoveryState,
  discoveryCatalog,
  discoveryError,
  workflowStatusBySource,
}: DataSourcesListProps) {
  const router = useRouter()
  const [detailSourceId, setDetailSourceId] = useState<string | null>(null)
  const [isDiscoverDialogOpen, setIsDiscoverDialogOpen] = useState(false)
  const [configurationDialogSource, setConfigurationDialogSource] = useState<DataSource | null>(null)
  const [configurationDialogTab, setConfigurationDialogTab] = useState<'schedule' | 'ai'>('schedule')
  const [configurationDialogActivationIntent, setConfigurationDialogActivationIntent] = useState(false)
  const [togglingSourceId, setTogglingSourceId] = useState<string | null>(null)
  const [deleteSourceId, setDeleteSourceId] = useState<string | null>(null)
  const [isDeletingSource, setIsDeletingSource] = useState(false)
  const [runningPipelineSourceId, setRunningPipelineSourceId] = useState<string | null>(null)
  const [liveWorkflowStatusBySource, setLiveWorkflowStatusBySource] = useState<
    Record<string, SourceWorkflowCardStatus>
  >(workflowStatusBySource ?? {})
  const [expandedSourceIds, setExpandedSourceIds] = useState<Set<string>>(new Set())
  const initialExpandDoneRef = useRef(false)
  const runGenerationBySourceRef = useRef<Record<string, number>>({})
  const detachedRunGenerationBySourceRef = useRef<Record<string, number>>({})
  const activeRunIdBySourceRef = useRef<Record<string, string>>({})

  const resolvedDataSources = dataSources?.items ?? []

  useEffect(() => {
    if (initialExpandDoneRef.current || resolvedDataSources.length === 0) return
    initialExpandDoneRef.current = true
    setExpandedSourceIds(new Set(resolvedDataSources.map((s) => s.id)))
  }, [resolvedDataSources])

  useEffect(() => {
    setLiveWorkflowStatusBySource(workflowStatusBySource ?? {})
  }, [workflowStatusBySource])

  const pollingSourceIds = useMemo(() => {
    const ids: string[] = []
    for (const source of resolvedDataSources) {
      if (source.status !== 'active') {
        continue
      }
      const status = liveWorkflowStatusBySource[source.id]
      const isRunActive =
        runningPipelineSourceId === source.id ||
        status?.last_pipeline_status === 'running'
      const hasBacklog =
        (status?.pending_paper_count ?? 0) > 0 ||
        (status?.pending_relation_review_count ?? 0) > 0
      if (isRunActive || hasBacklog) {
        ids.push(source.id)
      }
    }
    return ids
  }, [liveWorkflowStatusBySource, resolvedDataSources, runningPipelineSourceId])

  useEffect(() => {
    if (pollingSourceIds.length === 0) return
    let isMounted = true
    let isPolling = false
    const poll = async () => {
      if (isPolling || !isMounted) return
      isPolling = true
      try {
        const results = await Promise.all(
          pollingSourceIds.map(async (sourceId) => ({
            sourceId,
            result: await fetchSourceWorkflowCardStatusAction(spaceId, sourceId),
          })),
        )
        if (!isMounted) return

        setLiveWorkflowStatusBySource((previous) => {
          const next = { ...previous }
          for (const item of results) {
            if (item.result.success) {
              next[item.sourceId] = item.result.data
            }
          }
          return next
        })

        const hasBackendRunning = results.some(
          (item) =>
            item.result.success &&
            item.result.data.last_pipeline_status === 'running',
        )
        if (!hasBackendRunning && runningPipelineSourceId !== null) {
          setRunningPipelineSourceId(null)
        }
      } finally {
        isPolling = false
      }
    }
    void poll()
    const intervalId = window.setInterval(() => {
      void poll()
    }, 4000)
    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [pollingSourceIds, runningPipelineSourceId, spaceId])

  if (dataSourcesError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">
            Failed to load data sources: {dataSourcesError}
          </p>
        </CardContent>
      </Card>
    )
  }

  const detailSource =
    resolvedDataSources.find((source) => source.id === detailSourceId) ?? null
  const configurationSourceWorkflowStatus =
    configurationDialogSource !== null
      ? liveWorkflowStatusBySource[configurationDialogSource.id]
      : undefined

  const handleToggleSourceStatus = async (source: DataSource) => {
    const shouldActivate = source.status !== 'active'
    if (shouldActivate) {
      toast('Review Schedule and AI config before activation.')
      setConfigurationDialogActivationIntent(true)
      setConfigurationDialogTab('schedule')
      setConfigurationDialogSource(source)
      return
    }
    try {
      setTogglingSourceId(source.id)
      const result = await updateDataSourceAction(
        source.id,
        {
          status: shouldActivate ? 'active' : 'inactive',
        },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(
        shouldActivate
          ? `${source.name} is now active`
          : `${source.name} is now paused`,
      )
      router.refresh()
    } catch (error) {
      // Error toast is handled by the mutation
    } finally {
      setTogglingSourceId(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteSourceId) return
    try {
      setIsDeletingSource(true)
      const result = await deleteDataSourceAction(deleteSourceId, spaceId)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      setDeleteSourceId(null)
      router.refresh()
    } catch (error) {
      // Error toast is handled by the mutation
    } finally {
      setIsDeletingSource(false)
    }
  }

  const toggleSourceExpansion = (sourceId: string) => {
    setExpandedSourceIds((current) => {
      const next = new Set(current)
      if (next.has(sourceId)) {
        next.delete(sourceId)
      } else {
        next.add(sourceId)
      }
      return next
    })
  }

  const handleStopPipelineRun = async (source: DataSource) => {
    const activeRunId = activeRunIdBySourceRef.current[source.id]
    if (!activeRunId) {
      toast.error('No active run id available for cancellation.')
      return
    }
    const currentGeneration = runGenerationBySourceRef.current[source.id] ?? 0
    const cancelResult = await cancelSpaceSourcePipelineRunAction(
      spaceId,
      source.id,
      activeRunId,
    )
    if (!cancelResult.success) {
      toast.error(cancelResult.error)
      return
    }
    if (cancelResult.data.cancelled) {
      toast.success('Pipeline run cancelled.')
    } else {
      toast.message(`Pipeline run status: ${cancelResult.data.status}`)
    }
    if (currentGeneration > 0) {
      detachedRunGenerationBySourceRef.current[source.id] = currentGeneration
    }
    delete activeRunIdBySourceRef.current[source.id]
    setRunningPipelineSourceId((current) => (current === source.id ? null : current))
    router.refresh()
  }

  const formatScheduleLabel = (source: DataSource): string => {
    const schedule = source.ingestion_schedule
    if (!schedule || !schedule.enabled || schedule.frequency === 'manual') {
      return 'Manual'
    }
    if (schedule.frequency === 'cron') {
      return 'Custom'
    }
    return schedule.frequency.charAt(0).toUpperCase() + schedule.frequency.slice(1)
  }

  const formatTimestamp = (value?: string | null) => {
    if (!value) {
      return 'Never'
    }
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString()
  }

  const formatRelativeTime = (value?: string | null) => {
    if (!value) {
      return 'Never'
    }
    const target = new Date(value)
    if (Number.isNaN(target.getTime())) {
      return 'Unknown'
    }
    const diffMs = target.getTime() - Date.now()
    const absMs = Math.abs(diffMs)
    const units: [number, Intl.RelativeTimeFormatUnit][] = [
      [1000, 'second'],
      [60 * 1000, 'minute'],
      [60 * 60 * 1000, 'hour'],
      [24 * 60 * 60 * 1000, 'day'],
    ]
    const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
    for (let i = units.length - 1; i >= 0; i -= 1) {
      const [unitMs, unit] = units[i]
      if (absMs >= unitMs) {
        const valueInUnit = Math.round(diffMs / unitMs)
        return rtf.format(valueInUnit, unit)
      }
    }
    return 'moments away'
  }

  const normalizeSourceTitle = (name: string): string =>
    name.replace(/\s*\(from data discovery\)\s*$/i, '').trim()

  const readSourceMetadata = (source: DataSource): Record<string, unknown> => {
    const config = source.config
    if (!config || typeof config !== 'object' || Array.isArray(config)) {
      return {}
    }
    const metadata = (config as Record<string, unknown>).metadata
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
      return {}
    }
    return metadata as Record<string, unknown>
  }

  const readSourceAgentConfig = (source: DataSource): Record<string, unknown> => {
    const metadata = readSourceMetadata(source)
    const agentConfig = metadata.agent_config
    if (!agentConfig || typeof agentConfig !== 'object' || Array.isArray(agentConfig)) {
      return {}
    }
    return agentConfig as Record<string, unknown>
  }

  const parsePubMedSnapshot = (source: DataSource) => {
    const metadata = readSourceMetadata(source)
    const queryValue = metadata.query
    const maxResultsValue = metadata.max_results
    const openAccessOnlyValue = metadata.open_access_only

    return {
      query: typeof queryValue === 'string' ? queryValue : null,
      maxResults:
        typeof maxResultsValue === 'number' && Number.isFinite(maxResultsValue)
          ? Math.max(1, Math.floor(maxResultsValue))
          : null,
      openAccessOnly: openAccessOnlyValue !== false,
    }
  }

  const handleRunFullPipeline = async (source: DataSource, smokeMode: boolean) => {
    const nextGeneration = (runGenerationBySourceRef.current[source.id] ?? 0) + 1
    runGenerationBySourceRef.current[source.id] = nextGeneration
    delete detachedRunGenerationBySourceRef.current[source.id]
    const runId =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    activeRunIdBySourceRef.current[source.id] = runId
    try {
      if (smokeMode && source.source_type === 'pubmed') {
        const metadata = readSourceMetadata(source)
        const query = typeof metadata.query === 'string' ? metadata.query.toLowerCase() : ''
        const requiredTerms = Array.isArray(metadata.required_query_terms)
          ? metadata.required_query_terms.filter(
              (item): item is string => typeof item === 'string' && item.trim().length > 0,
            )
          : []
        const missingRequiredTerm =
          requiredTerms.length > 0 &&
          requiredTerms.some((term) => !query.includes(term.trim().toLowerCase()))
        if (missingRequiredTerm) {
          toast.error(
            'Smoke-mode guard: query is missing one or more required target terms for this source.',
          )
          return
        }
      }
      setRunningPipelineSourceId(source.id)
      setLiveWorkflowStatusBySource((previous) => {
        const current = previous[source.id]
        return {
          ...previous,
          [source.id]: {
            last_pipeline_status: 'running',
            last_failed_stage: null,
            pending_paper_count: current?.pending_paper_count ?? 0,
            pending_relation_review_count:
              current?.pending_relation_review_count ?? 0,
            graph_edges_delta_last_run:
              current?.graph_edges_delta_last_run ?? 0,
            graph_edges_total: current?.graph_edges_total ?? 0,
          },
        }
      })
      const agentConfig = readSourceAgentConfig(source)
      const modelId = typeof agentConfig.model_id === 'string' ? agentConfig.model_id : null
      const result = await runSpaceSourcePipelineAction(spaceId, source.id, {
        run_id: runId,
        source_type: source.source_type,
        model_id: modelId,
        smoke_mode: smokeMode,
      })
      if (runGenerationBySourceRef.current[source.id] !== nextGeneration) {
        return
      }
      if (detachedRunGenerationBySourceRef.current[source.id] === nextGeneration) {
        return
      }
      if (!result.success) {
        toast.error(result.error)
        return
      }
      const summary = result.data
      const stageLine = `Stages — ingestion: ${summary.ingestion_status}, enrichment: ${summary.enrichment_status}, extraction: ${summary.extraction_status}, graph: ${summary.graph_status}.`
      const skippedCoreStages =
        summary.enrichment_status === 'skipped' ||
        summary.extraction_status === 'skipped'
      if (summary.status === 'cancelled') {
        toast.message(`Pipeline cancelled for ${source.name}. ${stageLine}`)
      } else if (summary.status === 'failed' || skippedCoreStages) {
        toast.warning(
          `${smokeMode ? 'Smoke' : 'Full'} pipeline finished with partial progression for ${source.name}. ${stageLine} Run id: ${summary.run_id}.`,
        )
      } else {
        toast.success(
          `${smokeMode ? 'Smoke' : 'Full'} pipeline completed for ${source.name}. ${stageLine} Run id: ${summary.run_id}.`,
        )
      }
      router.refresh()
    } catch (error) {
      if (detachedRunGenerationBySourceRef.current[source.id] === nextGeneration) {
        return
      }
      toast.error('Failed to run full pipeline')
    } finally {
      if (runGenerationBySourceRef.current[source.id] === nextGeneration) {
        setRunningPipelineSourceId((current) => (current === source.id ? null : current))
        delete activeRunIdBySourceRef.current[source.id]
        router.refresh()
      }
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            {dataSources?.total || 0} data source{dataSources?.total !== 1 ? 's' : ''} in this space
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setIsDiscoverDialogOpen(true)}>
            <Search className="mr-2 size-4" />
            Add from Library
          </Button>
        </div>
      </div>

      {resolvedDataSources.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="py-12 text-center">
              <Database className="mx-auto mb-4 size-12 text-muted-foreground" />
              <h3 className="mb-2 text-lg font-semibold">No data sources added to this space yet</h3>
              <p className="mb-4 text-muted-foreground">
                Use the library to add PubMed or create a custom source from the same menu.
              </p>
              <div className="flex justify-center gap-3">
                <Button onClick={() => setIsDiscoverDialogOpen(true)}>
                  <Search className="mr-2 size-4" />
                  Add from Library
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {resolvedDataSources.map((source: DataSource) => {
            const agentConfig = getSourceAgentConfigSnapshot(source)
            const showsAiControls = agentConfig.supportsAiControls
            const isPubMedSource = source.source_type === 'pubmed'
            const pubMedSnapshot = isPubMedSource ? parsePubMedSnapshot(source) : null
            const workflowStatus = liveWorkflowStatusBySource[source.id]
            const displayTitle = normalizeSourceTitle(source.name)
            const description = isPubMedSource
              ? 'Biomedical literature database (NLM)'
              : source.description || 'No description'
            const lastExecutionAt =
              source.ingestion_schedule?.last_run_at ?? source.last_ingested_at ?? null
            const executionStatusLine = lastExecutionAt
              ? `Last execution: ${formatTimestamp(lastExecutionAt)}`
              : null
            const schedule = source.ingestion_schedule
            const hasRunnableSchedule =
              schedule?.enabled === true && String(schedule.frequency) !== 'manual'
            const nextRunRelative =
              hasRunnableSchedule && schedule?.next_run_at
                ? formatRelativeTime(schedule.next_run_at)
                : null
            const countTelemetryMetrics: Array<{
              label: string
              value: string
              tooltip?: string
            }> = [
              {
                label: 'Pending papers',
                value: String(workflowStatus?.pending_paper_count ?? 0),
              },
              {
                label: 'Pending review',
                value: String(workflowStatus?.pending_relation_review_count ?? 0),
              },
              {
                label: 'New edges',
                value: String(workflowStatus?.graph_edges_delta_last_run ?? 0),
                tooltip: 'Edges added in the latest pipeline run.',
              },
            ]
            const lastRunMetric = formatRelativeTime(lastExecutionAt)
            const isActive = source.status === 'active'
            const isArchived = source.status === 'archived'
            const backendRunning = workflowStatus?.last_pipeline_status === 'running'
            const isRunning = runningPipelineSourceId === source.id || backendRunning
            const showNextRunBadge = isActive && Boolean(nextRunRelative)
            const isExpanded = expandedSourceIds.has(source.id)
            const showLifecycleToggle = !isActive && !isArchived
            const lifecycleLabel = 'Activate'
            const lifecycleBadge = isArchived
              ? 'retired'
              : source.status === 'draft'
                ? 'draft'
                : isActive
                  ? 'active'
                  : 'disabled'
            const showOverflowMenu = true
            const inactiveMessage = isArchived
              ? 'Source is retired. Read-only mode.'
              : 'Source is inactive. Activate and complete configuration before execution.'
            const compactNextRunValue = showNextRunBadge
              ? `Next ${nextRunRelative}`
              : isActive
                ? 'Manual'
                : 'Paused'

            return (
              <Card
                key={source.id}
                className={cn('transition-opacity', !isActive && !isArchived && 'opacity-80')}
              >
                <CardHeader className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <TooltipProvider delayDuration={120}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7 shrink-0 text-muted-foreground"
                                aria-label={isExpanded ? `Collapse ${source.name}` : `Expand ${source.name}`}
                                title={isExpanded ? 'Collapse details' : 'Expand details'}
                                disabled={isRunning}
                                onClick={() => toggleSourceExpansion(source.id)}
                              >
                                <ChevronsUpDown className="size-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                              {isExpanded ? 'Collapse details' : 'Expand details'}
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <CardTitle className="truncate text-lg">{displayTitle}</CardTitle>
                        <Badge variant="outline" className="h-5 px-2 text-xs">
                          {lifecycleBadge}
                        </Badge>
                        {!isRunning && workflowStatus?.last_pipeline_status === 'failed' && (
                          <Badge variant="destructive" className="h-5 px-2 text-xs">
                            Pipeline failed
                          </Badge>
                        )}
                        {isRunning && (
                          <Badge variant="secondary" className="h-5 px-2 text-xs">
                            <Loader2 className="mr-1 size-3 animate-spin" />
                            Running
                          </Badge>
                        )}
                      </div>
                      <CardDescription className="mt-1 text-sm text-muted-foreground">
                        {description}
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                      {!isExpanded && (
                        <div className="hidden items-center gap-3 whitespace-nowrap pr-1 text-xs md:flex">
                          {isRunning && (
                            <span className="inline-flex items-center gap-1 text-primary">
                              <Loader2 className="size-3 animate-spin" />
                              Live
                            </span>
                          )}
                          <span className="text-muted-foreground">
                            Last run
                            <span className="ml-1 font-medium text-foreground">{lastRunMetric}</span>
                          </span>
                          <span className="text-muted-foreground">
                            Next run
                            <span className="ml-1 font-medium text-foreground">{compactNextRunValue}</span>
                          </span>
                        </div>
                      )}
                      {isActive &&
                        (isRunning ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="destructive"
                            className="h-7 gap-1 px-2 text-xs"
                            aria-label={`Stop run for ${source.name}`}
                            title="Stop run"
                            onClick={() => handleStopPipelineRun(source)}
                          >
                            <Square className="size-3" />
                            Stop run
                          </Button>
                        ) : (
                          <div className="flex items-center">
                            <Button
                              type="button"
                              size="icon"
                              variant="default"
                              className="h-7 w-7 rounded-r-none"
                              aria-label={`Run pipeline for ${source.name}`}
                              title="Run pipeline"
                              onClick={() => handleRunFullPipeline(source, false)}
                              disabled={runningPipelineSourceId === source.id}
                            >
                              <Play className="size-3.5" />
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="default"
                                  className="h-7 w-7 rounded-l-none border-l border-primary-foreground/20"
                                  aria-label={`Run options for ${source.name}`}
                                  title="More run options: full pipeline or quick test"
                                  disabled={runningPipelineSourceId === source.id}
                                >
                                  <ChevronDown className="size-3.5" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem
                                  disabled={runningPipelineSourceId === source.id}
                                  onClick={() => handleRunFullPipeline(source, false)}
                                >
                                  Run full pipeline
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  disabled={runningPipelineSourceId === source.id}
                                  onClick={() => handleRunFullPipeline(source, true)}
                                >
                                  Run quick test (stage cap 5)
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        ))}
                      {showsAiControls && (
                        <TooltipProvider delayDuration={120}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                type="button"
                                size="icon"
                                variant="outline"
                              className="h-7 w-7"
                              aria-label={`Configure ${source.name}`}
                              title="Configure source"
                              disabled={isRunning}
                              onClick={() => {
                                setConfigurationDialogActivationIntent(false)
                                setConfigurationDialogTab('schedule')
                                  setConfigurationDialogSource(source)
                                }}
                              >
                                <Settings2 className="size-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Configure source</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      {showLifecycleToggle && (
                        <Button
                          type="button"
                          size="sm"
                          variant="default"
                          className="h-7 px-3 text-xs"
                          disabled={togglingSourceId === source.id || isRunning}
                          onClick={() => handleToggleSourceStatus(source)}
                        >
                          {togglingSourceId === source.id ? (
                            <Loader2 className="size-3 animate-spin" />
                          ) : (
                            lifecycleLabel
                          )}
                        </Button>
                      )}
                      {showOverflowMenu && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="text-muted-foreground opacity-50 transition-opacity hover:opacity-100"
                              disabled={isRunning}
                            >
                              <MoreVertical className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/spaces/${spaceId}/data-sources/${source.id}/workflow?tab=setup`}>
                                Open pipeline workspace
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setDetailSourceId(source.id)}>
                              View details
                            </DropdownMenuItem>
                            {isActive && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  disabled={togglingSourceId === source.id}
                                  onClick={() => handleToggleSourceStatus(source)}
                                >
                                  Disable source
                                </DropdownMenuItem>
                              </>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteSourceId(source.id)}
                            >
                              <Trash2 className="mr-2 size-4" />
                              Remove source
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </div>
                  {executionStatusLine && isExpanded && (
                    <p className="text-sm text-muted-foreground">{executionStatusLine}</p>
                  )}
                  {isExpanded &&
                    !isRunning &&
                    isActive &&
                    (workflowStatus?.pending_paper_count ?? 0) > 0 && (
                      <p className="text-sm text-amber-700">
                        Queue backlog: {workflowStatus?.pending_paper_count ?? 0} pending paper
                        {(workflowStatus?.pending_paper_count ?? 0) === 1 ? '' : 's'}.
                      </p>
                    )}
                </CardHeader>
                {isExpanded && (
                  <CardContent className="space-y-4">
                    {isRunning && (
                      <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
                        <Loader2 className="size-4 animate-spin text-primary" />
                        <span>Live run in progress. Processing pipeline stages.</span>
                      </div>
                    )}
                    <div className="grid gap-6 xl:grid-cols-12 xl:items-start xl:divide-x xl:divide-border">
                    <div className="grid w-full grid-cols-[120px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm xl:col-span-4 xl:pr-6 2xl:col-span-3">
                      <div className="text-muted-foreground/80">Type</div>
                      <div className="font-semibold text-foreground capitalize">{source.source_type}</div>

                      <div className="text-muted-foreground/80">{isPubMedSource ? 'Access' : 'Status'}</div>
                      <div className="font-semibold text-foreground">
                        {isPubMedSource ? (
                          <span className="inline-flex items-center gap-2 whitespace-nowrap">
                            Open Access
                            <TooltipProvider delayDuration={120}>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span
                                    role="img"
                                    aria-label={
                                      pubMedSnapshot?.openAccessOnly
                                        ? 'Open access enforced'
                                        : 'Open access not enforced'
                                    }
                                    className="inline-flex cursor-help items-center text-muted-foreground"
                                  >
                                    <ShieldCheck className="size-4" />
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  {pubMedSnapshot?.openAccessOnly ? 'Enforced' : 'Not enforced'}
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </span>
                        ) : (
                          source.status
                        )}
                      </div>

                      <div className="inline-flex items-center gap-1 text-muted-foreground/80">
                        {isPubMedSource ? 'Cap / run' : 'Schedule'}
                        {isPubMedSource && (
                          <TooltipProvider delayDuration={120}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex cursor-help items-center">
                                  <Info className="size-3.5" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>Maximum papers ingested per run.</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                      <div className="font-semibold text-foreground">
                        {isPubMedSource
                          ? (pubMedSnapshot?.maxResults ?? 'Not set')
                          : formatScheduleLabel(source)}
                      </div>

                      <div className="text-muted-foreground/80">Ingestion</div>
                      <div className="font-semibold text-foreground">{formatTimestamp(source.last_ingested_at)}</div>

                      <div className="text-muted-foreground/80">Persistence</div>
                      <div className="font-semibold text-foreground">Deterministic</div>
                    </div>

                    <div className="w-full space-y-3 xl:col-span-8 xl:pl-6 2xl:col-span-9">
                      <div className="space-y-3 rounded-md bg-muted/20 p-4">
                        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-0 md:divide-x md:divide-border">
                          {countTelemetryMetrics.map((metric) => (
                            <div key={metric.label} className="space-y-1 md:px-3">
                              <div className="text-xl font-semibold leading-none">{metric.value}</div>
                              <div className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                {metric.label}
                                {metric.tooltip && (
                                  <TooltipProvider delayDuration={120}>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <span className="inline-flex cursor-help items-center">
                                          <Info className="size-3.5" />
                                        </span>
                                      </TooltipTrigger>
                                      <TooltipContent>{metric.tooltip}</TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                        {lastExecutionAt && (
                          <div className="flex items-center justify-between rounded-md border bg-background/60 px-3 py-2 text-sm">
                            <div className="text-muted-foreground">Last run</div>
                            <div className="font-medium">{lastRunMetric}</div>
                          </div>
                        )}
                        {!lastExecutionAt && (
                          <div className="space-y-2 rounded-md bg-background/70 px-3 py-2">
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              {isRunning ? (
                                <Loader2 className="size-4 animate-spin" />
                              ) : (
                                <Play className="size-4" />
                              )}
                              <span>
                                {isRunning
                                  ? 'Run in progress · awaiting completion status.'
                                  : 'Never run · No execution history available.'}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>

                      {!isActive && (
                        <div className="rounded-md border border-amber-300/60 bg-amber-50/60 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
                          {inactiveMessage}
                        </div>
                      )}
                    </div>
                  </div>
                  </CardContent>
                )}
              </Card>
            )
          })}
        </div>
      )}

      <DataSourceConfigurationDialog
        spaceId={spaceId}
        source={configurationDialogSource}
        workflowStatus={configurationSourceWorkflowStatus}
        open={Boolean(configurationDialogSource)}
        initialTab={configurationDialogTab}
        activationIntent={configurationDialogActivationIntent}
        onOpenChange={(open) => {
          if (!open) {
            setConfigurationDialogSource(null)
            setConfigurationDialogActivationIntent(false)
          }
        }}
      />
      <DataSourceIngestionDetailsDialog
        source={detailSource}
        open={Boolean(detailSourceId)}
        onOpenChange={(open) => {
          if (!open) {
            setDetailSourceId(null)
          }
        }}
      />
      <DiscoverSourcesDialog
        spaceId={spaceId}
        open={isDiscoverDialogOpen}
        onOpenChange={setIsDiscoverDialogOpen}
        discoveryState={discoveryState}
        discoveryCatalog={discoveryCatalog}
        discoveryError={discoveryError}
        onSourceAdded={() => router.refresh()}
      />
      <Dialog open={Boolean(deleteSourceId)} onOpenChange={(open) => !open && setDeleteSourceId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove data source</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove this data source? This action cannot be undone and will
              permanently delete the source from this research space.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteSourceId(null)}
              disabled={isDeletingSource}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeletingSource}
            >
              {isDeletingSource && <Loader2 className="mr-2 size-4 animate-spin" />}
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
