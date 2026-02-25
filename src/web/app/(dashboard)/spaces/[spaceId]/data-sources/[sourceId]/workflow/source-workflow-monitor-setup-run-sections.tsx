import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import { SummaryRow, TableCard } from './source-workflow-monitor-primitives'
import { displayValue, type MonitorRow } from './source-workflow-monitor-utils'
import { ChecklistItem, CountCard } from './source-workflow-monitor-section-primitives'

interface SetupTabSectionProps {
  sourceSnapshot: MonitorRow
  schedule: MonitorRow
  selectedRunId?: string
  warnings: string[]
}

interface RunMonitorTabSectionProps {
  runRows: MonitorRow[]
  documentRows: MonitorRow[]
  queueRows: MonitorRow[]
  extractionRows: MonitorRow[]
}

export function SetupTabSection({
  sourceSnapshot,
  schedule,
  selectedRunId,
  warnings,
}: SetupTabSectionProps) {
  const queryValue = String(sourceSnapshot.query ?? '').trim()
  const hasQuery = queryValue.length > 0
  const scheduleEnabled = schedule.enabled === true
  const scheduleRunnable = scheduleEnabled && String(schedule.frequency ?? '') !== 'manual'
  const hasModel = String(sourceSnapshot.model_id ?? '').trim().length > 0
  const oaValue = sourceSnapshot.open_access_only
  const isPubMed = String(sourceSnapshot.source_type ?? '') === 'pubmed'
  const oaReady = !isPubMed || oaValue === true

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Setup summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <SummaryRow label="Source status" value={displayValue(sourceSnapshot.status)} />
          <SummaryRow label="Schedule enabled" value={displayValue(schedule.enabled)} />
          <SummaryRow label="Schedule frequency" value={displayValue(schedule.frequency)} />
          <SummaryRow label="Query" value={displayValue(sourceSnapshot.query)} mono />
          <SummaryRow label="Model" value={displayValue(sourceSnapshot.model_id)} />
          <SummaryRow label="OA only" value={displayValue(sourceSnapshot.open_access_only)} />
          <SummaryRow label="Per-run cap" value={displayValue(sourceSnapshot.max_results)} />
          {selectedRunId && (
            <div className="pt-1 text-xs text-muted-foreground">
              Filtered to run id: <span className="font-mono">{selectedRunId}</span>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Readiness checklist</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <ChecklistItem label="Query configured" isReady={hasQuery} />
          <ChecklistItem label="Runnable schedule configured" isReady={scheduleRunnable} />
          <ChecklistItem label="AI model selected" isReady={hasModel} />
          <ChecklistItem label="PubMed OA policy satisfied" isReady={oaReady} />
        </CardContent>
      </Card>

      {warnings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Warnings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            {warnings.map((warning, index) => (
              <div key={`${warning}-${index}`}>- {warning}</div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export function RunMonitorTabSection({
  runRows,
  documentRows,
  queueRows,
  extractionRows,
}: RunMonitorTabSectionProps) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-4">
        <CountCard title="Documents" value={String(documentRows.length)} />
        <CountCard title="Queue rows" value={String(queueRows.length)} />
        <CountCard title="Extraction rows" value={String(extractionRows.length)} />
        <CountCard title="Pipeline runs" value={String(runRows.length)} />
      </div>

      <TableCard
        title="Pipeline runs"
        rows={runRows}
        emptyText="No pipeline runs found."
        limit={50}
        rowKey={(row, index) => `${displayValue(row.run_id)}-${index}`}
        columns={[
          {
            header: 'Run',
            className: 'font-mono text-xs',
            render: (row) => displayValue(row.run_id),
          },
          {
            header: 'Status',
            render: (row) => <Badge variant="outline">{displayValue(row.status)}</Badge>,
          },
          { header: 'Started', render: (row) => displayValue(row.started_at) },
          { header: 'Completed', render: (row) => displayValue(row.completed_at) },
          {
            header: 'Executed query',
            className: 'max-w-[500px] truncate font-mono text-xs',
            render: (row) => displayValue(row.executed_query),
          },
        ]}
      />

      <TableCard
        title="Recent papers (source_documents)"
        rows={documentRows}
        emptyText="No document rows found."
        rowKey={(row, index) => `${displayValue(row.id)}-${index}`}
        columns={[
          {
            header: 'Document ID',
            className: 'font-mono text-xs',
            render: (row) => displayValue(row.id),
          },
          {
            header: 'External Record',
            className: 'font-mono text-xs',
            render: (row) => displayValue(row.external_record_id),
          },
          { header: 'Enrichment', render: (row) => displayValue(row.enrichment_status) },
          { header: 'Extraction', render: (row) => displayValue(row.extraction_status) },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <TableCard
          title="Extraction queue rows"
          rows={queueRows}
          emptyText="No queue rows found."
          rowKey={(row, index) => `${displayValue(row.id)}-${index}`}
          columns={[
            {
              header: 'Queue ID',
              className: 'font-mono text-xs',
              render: (row) => displayValue(row.id),
            },
            {
              header: 'Record',
              className: 'font-mono text-xs',
              render: (row) => displayValue(row.source_record_id),
            },
            { header: 'Status', render: (row) => displayValue(row.status) },
            { header: 'Attempts', render: (row) => displayValue(row.attempts) },
          ]}
        />
        <TableCard
          title="Publication extraction rows"
          rows={extractionRows}
          emptyText="No extraction rows found."
          rowKey={(row, index) => `${displayValue(row.id)}-${index}`}
          columns={[
            {
              header: 'Extraction ID',
              className: 'font-mono text-xs',
              render: (row) => displayValue(row.id),
            },
            { header: 'Status', render: (row) => displayValue(row.status) },
            { header: 'Text source', render: (row) => displayValue(row.text_source) },
            { header: 'Facts', render: (row) => displayValue(row.facts_count) },
          ]}
        />
      </div>
    </div>
  )
}
