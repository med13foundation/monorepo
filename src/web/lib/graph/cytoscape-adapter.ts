import cytoscape, {
  type Core,
  type ElementDefinition,
  type EventObjectEdge,
  type EventObjectNode,
  type LayoutOptions,
} from 'cytoscape'
import type { GraphEdge, GraphModel } from '@/lib/graph/model'
import {
  edgeColorForRelationType,
  edgeStrengthScore,
  edgeVisualForStatus,
  nodeVisualForEntityType,
} from '@/lib/graph/style'
import type {
  GraphInteractionHandlers,
  GraphViewAdapter,
  HoverElementKind,
} from '@/lib/graph/view-adapter'

const CY_NODE_HIGHLIGHT_CLASS = 'kg-highlight'
const CY_NODE_DIM_CLASS = 'kg-dim'
const CY_EDGE_HIGHLIGHT_CLASS = 'kg-highlight'
const CY_EDGE_DIM_CLASS = 'kg-dim'
const CY_EDGE_FOCUS_LABEL_CLASS = 'kg-edge-label-focus'
const CY_EDGE_HOVER_LABEL_CLASS = 'kg-edge-label-hover'

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')
}

function nodeSizeForDegree(degree: number, maxDegree: number): number {
  if (maxDegree <= 0) {
    return 28
  }
  const ratio = Math.max(0, Math.min(1, degree / maxDegree))
  return Math.round(24 + Math.sqrt(ratio) * 42)
}

function nodeShapeClass(shape: string): string {
  return `kg-shape-${shape}`
}

function edgeStatusClass(status: string): string {
  return `kg-edge-status-${normalizeToken(status)}`
}

function edgeLineStyleClass(lineStyle: string): string {
  return `kg-edge-style-${lineStyle}`
}

function edgeStrengthClass(confidence: number, sourceCount: number): string {
  const score = edgeStrengthScore(confidence, sourceCount)
  if (score >= 0.9) {
    return 'kg-edge-strength-high'
  }
  if (score >= 0.72) {
    return 'kg-edge-strength-medium'
  }
  return 'kg-edge-strength-low'
}

function buildLayoutOptions(model: GraphModel): LayoutOptions {
  const elementCount = model.nodes.length + model.edges.length
  const shouldAnimate = elementCount <= 120
  if (model.edges.length === 0) {
    return {
      name: 'grid',
      fit: true,
      padding: 40,
      avoidOverlap: true,
      animate: shouldAnimate,
      animationDuration: 220,
    } as LayoutOptions
  }
  return {
    name: 'cose',
    animate: shouldAnimate,
    animationDuration: 320,
    fit: true,
    padding: 34,
    nodeRepulsion: 7800,
    idealEdgeLength: 146,
    edgeElasticity: 75,
    gravity: 0.35,
    nestingFactor: 0.9,
    randomize: false,
  } as LayoutOptions
}

function buildElements(model: GraphModel): ElementDefinition[] {
  const degreeByNodeId: Record<string, number> = {}
  let maxDegree = 0
  for (const node of model.nodes) {
    const degree = model.incidentEdges[node.id]?.length ?? 0
    degreeByNodeId[node.id] = degree
    maxDegree = Math.max(maxDegree, degree)
  }

  const nodeElements: ElementDefinition[] = model.nodes.map((node) => {
    const visual = nodeVisualForEntityType(node.entityType)
    const degree = degreeByNodeId[node.id] ?? 0

    return {
      classes: nodeShapeClass(visual.shape),
      data: {
        id: node.id,
        label: node.label,
        entityType: node.entityType,
        color: visual.fillColor,
        borderColor: visual.borderColor,
        size: nodeSizeForDegree(degree, maxDegree),
        degree,
      },
    }
  })

  const edgeElements: ElementDefinition[] = model.edges.map((edge) => {
    const statusVisual = edgeVisualForStatus(edge.curationStatus)

    return {
      classes: [
        edgeStatusClass(edge.curationStatus),
        edgeLineStyleClass(statusVisual.lineStyle),
        edgeStrengthClass(edge.confidence, edge.sourceCount),
      ].join(' '),
      data: {
        id: edge.id,
        source: edge.sourceId,
        target: edge.targetId,
        label: edge.relationType,
        curationStatus: edge.curationStatus,
        confidence: edge.confidence,
        color: edgeColorForRelationType(edge.relationType),
      },
    }
  })

  return [...nodeElements, ...edgeElements]
}

function hoverCoordinatesForNode(event: EventObjectNode): { x: number; y: number } {
  return {
    x: event.renderedPosition.x,
    y: event.renderedPosition.y,
  }
}

function hoverCoordinatesForEdge(event: EventObjectEdge): { x: number; y: number } {
  if (event.renderedPosition) {
    return {
      x: event.renderedPosition.x,
      y: event.renderedPosition.y,
    }
  }
  const midpoint = event.target.midpoint()
  return {
    x: midpoint.x,
    y: midpoint.y,
  }
}

function emitHover(
  handlers: GraphInteractionHandlers,
  kind: HoverElementKind,
  id: string,
  x: number,
  y: number,
): void {
  handlers.onHoverChange?.({
    kind,
    id,
    containerX: x,
    containerY: y,
  })
}

function applyClassHighlight(
  cy: Core,
  highlightedNodeIds: ReadonlySet<string>,
  highlightedEdgeIds: ReadonlySet<string>,
): void {
  cy.nodes().removeClass(CY_NODE_HIGHLIGHT_CLASS).removeClass(CY_NODE_DIM_CLASS)
  cy.edges()
    .removeClass(CY_EDGE_HIGHLIGHT_CLASS)
    .removeClass(CY_EDGE_DIM_CLASS)
    .removeClass(CY_EDGE_FOCUS_LABEL_CLASS)

  const hasNodeHighlights = highlightedNodeIds.size > 0
  const hasEdgeHighlights = highlightedEdgeIds.size > 0
  if (!hasNodeHighlights && !hasEdgeHighlights) {
    return
  }

  const nodeHighlights = cy.nodes().filter((node) => highlightedNodeIds.has(node.id()))
  const edgeHighlights = cy.edges().filter((edge) => highlightedEdgeIds.has(edge.id()))

  nodeHighlights.addClass(CY_NODE_HIGHLIGHT_CLASS)
  edgeHighlights.addClass(CY_EDGE_HIGHLIGHT_CLASS)
  edgeHighlights.addClass(CY_EDGE_FOCUS_LABEL_CLASS)
  cy.nodes().not(nodeHighlights).addClass(CY_NODE_DIM_CLASS)
  cy.edges().not(edgeHighlights).addClass(CY_EDGE_DIM_CLASS)
}

export class CytoscapeGraphViewAdapter implements GraphViewAdapter {
  private cy: Core | null = null
  private readonly handlers: GraphInteractionHandlers
  private graph: GraphModel | null = null

  public constructor(handlers: GraphInteractionHandlers) {
    this.handlers = handlers
  }

  public mount(container: HTMLElement): void {
    if (this.cy) {
      return
    }

    this.cy = cytoscape({
      container,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(color)',
            'background-opacity': 0.96,
            label: 'data(label)',
            color: '#0f172a',
            'font-size': '10px',
            'font-weight': 700,
            'text-wrap': 'wrap',
            'text-max-width': '125px',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 6,
            width: 'data(size)',
            height: 'data(size)',
            'border-color': 'data(borderColor)',
            'border-width': 2.4,
            'text-background-color': '#f8fafc',
            'text-background-opacity': 0.92,
            'text-background-padding': '2.5px',
            'text-border-color': '#ffffff',
            'text-border-opacity': 0.8,
            'text-border-width': 0.4,
            'overlay-opacity': 0,
          },
        },
        {
          selector: 'node.kg-shape-ellipse',
          style: {
            shape: 'ellipse',
          },
        },
        {
          selector: 'node.kg-shape-round-rectangle',
          style: {
            shape: 'round-rectangle',
          },
        },
        {
          selector: 'node.kg-shape-diamond',
          style: {
            shape: 'diamond',
          },
        },
        {
          selector: 'node.kg-shape-hexagon',
          style: {
            shape: 'hexagon',
          },
        },
        {
          selector: 'node.kg-shape-triangle',
          style: {
            shape: 'triangle',
          },
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'line-color': 'data(color)',
            width: 2.6,
            opacity: 0.58,
            'line-style': 'solid',
            'target-arrow-color': 'data(color)',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.95,
            label: '',
            color: '#1f2937',
            'font-size': '9px',
            'font-weight': 600,
            'text-background-color': '#f8fafc',
            'text-background-opacity': 0,
            'text-background-padding': '2px',
            'text-rotation': 'autorotate',
            'text-events': 'no',
            'overlay-opacity': 0,
          },
        },
        {
          selector: 'edge.kg-edge-style-dashed',
          style: {
            'line-style': 'dashed',
          },
        },
        {
          selector: 'edge.kg-edge-style-dotted',
          style: {
            'line-style': 'dotted',
          },
        },
        {
          selector: 'edge.kg-edge-strength-high',
          style: {
            width: 5.2,
          },
        },
        {
          selector: 'edge.kg-edge-strength-medium',
          style: {
            width: 3.8,
          },
        },
        {
          selector: 'edge.kg-edge-strength-low',
          style: {
            width: 2.7,
          },
        },
        {
          selector: 'edge.kg-edge-status-approved',
          style: {
            opacity: 0.9,
          },
        },
        {
          selector: 'edge.kg-edge-status-under-review',
          style: {
            opacity: 0.68,
          },
        },
        {
          selector: 'edge.kg-edge-status-draft',
          style: {
            opacity: 0.45,
          },
        },
        {
          selector: 'edge.kg-edge-status-rejected',
          style: {
            opacity: 0.28,
          },
        },
        {
          selector: 'edge.kg-edge-status-retracted',
          style: {
            opacity: 0.2,
          },
        },
        {
          selector: `edge.${CY_EDGE_FOCUS_LABEL_CLASS}, edge.${CY_EDGE_HOVER_LABEL_CLASS}, edge:selected`,
          style: {
            label: 'data(label)',
            'text-background-opacity': 0.92,
          },
        },
        {
          selector: `node.${CY_NODE_HIGHLIGHT_CLASS}`,
          style: {
            'border-color': '#0f766e',
            'border-width': 4,
            opacity: 1,
          },
        },
        {
          selector: `edge.${CY_EDGE_HIGHLIGHT_CLASS}`,
          style: {
            width: 6.4,
            opacity: 1,
            'z-index': 20,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#0f766e',
            'border-width': 4.5,
            opacity: 1,
          },
        },
        {
          selector: `node.${CY_NODE_DIM_CLASS}`,
          style: {
            opacity: 0.1,
          },
        },
        {
          selector: `edge.${CY_EDGE_DIM_CLASS}`,
          style: {
            opacity: 0.06,
          },
        },
      ],
      layout: { name: 'grid', fit: true, padding: 20 },
      wheelSensitivity: 0.2,
      minZoom: 0.1,
      maxZoom: 4,
    })

    this.cy.on('tap', 'node', (event: EventObjectNode) => {
      this.handlers.onNodeClick?.(event.target.id())
    })
    this.cy.on('mouseover', 'node', (event: EventObjectNode) => {
      const coordinates = hoverCoordinatesForNode(event)
      event.target.connectedEdges().addClass(CY_EDGE_HOVER_LABEL_CLASS)
      emitHover(this.handlers, 'node', event.target.id(), coordinates.x, coordinates.y)
    })
    this.cy.on('mouseout', 'node', (event: EventObjectNode) => {
      event.target.connectedEdges().removeClass(CY_EDGE_HOVER_LABEL_CLASS)
      this.handlers.onHoverChange?.(null)
    })
    this.cy.on('mouseover', 'edge', (event: EventObjectEdge) => {
      const coordinates = hoverCoordinatesForEdge(event)
      event.target.addClass(CY_EDGE_HOVER_LABEL_CLASS)
      emitHover(this.handlers, 'edge', event.target.id(), coordinates.x, coordinates.y)
    })
    this.cy.on('mouseout', 'edge', (event: EventObjectEdge) => {
      event.target.removeClass(CY_EDGE_HOVER_LABEL_CLASS)
      this.handlers.onHoverChange?.(null)
    })
  }

  public unmount(): void {
    this.handlers.onHoverChange?.(null)
    this.cy?.destroy()
    this.cy = null
  }

  public setGraph(model: GraphModel): void {
    this.graph = model
    if (!this.cy) {
      return
    }

    const elements = buildElements(model)
    this.cy.batch(() => {
      this.cy?.elements().remove()
      this.cy?.add(elements)
    })

    this.cy.layout(buildLayoutOptions(model)).run()
  }

  public setHighlight(
    highlightedNodeIds: ReadonlySet<string>,
    highlightedEdgeIds: ReadonlySet<string>,
  ): void {
    if (!this.cy) {
      return
    }
    applyClassHighlight(this.cy, highlightedNodeIds, highlightedEdgeIds)
  }

  public focusNode(nodeId: string): void {
    if (!this.cy) {
      return
    }
    const node = this.cy.getElementById(nodeId)
    if (!node.nonempty()) {
      return
    }
    node.select()
    const neighborhood = node.closedNeighborhood()
    this.cy.stop()
    this.cy.animate({
      fit: {
        eles: neighborhood,
        padding: 84,
      },
      duration: 380,
      easing: 'ease-out-cubic',
    })
  }

  public fit(): void {
    if (!this.cy || !this.graph || this.graph.edges.length + this.graph.nodes.length === 0) {
      return
    }
    this.cy.fit(undefined, 32)
  }
}

export function relationDetails(edge: GraphEdge): string {
  const confidencePct = (edge.confidence * 100).toFixed(1)
  return `${edge.relationType} (${edge.curationStatus}, ${confidencePct}%)`
}
