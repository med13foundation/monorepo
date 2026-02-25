import type { GraphModel } from '@/lib/graph/model'

export type HoverElementKind = 'node' | 'edge'

export interface GraphHoverEvent {
  kind: HoverElementKind
  id: string
  containerX: number
  containerY: number
}

export interface GraphInteractionHandlers {
  onNodeClick?: (nodeId: string) => void
  onHoverChange?: (event: GraphHoverEvent | null) => void
}

export interface GraphViewAdapter {
  mount(container: HTMLElement): void
  unmount(): void
  setGraph(model: GraphModel): void
  setHighlight(nodeIds: ReadonlySet<string>, edgeIds: ReadonlySet<string>): void
  focusNode(nodeId: string): void
  fit(): void
}
