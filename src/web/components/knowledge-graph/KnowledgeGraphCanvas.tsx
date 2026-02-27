'use client'

import { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { GraphEdge, GraphModel, GraphNode } from '@/lib/graph/model'
import { CytoscapeGraphViewAdapter } from '@/lib/graph/cytoscape-adapter'
import type { GraphHoverEvent } from '@/lib/graph/view-adapter'

interface KnowledgeGraphCanvasProps {
  graph: GraphModel
  highlightedNodeIds: ReadonlySet<string>
  highlightedEdgeIds: ReadonlySet<string>
  onNodeClick: (nodeId: string) => void
  onHoverNodeChange?: (nodeId: string | null) => void
  /** Called on any tap on the canvas (background, node, or edge). Use e.g. to collapse overlays. */
  onCanvasTap?: () => void
  chrome?: 'full' | 'minimal' | 'none'
  className?: string
}

interface TooltipPosition {
  left: number
  top: number
}

const TOOLTIP_WIDTH = 280
const TOOLTIP_HEIGHT = 152
const MAP_GRID_STYLE: CSSProperties = {
  backgroundImage:
    'linear-gradient(to right, rgba(100, 116, 139, 0.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(100, 116, 139, 0.1) 1px, transparent 1px)',
  backgroundSize: '44px 44px',
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, max))
}

function tooltipPosition(
  hoverEvent: GraphHoverEvent,
  containerWidth: number,
  containerHeight: number,
): TooltipPosition {
  const rawLeft = hoverEvent.containerX + 14
  const rawTop = hoverEvent.containerY + 14
  return {
    left: clamp(rawLeft, 8, Math.max(8, containerWidth - TOOLTIP_WIDTH - 8)),
    top: clamp(rawTop, 8, Math.max(8, containerHeight - TOOLTIP_HEIGHT - 8)),
  }
}

function confidencePercent(confidence: number): string {
  return `${(confidence * 100).toFixed(1)}%`
}

function formattedDate(value: string): string {
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) {
    return 'Unknown'
  }
  return new Date(parsed).toLocaleDateString()
}

function NodeTooltipContent({ node, degree }: { node: GraphNode; degree: number }) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {node.entityType}
      </div>
      <div className="text-sm font-medium text-foreground">{node.label}</div>
      <div className="truncate font-mono text-[11px] text-muted-foreground">{node.id}</div>
      <div className="grid grid-cols-2 gap-x-2 gap-y-1 border-t pt-2 text-[11px] text-muted-foreground">
        <div>Connections</div>
        <div className="text-right font-semibold text-foreground">{degree}</div>
        <div>Updated</div>
        <div className="text-right">{formattedDate(node.updatedAt)}</div>
      </div>
    </div>
  )
}

function EdgeTooltipContent({ edge }: { edge: GraphEdge }) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {edge.relationType}
      </div>
      <div className="text-sm font-medium text-foreground">
        {edge.curationStatus} • {confidencePercent(edge.confidence)}
      </div>
      <div className="truncate font-mono text-[11px] text-muted-foreground">{edge.id}</div>
      <div className="grid grid-cols-2 gap-x-2 gap-y-1 border-t pt-2 text-[11px] text-muted-foreground">
        <div>Evidence Sources</div>
        <div className="text-right font-semibold text-foreground">{edge.sourceCount}</div>
        <div>Tier</div>
        <div className="truncate text-right">{edge.highestEvidenceTier ?? 'Unknown'}</div>
      </div>
    </div>
  )
}

export default function KnowledgeGraphCanvas({
  graph,
  highlightedNodeIds,
  highlightedEdgeIds,
  onNodeClick,
  onHoverNodeChange,
  onCanvasTap,
  chrome = 'full',
  className,
}: KnowledgeGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const adapterRef = useRef<CytoscapeGraphViewAdapter | null>(null)
  const [hoverEvent, setHoverEvent] = useState<GraphHoverEvent | null>(null)
  const hoverKeyRef = useRef<string>('none')
  const hoveredNodeIdRef = useRef<string | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return undefined
    }

    const adapter = new CytoscapeGraphViewAdapter({
      onNodeClick: (nodeId) => {
        onNodeClick(nodeId)
        adapterRef.current?.focusNode(nodeId)
      },
      onCanvasTap,
      onHoverChange: (event) => {
        const nextHoverKey = event ? `${event.kind}:${event.id}` : 'none'
        if (nextHoverKey !== hoverKeyRef.current) {
          hoverKeyRef.current = nextHoverKey
          setHoverEvent(event)
        }

        const nextHoveredNodeId = !event || event.kind !== 'node' ? null : event.id
        if (nextHoveredNodeId !== hoveredNodeIdRef.current) {
          hoveredNodeIdRef.current = nextHoveredNodeId
          onHoverNodeChange?.(nextHoveredNodeId)
        }
      },
    })
    adapter.mount(container)
    adapterRef.current = adapter

    return () => {
      adapter.unmount()
      adapterRef.current = null
      hoverKeyRef.current = 'none'
      hoveredNodeIdRef.current = null
    }
  }, [onCanvasTap, onHoverNodeChange, onNodeClick])

  useEffect(() => {
    adapterRef.current?.setGraph(graph)
  }, [graph])

  useEffect(() => {
    adapterRef.current?.setHighlight(highlightedNodeIds, highlightedEdgeIds)
  }, [highlightedEdgeIds, highlightedNodeIds])

  const hasRenderableGraph = graph.stats.nodeCount > 0

  const tooltip = useMemo(() => {
    if (!hoverEvent || !containerRef.current) {
      return null
    }
    const rect = containerRef.current.getBoundingClientRect()
    const position = tooltipPosition(hoverEvent, rect.width, rect.height)
    if (hoverEvent.kind === 'node') {
      const node = graph.nodeById[hoverEvent.id]
      if (!node) {
        return null
      }
      return {
        content: (
          <NodeTooltipContent
            node={node}
            degree={graph.incidentEdges[node.id]?.length ?? 0}
          />
        ),
        position,
      }
    }
    const edge = graph.edgeById[hoverEvent.id]
    if (!edge) {
      return null
    }
    return {
      content: <EdgeTooltipContent edge={edge} />,
      position,
    }
  }, [graph.edgeById, graph.incidentEdges, graph.nodeById, hoverEvent])

  const isMinimalChrome = chrome === 'minimal'

  return (
    <div
      className={cn(
        'relative h-[560px] w-full overflow-hidden rounded-xl border border-border/80 bg-[linear-gradient(168deg,#f8fbfc_0%,#eef4f6_100%)] shadow-brand-sm',
        isMinimalChrome && 'shadow-none',
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 opacity-55" style={MAP_GRID_STYLE} />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_16%_14%,rgba(20,184,166,0.1),transparent_48%),radial-gradient(circle_at_84%_84%,rgba(59,130,246,0.06),transparent_44%)]" />
      {!isMinimalChrome && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-background/55 to-transparent" />
      )}
      <div ref={containerRef} className="relative z-10 size-full" />

      {chrome === 'full' ? (
        <div className="absolute left-3 top-3 z-20 flex items-center gap-2">
          <Badge variant="outline" className="bg-background/85 backdrop-blur">
            Interactive Graph
          </Badge>
          <div className="hidden text-xs text-muted-foreground md:block">
            Click a node to focus and expand. Edge labels appear on hover and focus.
          </div>
        </div>
      ) : null}
      {chrome === 'full' || chrome === 'minimal' ? (
        <div className="absolute right-3 top-3 z-20 flex flex-col items-end gap-2">
          <div className="inline-flex flex-col overflow-hidden rounded-lg border border-border/70 bg-background/90 shadow-brand-sm backdrop-blur">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Zoom in"
              disabled={!hasRenderableGraph}
              className="size-8 rounded-none p-0"
              onClick={() => adapterRef.current?.zoomIn()}
            >
              <Plus className="size-4" />
            </Button>
            <div className="h-px bg-border/70" />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Zoom out"
              disabled={!hasRenderableGraph}
              className="size-8 rounded-none p-0"
              onClick={() => adapterRef.current?.zoomOut()}
            >
              <Minus className="size-4" />
            </Button>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!hasRenderableGraph}
            className="h-8 bg-background/90 backdrop-blur"
            onClick={() => adapterRef.current?.fit()}
          >
            Fit View
          </Button>
        </div>
      ) : null}

      {!hasRenderableGraph ? (
        <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center p-8">
          <div className="max-w-sm rounded-xl border border-border/70 bg-background/90 px-6 py-4 text-center shadow-brand-sm backdrop-blur">
            <div className="text-sm font-semibold text-foreground">
              No graph elements in the current view
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Run a graph search, load the starter subgraph, or relax local filters.
            </div>
          </div>
        </div>
      ) : null}

      {tooltip && (
        <div
          className="pointer-events-none absolute z-30 w-[280px] rounded-lg border border-border/70 bg-background/95 p-3 shadow-brand-sm backdrop-blur"
          style={{
            left: `${tooltip.position.left}px`,
            top: `${tooltip.position.top}px`,
          }}
        >
          {tooltip.content}
        </div>
      )}
    </div>
  )
}
