import { useMemo } from 'react'
import { Waypoints } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import KnowledgeGraphCanvas from '@/components/knowledge-graph/KnowledgeGraphCanvas'
import type { GraphEdge, GraphModel } from '@/lib/graph/model'
import {
  edgeColorForRelationType,
  edgeVisualForStatus,
  nodeVisualForEntityType,
} from '@/lib/graph/style'
import type { KernelGraphSubgraphMeta } from '@/types/kernel'

interface KnowledgeGraphVisualizationProps {
  filteredGraph: GraphModel
  renderGraph: GraphModel
  subgraphMeta: KernelGraphSubgraphMeta | null
  truncationNotice: boolean | undefined
  preCapNodeCount: number
  preCapEdgeCount: number
  isExpandingNodeId: string | null
  neighborhood: {
    nodeIds: Set<string>
    edgeIds: Set<string>
  }
  selectedNodeId: string | null
  onNodeClick: (nodeId: string) => void
  onHoverNodeChange: (nodeId: string | null) => void
  onClearSelection: () => void
}

interface MetricCardProps {
  label: string
  value: number
}

function MetricCard({ label, value }: MetricCardProps) {
  return (
    <Card className="overflow-hidden border-border/80 bg-gradient-to-br from-card via-card to-muted/35">
      <CardContent className="relative py-6">
        <div className="absolute inset-y-0 left-0 w-1 bg-primary/55" />
        <div className="flex items-center justify-between pl-2">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">{label}</div>
            <div className="text-3xl font-semibold tracking-tight">{value}</div>
          </div>
          <Waypoints className="size-8 text-primary/70" />
        </div>
      </CardContent>
    </Card>
  )
}

function confidenceValue(confidence: number): string {
  return `${(confidence * 100).toFixed(1)}%`
}

function isGraphEdge(value: GraphEdge | undefined): value is GraphEdge {
  return Boolean(value)
}

export function KnowledgeGraphVisualization({
  filteredGraph,
  renderGraph,
  subgraphMeta,
  truncationNotice,
  preCapNodeCount,
  preCapEdgeCount,
  isExpandingNodeId,
  neighborhood,
  selectedNodeId,
  onNodeClick,
  onHoverNodeChange,
  onClearSelection,
}: KnowledgeGraphVisualizationProps) {
  const nodeLegend = useMemo(
    () =>
      [...new Set(renderGraph.nodes.map((node) => node.entityType))]
        .slice(0, 7)
        .map((entityType) => ({
          label: entityType,
          visual: nodeVisualForEntityType(entityType),
        })),
    [renderGraph.nodes],
  )

  const statusLegend = useMemo(
    () =>
      [...new Set(filteredGraph.edges.map((edge) => edge.curationStatus))]
        .slice(0, 5)
        .map((status) => ({
          label: status,
          visual: edgeVisualForStatus(status),
        })),
    [filteredGraph.edges],
  )

  const relationLegend = useMemo(
    () =>
      [...new Set(filteredGraph.edges.map((edge) => edge.relationType))]
        .slice(0, 5)
        .map((relationType) => ({
          label: relationType,
          color: edgeColorForRelationType(relationType),
        })),
    [filteredGraph.edges],
  )

  const selectedNode = selectedNodeId ? renderGraph.nodeById[selectedNodeId] ?? null : null

  const selectedEdges = useMemo(
    () =>
      selectedNodeId
        ? [...neighborhood.edgeIds]
            .map((edgeId) => renderGraph.edgeById[edgeId])
            .filter(isGraphEdge)
        : [],
    [neighborhood.edgeIds, renderGraph.edgeById, selectedNodeId],
  )

  const selectedEvidenceCount = selectedEdges.reduce((sum, edge) => sum + edge.sourceCount, 0)
  const curatedEdgeCount = selectedEdges.filter(
    (edge) => edge.curationStatus === 'APPROVED' || edge.curationStatus === 'UNDER_REVIEW',
  ).length
  const averageConfidence = selectedEdges.length
    ? selectedEdges.reduce((sum, edge) => sum + edge.confidence, 0) / selectedEdges.length
    : 0
  const relationBreakdown = useMemo(() => {
    const counts = new Map<string, number>()
    for (const edge of selectedEdges) {
      counts.set(edge.relationType, (counts.get(edge.relationType) ?? 0) + 1)
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 4)
  }, [selectedEdges])

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <MetricCard label="Entities" value={filteredGraph.stats.nodeCount} />
        <MetricCard label="Relations" value={filteredGraph.stats.edgeCount} />
      </div>

      <Card className="overflow-hidden border-border/80 bg-gradient-to-br from-card to-muted/25">
        <CardContent className="space-y-4 py-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline" className="bg-background/90">
              Rendered: {renderGraph.stats.nodeCount} nodes / {renderGraph.stats.edgeCount} edges
            </Badge>
            {subgraphMeta ? (
              <Badge variant="outline" className="bg-background/90">
                Mode: {subgraphMeta.mode} • Depth {subgraphMeta.requested_depth} • Top K{' '}
                {subgraphMeta.requested_top_k}
              </Badge>
            ) : null}
            {truncationNotice ? (
              <Badge variant="secondary" className="bg-accent/80">
                Truncated for performance (pre-cap: {preCapNodeCount} nodes / {preCapEdgeCount}{' '}
                edges)
              </Badge>
            ) : null}
            {isExpandingNodeId ? (
              <Badge variant="outline" className="bg-background/90">
                Expanding {isExpandingNodeId}
              </Badge>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border/70 bg-background/70 px-3 py-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Legend</span>
            {nodeLegend.map((item) => (
              <span key={item.label} className="inline-flex items-center gap-1.5">
                <span
                  className="size-2.5 rounded-full border border-black/10"
                  style={{ backgroundColor: item.visual.fillColor }}
                />
                <span>{item.label}</span>
              </span>
            ))}
            {statusLegend.map((item) => (
              <span key={item.label} className="inline-flex items-center gap-1.5">
                <span
                  className="h-0 w-4 border-t-2"
                  style={{
                    borderTopColor: '#475569',
                    borderTopStyle: item.visual.lineStyle,
                    opacity: item.visual.opacity,
                  }}
                />
                <span>{item.label}</span>
              </span>
            ))}
            {relationLegend.map((item) => (
              <span key={item.label} className="inline-flex items-center gap-1.5">
                <span
                  className="h-0 w-4 border-t-2"
                  style={{
                    borderTopColor: item.color,
                    borderTopStyle: 'solid',
                  }}
                />
                <span>{item.label}</span>
              </span>
            ))}
          </div>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <KnowledgeGraphCanvas
              graph={renderGraph}
              highlightedNodeIds={neighborhood.nodeIds}
              highlightedEdgeIds={neighborhood.edgeIds}
              onNodeClick={onNodeClick}
              onHoverNodeChange={onHoverNodeChange}
            />
            <div className="rounded-xl border border-border/70 bg-background/80 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    Relation Inspect
                  </div>
                  <div className="text-sm font-semibold">Focus Mode</div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!selectedNode}
                  onClick={onClearSelection}
                >
                  Clear
                </Button>
              </div>
              {!selectedNode ? (
                <div className="rounded-lg border border-dashed border-border/70 bg-muted/35 p-3 text-xs text-muted-foreground">
                  Select a node to isolate its neighborhood and inspect evidence strength.
                </div>
              ) : (
                <div className="space-y-3 text-xs">
                  <div>
                    <div className="text-muted-foreground">{selectedNode.entityType}</div>
                    <div className="text-sm font-semibold text-foreground">{selectedNode.label}</div>
                    <div className="truncate font-mono text-[11px] text-muted-foreground">
                      {selectedNode.id}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/70 bg-muted/30 p-2">
                    <div className="text-muted-foreground">Degree</div>
                    <div className="text-right font-semibold">{selectedEdges.length}</div>
                    <div className="text-muted-foreground">Evidence Sources</div>
                    <div className="text-right font-semibold">{selectedEvidenceCount}</div>
                    <div className="text-muted-foreground">Avg Confidence</div>
                    <div className="text-right font-semibold">
                      {confidenceValue(averageConfidence)}
                    </div>
                    <div className="text-muted-foreground">Curated Links</div>
                    <div className="text-right font-semibold">{curatedEdgeCount}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={curatedEdgeCount > 0 ? 'default' : 'secondary'}>
                      {curatedEdgeCount > 0 ? 'Curated Evidence Present' : 'Inferred / Draft Heavy'}
                    </Badge>
                    <Badge variant="outline">
                      Neighborhood: {neighborhood.nodeIds.size} nodes
                    </Badge>
                  </div>
                  <div className="space-y-1.5">
                    <div className="font-medium text-foreground">Top Relation Types</div>
                    {relationBreakdown.length === 0 ? (
                      <div className="text-muted-foreground">No incident relations in view.</div>
                    ) : (
                      relationBreakdown.map(([relationType, count]) => (
                        <div
                          key={relationType}
                          className="flex items-center justify-between rounded-md border border-border/60 px-2 py-1"
                        >
                          <span className="truncate font-mono">{relationType}</span>
                          <span className="font-semibold">{count}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  )
}
