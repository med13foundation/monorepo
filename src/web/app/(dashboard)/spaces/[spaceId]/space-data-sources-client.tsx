'use client'

import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import {
  DataSourcesList,
  type SourceWorkflowCardStatus,
} from '@/components/data-sources/DataSourcesList'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

interface SpaceDataSourcesClientProps {
  spaceId: string
  dataSources: DataSourceListResponse | null
  dataSourcesError?: string | null
  discoveryState: OrchestratedSessionState | null
  discoveryCatalog: SourceCatalogEntry[]
  discoveryError?: string | null
  workflowStatusBySource?: Record<string, SourceWorkflowCardStatus>
  workflowMonitorEnabled?: boolean
  onboarding?: boolean
}

export default function SpaceDataSourcesClient({
  spaceId,
  dataSources,
  dataSourcesError,
  discoveryState,
  discoveryCatalog,
  discoveryError,
  workflowStatusBySource,
  workflowMonitorEnabled = true,
  onboarding = false,
}: SpaceDataSourcesClientProps) {
  return (
    <div className="space-y-6">
      {onboarding && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="py-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">Onboarding</Badge>
              <span className="text-sm">
                Configure PubMed query, OA-only mode, schedule, and AI settings. Then use
                <strong> Run full pipeline now</strong> and open the workflow monitor.
              </span>
            </div>
          </CardContent>
        </Card>
      )}
      {!workflowMonitorEnabled && (
        <Card>
          <CardContent className="py-3 text-sm text-muted-foreground">
            Workflow monitor is disabled (`SPACE_WORKFLOW_MONITOR_ENABLED=false`).
          </CardContent>
        </Card>
      )}
      <DataSourcesList
        spaceId={spaceId}
        dataSources={dataSources}
        dataSourcesError={dataSourcesError}
        discoveryState={discoveryState}
        discoveryCatalog={discoveryCatalog}
        discoveryError={discoveryError}
        workflowStatusBySource={workflowStatusBySource}
      />
    </div>
  )
}
