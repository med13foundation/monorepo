import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import { TableCard } from './source-workflow-monitor-primitives'
import { asList, displayValue, type MonitorRow } from './source-workflow-monitor-utils'
import { CountCard } from './source-workflow-monitor-section-primitives'

interface ReviewTabSectionProps {
  relationRows: MonitorRow[]
  pendingRelationRows: MonitorRow[]
  reviewQueueRows: MonitorRow[]
  rejectedRows: MonitorRow[]
}

interface GraphTabSectionProps {
  spaceId: string
  graphSummary: MonitorRow
}

export function ReviewTabSection({
  relationRows,
  pendingRelationRows,
  reviewQueueRows,
  rejectedRows,
}: ReviewTabSectionProps) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-4">
        <CountCard title="Persisted rows" value={String(relationRows.length)} />
        <CountCard title="Pending rows" value={String(pendingRelationRows.length)} />
        <CountCard title="Review queue" value={String(reviewQueueRows.length)} />
        <CountCard title="Rejected rows" value={String(rejectedRows.length)} />
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
    </div>
  )
}

export function GraphTabSection({ spaceId, graphSummary }: GraphTabSectionProps) {
  const topRelationTypes = asList(graphSummary.top_relation_types)

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <CountCard title="Nodes" value={displayValue(graphSummary.node_count)} />
        <CountCard title="Edges" value={displayValue(graphSummary.edge_count)} />
        <CountCard title="Edges from this source" value={displayValue(graphSummary.source_edge_count)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Top relation types</CardTitle>
        </CardHeader>
        <CardContent>
          {topRelationTypes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No relation distribution available yet.</p>
          ) : (
            <div className="space-y-2">
              {topRelationTypes.map((item, index) => (
                <div
                  key={`${displayValue(item.relation_type)}-${index}`}
                  className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                >
                  <span className="font-medium">{displayValue(item.relation_type)}</span>
                  <Badge variant="outline">{displayValue(item.count)}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button asChild variant="outline">
          <Link href={`/spaces/${spaceId}/knowledge-graph`}>Open full graph view</Link>
        </Button>
      </div>
    </div>
  )
}
