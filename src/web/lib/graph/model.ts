import type {
  KernelEntityResponse,
  KernelGraphExportResponse,
  KernelGraphSubgraphResponse,
  KernelRelationResponse,
  RelationClaimResponse,
} from '@/types/kernel'
import type { JSONObject } from '@/types/generated'

export interface GraphNode {
  id: string
  entityType: string
  label: string
  metadata: JSONObject
  createdAt: string
  updatedAt: string
}

export interface GraphEdge {
  id: string
  sourceId: string
  targetId: string
  relationType: string
  curationStatus: string
  confidence: number
  provenanceId: string | null
  createdAt: string
  updatedAt: string
  sourceCount: number
  highestEvidenceTier: string | null
}

export interface GraphStats {
  nodeCount: number
  edgeCount: number
}

export interface GraphModel {
  nodes: GraphNode[]
  edges: GraphEdge[]
  nodeById: Record<string, GraphNode>
  edgeById: Record<string, GraphEdge>
  adjacency: Record<string, string[]>
  incidentEdges: Record<string, string[]>
  relationTypes: string[]
  curationStatuses: string[]
  stats: GraphStats
}

export interface GraphPruneResult {
  model: GraphModel
  preCapNodeCount: number
  preCapEdgeCount: number
  truncatedNodes: boolean
  truncatedEdges: boolean
}

export interface GraphNeighborhood {
  nodeIds: Set<string>
  edgeIds: Set<string>
}

type GraphSource = Pick<KernelGraphExportResponse, 'nodes' | 'edges'> | Pick<KernelGraphSubgraphResponse, 'nodes' | 'edges'>

const CURATION_STATUS_PRIORITY: Record<string, number> = {
  APPROVED: 5,
  UNDER_REVIEW: 4,
  DRAFT: 3,
  REJECTED: 2,
  RETRACTED: 1,
}

const CLAIM_STATUS_TO_CURATION_STATUS: Record<
  RelationClaimResponse['claim_status'],
  string | null
> = {
  OPEN: 'DRAFT',
  NEEDS_MAPPING: 'UNDER_REVIEW',
  REJECTED: 'REJECTED',
  RESOLVED: null,
}

function safeTimestamp(value: string): number {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function curationPriority(status: string): number {
  return CURATION_STATUS_PRIORITY[status.toUpperCase()] ?? 0
}

function normalizeNode(node: KernelEntityResponse): GraphNode {
  return {
    id: node.id,
    entityType: node.entity_type,
    label: node.display_label ?? node.id,
    metadata: node.metadata,
    createdAt: node.created_at,
    updatedAt: node.updated_at,
  }
}

function relationConfidence(relation: KernelRelationResponse): number {
  if (typeof relation.aggregate_confidence === 'number') {
    return relation.aggregate_confidence
  }
  if (typeof relation.confidence === 'number') {
    return relation.confidence
  }
  return 0
}

function normalizeEdge(edge: KernelRelationResponse): GraphEdge {
  return {
    id: edge.id,
    sourceId: edge.source_id,
    targetId: edge.target_id,
    relationType: edge.relation_type,
    curationStatus: edge.curation_status,
    confidence: relationConfidence(edge),
    provenanceId: edge.provenance_id,
    createdAt: edge.created_at,
    updatedAt: edge.updated_at,
    sourceCount: edge.source_count ?? 0,
    highestEvidenceTier: edge.highest_evidence_tier ?? edge.evidence_tier ?? null,
  }
}

function sortNodes(nodes: GraphNode[]): GraphNode[] {
  return [...nodes].sort((left, right) => {
    const updatedDelta = safeTimestamp(right.updatedAt) - safeTimestamp(left.updatedAt)
    if (updatedDelta !== 0) {
      return updatedDelta
    }
    return left.id.localeCompare(right.id)
  })
}

function sortEdges(edges: GraphEdge[]): GraphEdge[] {
  return [...edges].sort((left, right) => {
    const priorityDelta = curationPriority(right.curationStatus) - curationPriority(left.curationStatus)
    if (priorityDelta !== 0) {
      return priorityDelta
    }
    const updatedDelta = safeTimestamp(right.updatedAt) - safeTimestamp(left.updatedAt)
    if (updatedDelta !== 0) {
      return updatedDelta
    }
    return left.id.localeCompare(right.id)
  })
}

function uniqueSortedValues(values: Iterable<string>): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right))
}

function ensureNodeRecord(
  record: Record<string, string[]>,
  nodeId: string,
): string[] {
  if (!record[nodeId]) {
    record[nodeId] = []
  }
  return record[nodeId]
}

export function emptyGraphModel(): GraphModel {
  return {
    nodes: [],
    edges: [],
    nodeById: {},
    edgeById: {},
    adjacency: {},
    incidentEdges: {},
    relationTypes: [],
    curationStatuses: [],
    stats: {
      nodeCount: 0,
      edgeCount: 0,
    },
  }
}

export function buildGraphModel(source: GraphSource): GraphModel {
  const nodeById: Record<string, GraphNode> = {}
  for (const node of source.nodes) {
    const normalized = normalizeNode(node)
    const existing = nodeById[normalized.id]
    if (!existing || safeTimestamp(normalized.updatedAt) > safeTimestamp(existing.updatedAt)) {
      nodeById[normalized.id] = normalized
    }
  }

  const edgeById: Record<string, GraphEdge> = {}
  for (const edge of source.edges) {
    const normalized = normalizeEdge(edge)
    if (!nodeById[normalized.sourceId] || !nodeById[normalized.targetId]) {
      continue
    }
    const existing = edgeById[normalized.id]
    if (!existing || safeTimestamp(normalized.updatedAt) > safeTimestamp(existing.updatedAt)) {
      edgeById[normalized.id] = normalized
    }
  }

  const nodes = sortNodes(Object.values(nodeById))
  const edges = sortEdges(Object.values(edgeById))
  const adjacency: Record<string, string[]> = {}
  const incidentEdges: Record<string, string[]> = {}

  for (const node of nodes) {
    adjacency[node.id] = []
    incidentEdges[node.id] = []
  }

  for (const edge of edges) {
    const sourceAdjacency = ensureNodeRecord(adjacency, edge.sourceId)
    const targetAdjacency = ensureNodeRecord(adjacency, edge.targetId)
    const sourceIncident = ensureNodeRecord(incidentEdges, edge.sourceId)
    const targetIncident = ensureNodeRecord(incidentEdges, edge.targetId)

    if (!sourceAdjacency.includes(edge.targetId)) {
      sourceAdjacency.push(edge.targetId)
    }
    if (!targetAdjacency.includes(edge.sourceId)) {
      targetAdjacency.push(edge.sourceId)
    }
    sourceIncident.push(edge.id)
    targetIncident.push(edge.id)
  }

  return {
    nodes,
    edges,
    nodeById,
    edgeById,
    adjacency,
    incidentEdges,
    relationTypes: uniqueSortedValues(edges.map((edge) => edge.relationType)),
    curationStatuses: uniqueSortedValues(edges.map((edge) => edge.curationStatus)),
    stats: {
      nodeCount: nodes.length,
      edgeCount: edges.length,
    },
  }
}

function nodeLookupKey(entityType: string, label: string): string {
  return `${entityType.trim().toUpperCase()}::${label.trim().toUpperCase()}`
}

function graphNodesToKernelNodes(nodes: GraphNode[]): KernelEntityResponse[] {
  return nodes.map((node) => ({
    id: node.id,
    research_space_id: '',
    entity_type: node.entityType,
    display_label: node.label,
    metadata: node.metadata,
    created_at: node.createdAt,
    updated_at: node.updatedAt,
  }))
}

function graphEdgesToKernelEdges(edges: GraphEdge[]): KernelRelationResponse[] {
  return edges.map((edge) => ({
    id: edge.id,
    research_space_id: '',
    source_id: edge.sourceId,
    relation_type: edge.relationType,
    target_id: edge.targetId,
    curation_status: edge.curationStatus,
    aggregate_confidence: edge.confidence,
    source_count: edge.sourceCount,
    highest_evidence_tier: edge.highestEvidenceTier,
    confidence: edge.confidence,
    evidence_summary: null,
    evidence_tier: edge.highestEvidenceTier,
    provenance_id: edge.provenanceId,
    reviewed_by: null,
    reviewed_at: null,
    created_at: edge.createdAt,
    updated_at: edge.updatedAt,
  }))
}

export function mergeGraphModelWithRelationClaims(
  base: GraphModel,
  claims: ReadonlyArray<RelationClaimResponse>,
): GraphModel {
  if (claims.length === 0) {
    return base
  }

  const nodes = graphNodesToKernelNodes(base.nodes)
  const edges = graphEdgesToKernelEdges(base.edges)
  const nodeIdByTypeAndLabel = new Map<string, string>()

  for (const node of base.nodes) {
    const key = nodeLookupKey(node.entityType, node.label)
    if (!nodeIdByTypeAndLabel.has(key)) {
      nodeIdByTypeAndLabel.set(key, node.id)
    }
  }

  for (const claim of claims) {
    const mappedStatus = CLAIM_STATUS_TO_CURATION_STATUS[claim.claim_status]
    if (mappedStatus === null) {
      continue
    }

    const sourceLabel = claim.source_label?.trim() || claim.source_type
    const targetLabel = claim.target_label?.trim() || claim.target_type
    const sourceType = claim.source_type.trim().toUpperCase()
    const targetType = claim.target_type.trim().toUpperCase()

    const sourceLookupKey = nodeLookupKey(sourceType, sourceLabel)
    const targetLookupKey = nodeLookupKey(targetType, targetLabel)

    let sourceNodeId = nodeIdByTypeAndLabel.get(sourceLookupKey)
    if (!sourceNodeId) {
      sourceNodeId = `claim:${claim.id}:source`
      nodeIdByTypeAndLabel.set(sourceLookupKey, sourceNodeId)
      nodes.push({
        id: sourceNodeId,
        research_space_id: claim.research_space_id,
        entity_type: sourceType,
        display_label: sourceLabel,
        metadata: {},
        created_at: claim.created_at,
        updated_at: claim.updated_at,
      })
    }

    let targetNodeId = nodeIdByTypeAndLabel.get(targetLookupKey)
    if (!targetNodeId) {
      targetNodeId = `claim:${claim.id}:target`
      nodeIdByTypeAndLabel.set(targetLookupKey, targetNodeId)
      nodes.push({
        id: targetNodeId,
        research_space_id: claim.research_space_id,
        entity_type: targetType,
        display_label: targetLabel,
        metadata: {},
        created_at: claim.created_at,
        updated_at: claim.updated_at,
      })
    }

    edges.push({
      id: `claim:${claim.id}`,
      research_space_id: claim.research_space_id,
      source_id: sourceNodeId,
      relation_type: claim.relation_type,
      target_id: targetNodeId,
      curation_status: mappedStatus,
      aggregate_confidence: claim.confidence,
      source_count: 1,
      highest_evidence_tier: null,
      confidence: claim.confidence,
      evidence_summary: claim.validation_reason,
      evidence_tier: null,
      provenance_id: null,
      reviewed_by: claim.triaged_by,
      reviewed_at: claim.triaged_at,
      created_at: claim.created_at,
      updated_at: claim.updated_at,
    })
  }

  return buildGraphModel({ nodes, edges })
}

function mergeNodeMaps(
  left: Record<string, GraphNode>,
  right: Record<string, GraphNode>,
): Record<string, GraphNode> {
  const merged: Record<string, GraphNode> = { ...left }
  for (const node of Object.values(right)) {
    const existing = merged[node.id]
    if (!existing || safeTimestamp(node.updatedAt) > safeTimestamp(existing.updatedAt)) {
      merged[node.id] = node
    }
  }
  return merged
}

function mergeEdgeMaps(
  left: Record<string, GraphEdge>,
  right: Record<string, GraphEdge>,
): Record<string, GraphEdge> {
  const merged: Record<string, GraphEdge> = { ...left }
  for (const edge of Object.values(right)) {
    const existing = merged[edge.id]
    if (!existing || safeTimestamp(edge.updatedAt) > safeTimestamp(existing.updatedAt)) {
      merged[edge.id] = edge
    }
  }
  return merged
}

export function mergeGraphModels(base: GraphModel, incoming: GraphModel): GraphModel {
  const nodes = mergeNodeMaps(base.nodeById, incoming.nodeById)
  const edges = mergeEdgeMaps(base.edgeById, incoming.edgeById)
  return buildGraphModel({
    nodes: graphNodesToKernelNodes(Object.values(nodes)),
    edges: graphEdgesToKernelEdges(Object.values(edges)),
  })
}

export function filterGraphModel(
  model: GraphModel,
  relationTypes: ReadonlySet<string>,
  curationStatuses: ReadonlySet<string>,
): GraphModel {
  const hasRelationTypeFilter = relationTypes.size > 0
  const hasStatusFilter = curationStatuses.size > 0

  const filteredEdges = model.edges.filter((edge) => {
    if (hasRelationTypeFilter && !relationTypes.has(edge.relationType)) {
      return false
    }
    if (hasStatusFilter && !curationStatuses.has(edge.curationStatus)) {
      return false
    }
    return true
  })

  if (filteredEdges.length === 0) {
    return buildGraphModel({
      nodes: graphNodesToKernelNodes(model.nodes),
      edges: [],
    })
  }

  const referencedNodeIds = new Set<string>()
  for (const edge of filteredEdges) {
    referencedNodeIds.add(edge.sourceId)
    referencedNodeIds.add(edge.targetId)
  }

  const filteredNodes = model.nodes.filter((node) => referencedNodeIds.has(node.id))
  return buildGraphModel({
    nodes: graphNodesToKernelNodes(filteredNodes),
    edges: graphEdgesToKernelEdges(filteredEdges),
  })
}

export function pruneGraphModelForRender(
  model: GraphModel,
  maxNodes: number,
  maxEdges: number,
  prioritizedNodeIds: readonly string[] = [],
): GraphPruneResult {
  const preCapNodeCount = model.stats.nodeCount
  const preCapEdgeCount = model.stats.edgeCount
  if (preCapNodeCount <= maxNodes && preCapEdgeCount <= maxEdges) {
    return {
      model,
      preCapNodeCount,
      preCapEdgeCount,
      truncatedNodes: false,
      truncatedEdges: false,
    }
  }

  let prunedEdges = sortEdges(model.edges).slice(0, Math.max(maxEdges, 0))
  const referencedNodeIds = new Set<string>()
  for (const edge of prunedEdges) {
    referencedNodeIds.add(edge.sourceId)
    referencedNodeIds.add(edge.targetId)
  }

  if (prunedEdges.length === 0) {
    const prunedNodes = sortNodes(model.nodes).slice(0, Math.max(maxNodes, 0))
    return {
      model: buildGraphModel({
        nodes: graphNodesToKernelNodes(prunedNodes),
        edges: [],
      }),
      preCapNodeCount,
      preCapEdgeCount,
      truncatedNodes: preCapNodeCount > prunedNodes.length,
      truncatedEdges: preCapEdgeCount > 0,
    }
  }

  let allowedNodeIds = [...referencedNodeIds]
  if (allowedNodeIds.length > maxNodes) {
    const priorityIds: string[] = []
    const seenPriority = new Set<string>()
    for (const prioritizedNodeId of prioritizedNodeIds) {
      if (!referencedNodeIds.has(prioritizedNodeId) || seenPriority.has(prioritizedNodeId)) {
        continue
      }
      seenPriority.add(prioritizedNodeId)
      priorityIds.push(prioritizedNodeId)
    }

    const remainingNodes = sortNodes(
      model.nodes.filter((node) => referencedNodeIds.has(node.id) && !seenPriority.has(node.id)),
    )
    allowedNodeIds = [
      ...priorityIds,
      ...remainingNodes.map((node) => node.id),
    ].slice(0, Math.max(maxNodes, 0))
    const allowedNodeSet = new Set<string>(allowedNodeIds)
    prunedEdges = prunedEdges.filter(
      (edge) => allowedNodeSet.has(edge.sourceId) && allowedNodeSet.has(edge.targetId),
    )
  }

  const allowedNodeSet = new Set<string>(allowedNodeIds)
  const prunedNodes = sortNodes(
    model.nodes.filter((node) => allowedNodeSet.has(node.id)),
  )

  const prunedModel = buildGraphModel({
    nodes: prunedNodes.map((node) => ({
      id: node.id,
      research_space_id: '',
      entity_type: node.entityType,
      display_label: node.label,
      metadata: node.metadata,
      created_at: node.createdAt,
      updated_at: node.updatedAt,
    })),
    edges: prunedEdges.map((edge) => ({
      id: edge.id,
      research_space_id: '',
      source_id: edge.sourceId,
      relation_type: edge.relationType,
      target_id: edge.targetId,
      curation_status: edge.curationStatus,
      aggregate_confidence: edge.confidence,
      source_count: edge.sourceCount,
      highest_evidence_tier: edge.highestEvidenceTier,
      confidence: edge.confidence,
      evidence_summary: null,
      evidence_tier: edge.highestEvidenceTier,
      provenance_id: edge.provenanceId,
      reviewed_by: null,
      reviewed_at: null,
      created_at: edge.createdAt,
      updated_at: edge.updatedAt,
    })),
  })

  return {
    model: prunedModel,
    preCapNodeCount,
    preCapEdgeCount,
    truncatedNodes: preCapNodeCount > prunedModel.stats.nodeCount,
    truncatedEdges: preCapEdgeCount > prunedModel.stats.edgeCount,
  }
}

export function getNeighborhood(model: GraphModel, nodeId: string): GraphNeighborhood {
  const node = model.nodeById[nodeId]
  if (!node) {
    return {
      nodeIds: new Set(),
      edgeIds: new Set(),
    }
  }

  const nodeIds = new Set<string>([node.id])
  const edgeIds = new Set<string>()
  for (const edgeId of model.incidentEdges[node.id] ?? []) {
    const edge = model.edgeById[edgeId]
    if (!edge) {
      continue
    }
    edgeIds.add(edge.id)
    nodeIds.add(edge.sourceId)
    nodeIds.add(edge.targetId)
  }

  return {
    nodeIds,
    edgeIds,
  }
}
