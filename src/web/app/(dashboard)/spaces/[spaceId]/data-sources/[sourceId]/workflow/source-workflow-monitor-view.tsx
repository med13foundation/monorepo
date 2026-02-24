import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SourcePipelineRunsResponse, SourceWorkflowMonitorResponse } from '@/types/kernel'

import { SummaryRow, TableCard } from './source-workflow-monitor-primitives'
import { asList, asRecord, displayValue } from './source-workflow-monitor-utils'

interface SourceWorkflowMonitorViewProps {
  spaceId: string
  selectedRunId?: string
  monitor: SourceWorkflowMonitorResponse | null
  monitorError: string | null
  pipelineRuns: SourcePipelineRunsResponse | null
}

export function SourceWorkflowMonitorView({
  spaceId,
  selectedRunId,
  monitor,
  monitorError,
  pipelineRuns,
}: SourceWorkflowMonitorViewProps) {
  const sourceSnapshot = asRecord(monitor?.source_snapshot)
  const schedule = asRecord(sourceSnapshot.schedule)
  const runRows = asList(pipelineRuns?.runs ?? monitor?.pipeline_runs ?? [])
  const documentRows = asList(monitor?.documents)
  const queueRows = asList(monitor?.extraction_queue)
  const extractionRows = asList(monitor?.publication_extractions)
  const relationReview = asRecord(monitor?.relation_review)
  const relationRows = asList(relationReview.persisted_relation_rows)
  const pendingRelationRows = asList(relationReview.pending_review_relation_rows)
  const reviewQueueRows = asList(relationReview.review_queue_rows)
  const rejectedRows = asList(relationReview.rejected_relation_rows)
  const graphSummary = asRecord(monitor?.graph_summary)
  const warnings = Array.isArray(monitor?.warnings)
    ? monitor?.warnings.filter((item): item is string => typeof item === 'string')
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Source Workflow Monitor</h1>
          <p className="text-sm text-muted-foreground">
            Source: {displayValue(sourceSnapshot.name)} ({displayValue(sourceSnapshot.source_type)})
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href={`/spaces/${spaceId}/data-sources`}>Back to data sources</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={`/spaces/${spaceId}/knowledge-graph`}>Open graph</Link>
          </Button>
        </div>
      </div>

      {monitorError ? (
        <Card>
          <CardContent className="py-8 text-sm text-destructive">{monitorError}</CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Run summary</CardTitle>
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
              {warnings.length > 0 && (
                <div className="space-y-1 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <div className="font-semibold">Warnings</div>
                  {warnings.map((warning, index) => (
                    <div key={`${warning}-${index}`}>- {warning}</div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

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

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Papers queue</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <SummaryRow label="Documents" value={String(documentRows.length)} />
                <SummaryRow label="Queue rows" value={String(queueRows.length)} />
                <SummaryRow label="Extractions" value={String(extractionRows.length)} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Relation review</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <SummaryRow label="Persisted relation rows" value={String(relationRows.length)} />
                <SummaryRow label="Pending review rows" value={String(pendingRelationRows.length)} />
                <SummaryRow label="Review queue rows" value={String(reviewQueueRows.length)} />
                <SummaryRow label="Rejected rows" value={String(rejectedRows.length)} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Graph snapshot</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <SummaryRow label="Nodes" value={displayValue(graphSummary.node_count)} />
                <SummaryRow label="Edges" value={displayValue(graphSummary.edge_count)} />
                <SummaryRow
                  label="Edges from this source"
                  value={displayValue(graphSummary.source_edge_count)}
                />
              </CardContent>
            </Card>
          </div>

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

          <TableCard
            title="Relation rows (with evidence context)"
            rows={relationRows}
            emptyText="No relation rows found."
            limit={30}
            rowKey={(row, index) => `${displayValue(row.evidence_id)}-${index}`}
            columns={[
              {
                header: 'Document',
                className: 'font-mono text-xs',
                render: (row) => displayValue(row.document_id),
              },
              { header: 'Relation', render: (row) => displayValue(row.relation_type) },
              {
                header: 'Status',
                render: (row) => <Badge variant="outline">{displayValue(row.curation_status)}</Badge>,
              },
              {
                header: 'Source -> Target',
                className: 'text-xs',
                render: (row) =>
                  `${displayValue(row.source_entity_label)} -> ${displayValue(row.target_entity_label)}`,
              },
              {
                header: 'Evidence',
                className: 'max-w-[420px] truncate text-xs',
                render: (row) => displayValue(row.evidence_summary),
              },
            ]}
          />

          <TableCard
            title="Rejected relation details (per extraction)"
            rows={rejectedRows}
            emptyText="No rejected relation rows found."
            limit={30}
            rowKey={(row, index) => `${displayValue(row.extraction_id)}-${index}`}
            columns={[
              {
                header: 'Document',
                className: 'font-mono text-xs',
                render: (row) => displayValue(row.document_id),
              },
              { header: 'Reason', render: (row) => displayValue(row.reason) },
              { header: 'Status', render: (row) => displayValue(row.status) },
              {
                header: 'Queue Item',
                className: 'font-mono text-xs',
                render: (row) => displayValue(row.queue_item_id),
              },
            ]}
          />
        </>
      )}
    </div>
  )
}
