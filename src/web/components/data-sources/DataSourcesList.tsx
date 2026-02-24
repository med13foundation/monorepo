"use client"

import { useState } from 'react'
import { toast } from 'sonner'
import {
  deleteDataSourceAction,
  testDataSourceAiConfigurationAction,
  updateDataSourceAction,
} from '@/app/actions/data-sources'
import { runSpaceSourcePipelineAction } from '@/app/actions/kernel-ingest'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
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
  FlaskConical,
  Loader2,
  Clock,
  Info,
  Search,
  MoreVertical,
  Trash2,
  TestTube,
} from 'lucide-react'
import { DataSourceScheduleDialog } from './DataSourceScheduleDialog'
import { DataSourceAiConfigDialog } from './DataSourceAiConfigDialog'
import { DataSourceIngestionDetailsDialog } from './DataSourceIngestionDetailsDialog'
import { DiscoverSourcesDialog } from './DiscoverSourcesDialog'
import { DataSourceAiTestDialog } from './DataSourceAiTestDialog'
import { getSourceAgentConfigSnapshot } from './sourceAgentConfig'
import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'
import type { DataSource } from '@/types/data-source'
import { componentRegistry } from '@/lib/components/registry'
import type { DataSourceAiTestResult, DataSourceListResponse } from '@/lib/api/data-sources'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

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
  const [scheduleDialogSource, setScheduleDialogSource] = useState<DataSource | null>(null)
  const [aiConfigDialogSource, setAiConfigDialogSource] = useState<DataSource | null>(null)
  const [testingSourceId, setTestingSourceId] = useState<string | null>(null)
  const [togglingSourceId, setTogglingSourceId] = useState<string | null>(null)
  const [retiringSourceId, setRetiringSourceId] = useState<string | null>(null)
  const [deleteSourceId, setDeleteSourceId] = useState<string | null>(null)
  const [isDeletingSource, setIsDeletingSource] = useState(false)
  const [aiTestDialogSource, setAiTestDialogSource] = useState<DataSource | null>(null)
  const [aiTestResult, setAiTestResult] = useState<DataSourceAiTestResult | null>(null)
  const [isAiTestDialogOpen, setIsAiTestDialogOpen] = useState(false)
  const [runningPipelineSourceId, setRunningPipelineSourceId] = useState<string | null>(null)
  const StatusBadge = componentRegistry.get<{ status: string }>('dataSource.statusBadge')

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

  const resolvedDataSources = dataSources?.items ?? []

  const detailSource =
    resolvedDataSources.find((source) => source.id === detailSourceId) ?? null

  const handleTestAiConfiguration = async (source: DataSource) => {
    try {
      setTestingSourceId(source.id)
      const result = await testDataSourceAiConfigurationAction(source.id)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      setAiTestDialogSource(source)
      setAiTestResult(result.data)
      setIsAiTestDialogOpen(true)
    } catch (error) {
      toast.error('Unable to test AI configuration')
    } finally {
      setTestingSourceId(null)
    }
  }

  const handleRetire = async (source: DataSource) => {
    try {
      setRetiringSourceId(source.id)
      const result = await updateDataSourceAction(
        source.id,
        {
          status: 'archived',
        },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      router.refresh()
    } catch (error) {
      // Error toast is handled by the mutation
    } finally {
      setRetiringSourceId(null)
    }
  }

  const handleToggleSourceStatus = async (source: DataSource) => {
    const shouldActivate = source.status !== 'active'
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
          : `${source.name} is now inactive`,
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

  const formatScheduleLabel = (source: DataSource): string => {
    const schedule = source.ingestion_schedule
    if (!schedule || !schedule.enabled) {
      return 'Manual only'
    }
    if (schedule.frequency === 'cron') {
      return schedule.cron_expression ? `Cron (${schedule.cron_expression})` : 'Cron'
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
      return 'Not scheduled'
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
      const agentConfig = readSourceAgentConfig(source)
      const modelId = typeof agentConfig.model_id === 'string' ? agentConfig.model_id : null
      const result = await runSpaceSourcePipelineAction(spaceId, source.id, {
        source_type: source.source_type,
        model_id: modelId,
        smoke_mode: smokeMode,
      })
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(
        smokeMode
          ? `Smoke pipeline run completed for ${source.name} (run id: ${result.data.run_id}).`
          : `Full pipeline run completed for ${source.name} (run id: ${result.data.run_id}).`,
      )
      router.refresh()
    } catch (error) {
      toast.error('Failed to run full pipeline')
    } finally {
      setRunningPipelineSourceId(null)
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
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {resolvedDataSources.map((source: DataSource) => {
            const agentConfig = getSourceAgentConfigSnapshot(source)
            const showsAiControls = agentConfig.supportsAiControls
            const isPubMedSource = source.source_type === 'pubmed'
            const pubMedSnapshot = isPubMedSource ? parsePubMedSnapshot(source) : null
            const workflowStatus = workflowStatusBySource?.[source.id]
            const preActivationChecklist: string[] = []
            if (source.status !== 'active' && isPubMedSource) {
              if (!pubMedSnapshot?.query) {
                preActivationChecklist.push('Set the PubMed query')
              }
              if (pubMedSnapshot?.openAccessOnly !== true) {
                preActivationChecklist.push('Enable OA-only mode (enforced on save)')
              }
              const schedule = source.ingestion_schedule
              if (
                !schedule ||
                schedule.enabled !== true ||
                schedule.frequency === 'manual'
              ) {
                preActivationChecklist.push('Configure a non-manual schedule')
              }
            }

            return (
              <Card key={source.id}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{source.name}</CardTitle>
                      <CardDescription className="mt-1">
                        {source.description || 'No description'}
                      </CardDescription>
                    </div>
                    {StatusBadge ? (
                      <StatusBadge status={source.status} />
                    ) : (
                      <Badge variant="outline">{source.status}</Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Type:</span>
                      <div className="flex items-center gap-2">
                        <span className="font-medium capitalize">{source.source_type}</span>
                        {agentConfig.isAiManaged && (
                          <Badge
                            variant="secondary"
                            className="bg-blue-100 px-1 py-0 text-[10px] uppercase text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                          >
                            AI Managed
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Last ingested:</span>
                      <span className="font-medium">{formatTimestamp(source.last_ingested_at)}</span>
                    </div>
                    {isPubMedSource && (
                      <>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">OA-only:</span>
                          <Badge variant="secondary">
                            {pubMedSnapshot?.openAccessOnly ? 'Enforced' : 'Disabled'}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Per-run cap:</span>
                          <span className="font-medium">
                            {pubMedSnapshot?.maxResults ?? 'Not set'}
                          </span>
                        </div>
                        {pubMedSnapshot?.query && (
                          <div className="rounded border bg-muted/30 p-2">
                            <p className="mb-1 text-[11px] uppercase text-muted-foreground">
                              Query preview
                            </p>
                            <p className="line-clamp-3 font-mono text-xs">
                              {pubMedSnapshot.query}
                            </p>
                          </div>
                        )}
                      </>
                    )}
                    {workflowStatus && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Badge variant="outline">
                          Last pipeline: {workflowStatus.last_pipeline_status ?? 'n/a'}
                        </Badge>
                        <Badge variant="outline">
                          Pending papers: {workflowStatus.pending_paper_count}
                        </Badge>
                        <Badge variant="outline">
                          Pending review: {workflowStatus.pending_relation_review_count}
                        </Badge>
                        <Badge variant="outline">
                          Graph Δ edges: {workflowStatus.graph_edges_delta_last_run}
                        </Badge>
                      </div>
                    )}
                    {preActivationChecklist.length > 0 && (
                      <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                        <p className="mb-1 font-medium">Pre-activation checklist</p>
                        {preActivationChecklist.map((item) => (
                          <p key={item}>- {item}</p>
                        ))}
                      </div>
                    )}
                    {source.tags && source.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {source.tags.map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <div className="mt-3 space-y-2 rounded-md border p-3">
                      {showsAiControls && (
                        <>
                          <div className="flex items-center justify-between text-sm">
                            <div className="flex items-center gap-1 text-muted-foreground">
                              <Clock className="size-4" />
                              <span>Schedule</span>
                            </div>
                            <span className="font-medium">{formatScheduleLabel(source)}</span>
                          </div>
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>Timezone</span>
                            <span>{source.ingestion_schedule?.timezone || 'UTC'}</span>
                          </div>
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>Next run</span>
                            <span>{formatRelativeTime(source.ingestion_schedule?.next_run_at)}</span>
                          </div>
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>Last run</span>
                            <span>{formatTimestamp(source.ingestion_schedule?.last_run_at)}</span>
                          </div>
                        </>
                      )}
                      <div className="flex flex-wrap gap-2 pt-2">
                        {showsAiControls && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => setScheduleDialogSource(source)}
                          >
                            Configure schedule
                          </Button>
                        )}
                        {showsAiControls && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => setAiConfigDialogSource(source)}
                          >
                            Configure AI
                          </Button>
                        )}
                        {showsAiControls && (
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={() => handleTestAiConfiguration(source)}
                            disabled={testingSourceId === source.id}
                          >
                            {testingSourceId === source.id ? (
                              <Loader2 className="mr-2 size-4 animate-spin" />
                            ) : (
                              <TestTube className="mr-2 size-4" />
                            )}
                            Test AI
                          </Button>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="default"
                          onClick={() => handleRunFullPipeline(source, false)}
                          disabled={runningPipelineSourceId === source.id}
                        >
                          {runningPipelineSourceId === source.id ? (
                            <Loader2 className="mr-2 size-4 animate-spin" />
                          ) : (
                            <FlaskConical className="mr-2 size-4" />
                          )}
                          Run full pipeline now
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleRunFullPipeline(source, true)}
                          disabled={runningPipelineSourceId === source.id}
                        >
                          {runningPipelineSourceId === source.id ? (
                            <Loader2 className="mr-2 size-4 animate-spin" />
                          ) : null}
                          Run smoke (stage cap 5)
                        </Button>
                        <Button type="button" size="sm" variant="outline" asChild>
                          <Link href={`/spaces/${spaceId}/data-sources/${source.id}/workflow`}>
                            Workflow monitor
                          </Link>
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="text-muted-foreground"
                          onClick={() => setDetailSourceId(source.id)}
                        >
                          <Info className="mr-2 size-4" />
                          View details
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="text-muted-foreground"
                            >
                              <MoreVertical className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {source.status !== 'archived' && (
                              <DropdownMenuItem
                                disabled={togglingSourceId === source.id}
                                onClick={() => handleToggleSourceStatus(source)}
                              >
                                {source.status === 'active' ? 'Disable source' : 'Enable source'}
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem
                              disabled={source.status === 'archived' || retiringSourceId === source.id}
                              onClick={() => handleRetire(source)}
                            >
                              Retire source
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteSourceId(source.id)}
                            >
                              <Trash2 className="mr-2 size-4" />
                              Remove source
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <DataSourceScheduleDialog
        spaceId={spaceId}
        source={scheduleDialogSource}
        open={Boolean(scheduleDialogSource)}
        onOpenChange={(open) => {
          if (!open) {
            setScheduleDialogSource(null)
          }
        }}
      />
      <DataSourceAiConfigDialog
        spaceId={spaceId}
        source={aiConfigDialogSource}
        open={Boolean(aiConfigDialogSource)}
        onOpenChange={(open) => {
          if (!open) {
            setAiConfigDialogSource(null)
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
      <DataSourceAiTestDialog
        source={aiTestDialogSource}
        result={aiTestResult}
        open={isAiTestDialogOpen}
        onOpenChange={(open) => {
          setIsAiTestDialogOpen(open)
          if (!open) {
            setAiTestDialogSource(null)
            setAiTestResult(null)
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
