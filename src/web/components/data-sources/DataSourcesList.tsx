"use client"

import { useState } from 'react'
import { toast } from 'sonner'
import {
  deleteDataSourceAction,
  testDataSourceAiConfigurationAction,
  updateDataSourceAction,
} from '@/app/actions/data-sources'
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
import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'
import type { DataSource } from '@/types/data-source'
import { componentRegistry } from '@/lib/components/registry'
import type { DataSourceAiTestResult, DataSourceListResponse } from '@/lib/api/data-sources'
import { useRouter } from 'next/navigation'

interface DataSourcesListProps {
  spaceId: string
  dataSources: DataSourceListResponse | null
  dataSourcesError?: string | null
  discoveryState: OrchestratedSessionState | null
  discoveryCatalog: SourceCatalogEntry[]
  discoveryError?: string | null
}

type SourceAgentConfigSnapshot = {
  isAiManaged: boolean
  queryAgentSourceType: string | null
}

function getSourceAgentConfigSnapshot(source: DataSource): SourceAgentConfigSnapshot {
  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value)
  const config = isRecord(source.config) ? source.config : {}
  const metadata = isRecord(config.metadata) ? config.metadata : {}
  const agentConfig = isRecord(metadata.agent_config) ? metadata.agent_config : {}
  const queryAgentSourceType = typeof agentConfig.query_agent_source_type === 'string'
    && agentConfig.query_agent_source_type.trim().length > 0
    ? agentConfig.query_agent_source_type.trim()
    : null
  return {
    isAiManaged: agentConfig.is_ai_managed === true,
    queryAgentSourceType,
  }
}

export function DataSourcesList({
  spaceId,
  dataSources,
  dataSourcesError,
  discoveryState,
  discoveryCatalog,
  discoveryError,
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
            const showsAiControls =
              source.source_type === 'pubmed' ||
              agentConfig.queryAgentSourceType !== null ||
              agentConfig.isAiManaged

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
