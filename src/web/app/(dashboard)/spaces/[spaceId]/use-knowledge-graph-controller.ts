'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchKernelGraphExport,
  fetchKernelNeighborhood,
  fetchKernelSubgraph,
  searchKernelGraph,
} from '@/lib/api/kernel'
import {
  buildGraphModel,
  emptyGraphModel,
  filterGraphModel,
  getNeighborhood,
  mergeGraphModels,
  pruneGraphModelForRender,
  type GraphModel,
} from '@/lib/graph/model'
import type {
  GraphSearchResponse,
  KernelGraphSubgraphMeta,
  KernelGraphSubgraphRequest,
} from '@/types/kernel'

const DEFAULT_STARTER_TOP_K = 25
const DEFAULT_STARTER_DEPTH = 2
const MAX_DEPTH = 4
const MAX_TOP_K = 100
const MIN_DEPTH = 1
const MIN_TOP_K = 1
const MAX_RENDER_NODES = 180
const MAX_RENDER_EDGES = 260
const DEFAULT_VISIBLE_CURATION_STATUSES = ['APPROVED', 'UNDER_REVIEW', 'DRAFT']
const MAX_SEEDED_SEARCH_RESULTS = 5
const DEFAULT_EXPAND_TOP_K = 25

interface QueryRouter {
  replace: (href: string) => void
}

interface UseKnowledgeGraphControllerArgs {
  spaceId: string
  token?: string
  router: QueryRouter
  initialQuestion: string
  initialTopK: number
  initialMaxDepth: number
  initialForceAgent: boolean
}

function parseBoundedInt(
  value: string,
  fallback: number,
  minValue: number,
  maxValue: number,
): number {
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed)) {
    return fallback
  }
  return Math.min(maxValue, Math.max(minValue, parsed))
}

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message
  }
  return fallback
}

function errorStatusCode(error: unknown): number | null {
  if (typeof error !== 'object' || error === null) {
    return null
  }
  if (!('response' in error)) {
    return null
  }
  const response = (error as { response?: { status?: unknown } }).response
  if (!response || typeof response.status !== 'number') {
    return null
  }
  return response.status
}

function updateQueryParams(
  router: QueryRouter,
  spaceId: string,
  question: string,
  topK: number,
  maxDepth: number,
  forceAgent: boolean,
): void {
  const params = new URLSearchParams()
  const trimmedQuestion = question.trim()
  if (trimmedQuestion.length > 0) {
    params.set('q', trimmedQuestion)
    params.set('top_k', String(topK))
    params.set('max_depth', String(maxDepth))
    if (forceAgent) {
      params.set('force_agent', '1')
    }
  }
  const suffix = params.toString()
  router.replace(
    suffix.length > 0
      ? `/spaces/${spaceId}/knowledge-graph?${suffix}`
      : `/spaces/${spaceId}/knowledge-graph`,
  )
}

export interface KnowledgeGraphController {
  questionInput: string
  topKInput: string
  maxDepthInput: string
  forceAgent: boolean
  setQuestionInput: (value: string) => void
  setTopKInput: (value: string) => void
  setMaxDepthInput: (value: string) => void
  setForceAgent: (value: boolean) => void
  topK: number
  maxDepth: number
  minDepth: number
  maxDepthLimit: number
  minTopK: number
  maxTopKLimit: number
  graphSearch: GraphSearchResponse | null
  graphSearchResults: GraphSearchResponse['results']
  graphSearchError: string | null
  graphError: string | null
  graphNotice: string | null
  isLoading: boolean
  isExpandingNodeId: string | null
  filteredGraph: GraphModel
  renderGraph: GraphModel
  neighborhood: {
    nodeIds: Set<string>
    edgeIds: Set<string>
  }
  selectedNodeId: string | null
  subgraphMeta: KernelGraphSubgraphMeta | null
  truncationNotice: boolean | undefined
  preCapNodeCount: number
  preCapEdgeCount: number
  availableRelationTypes: string[]
  availableCurationStatuses: string[]
  relationTypeFilter: Set<string>
  curationStatusFilter: Set<string>
  showRelationTable: boolean
  showEntityTable: boolean
  setShowRelationTable: (open: boolean) => void
  setShowEntityTable: (open: boolean) => void
  onNodeClick: (nodeId: string) => void
  onHoverNodeChange: (nodeId: string | null) => void
  clearSelection: () => void
  runSearch: (syncUrl?: boolean) => Promise<void>
  resetToStarter: () => void
  resetFilters: () => void
  toggleRelationType: (relationType: string, checked: boolean) => void
  toggleCurationStatus: (status: string, checked: boolean) => void
}

export function useKnowledgeGraphController({
  spaceId,
  token,
  router,
  initialQuestion,
  initialTopK,
  initialMaxDepth,
  initialForceAgent,
}: UseKnowledgeGraphControllerArgs): KnowledgeGraphController {
  const bootstrapRef = useRef(false)

  const [questionInput, setQuestionInput] = useState(initialQuestion)
  const [topKInput, setTopKInput] = useState(String(initialTopK))
  const [maxDepthInput, setMaxDepthInput] = useState(String(initialMaxDepth))
  const [forceAgent, setForceAgent] = useState(initialForceAgent)

  const [rawGraph, setRawGraph] = useState<GraphModel>(emptyGraphModel())
  const [subgraphMeta, setSubgraphMeta] = useState<KernelGraphSubgraphMeta | null>(null)
  const [graphSearch, setGraphSearch] = useState<GraphSearchResponse | null>(null)

  const [graphError, setGraphError] = useState<string | null>(null)
  const [graphNotice, setGraphNotice] = useState<string | null>(null)
  const [graphSearchError, setGraphSearchError] = useState<string | null>(null)
  const [isLoadingGraph, setIsLoadingGraph] = useState(false)
  const [isSearching, setIsSearching] = useState(false)
  const [isExpandingNodeId, setIsExpandingNodeId] = useState<string | null>(null)

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const [relationTypeFilter, setRelationTypeFilter] = useState<Set<string>>(new Set())
  const [curationStatusFilter, setCurationStatusFilter] = useState<Set<string>>(
    new Set(DEFAULT_VISIBLE_CURATION_STATUSES),
  )

  const [showRelationTable, setShowRelationTable] = useState(false)
  const [showEntityTable, setShowEntityTable] = useState(false)

  const topK = useMemo(
    () => parseBoundedInt(topKInput, initialTopK, MIN_TOP_K, MAX_TOP_K),
    [initialTopK, topKInput],
  )
  const maxDepth = useMemo(
    () => parseBoundedInt(maxDepthInput, initialMaxDepth, MIN_DEPTH, MAX_DEPTH),
    [initialMaxDepth, maxDepthInput],
  )

  const fetchSubgraph = useCallback(
    async (payload: KernelGraphSubgraphRequest): Promise<void> => {
      if (!token) {
        setGraphError('Authentication token is unavailable.')
        return
      }

      setIsLoadingGraph(true)
      setGraphError(null)
      setGraphNotice(null)

      try {
        const response = await fetchKernelSubgraph(spaceId, payload, token)
        setRawGraph(buildGraphModel(response))
        setSubgraphMeta(response.meta)
      } catch (error) {
        if (errorStatusCode(error) === 404) {
          try {
            const legacyGraph = await fetchKernelGraphExport(spaceId, token)
            setRawGraph(buildGraphModel(legacyGraph))
            setSubgraphMeta(null)
            setGraphNotice(
              'Subgraph endpoint is unavailable on this backend instance. Showing legacy graph export.',
            )
            return
          } catch (legacyError) {
            setGraphError(
              toErrorMessage(
                legacyError,
                'Unable to load legacy knowledge graph export for this research space.',
              ),
            )
            return
          }
        }
        setGraphError(
          toErrorMessage(
            error,
            'Unable to load bounded subgraph for this research space.',
          ),
        )
      } finally {
        setIsLoadingGraph(false)
      }
    },
    [spaceId, token],
  )

  const loadStarterSubgraph = useCallback(async (): Promise<void> => {
    setSelectedNodeId(null)
    setHoveredNodeId(null)
    await fetchSubgraph({
      mode: 'starter',
      seed_entity_ids: [],
      depth: DEFAULT_STARTER_DEPTH,
      top_k: DEFAULT_STARTER_TOP_K,
      max_nodes: MAX_RENDER_NODES,
      max_edges: MAX_RENDER_EDGES,
    })
  }, [fetchSubgraph])

  const runQuery = useCallback(
    async ({
      question,
      topK,
      maxDepth,
      forceAgent,
      syncUrl,
    }: {
      question: string
      topK: number
      maxDepth: number
      forceAgent: boolean
      syncUrl: boolean
    }): Promise<void> => {
      const normalizedQuestion = question.trim()
      if (!token) {
        setGraphSearchError('Authentication token is unavailable.')
        return
      }

      if (normalizedQuestion.length === 0) {
        setGraphSearch(null)
        setGraphSearchError(null)
        if (syncUrl) {
          updateQueryParams(
            router,
            spaceId,
            '',
            topK,
            maxDepth,
            forceAgent,
          )
        }
        await loadStarterSubgraph()
        return
      }

      setIsSearching(true)
      setGraphSearchError(null)
      setGraphError(null)
      setGraphNotice(null)
      setSelectedNodeId(null)
      setHoveredNodeId(null)

      try {
        const searchResponse = await searchKernelGraph(
          spaceId,
          {
            question: normalizedQuestion,
            top_k: topK,
            max_depth: maxDepth,
            include_evidence_chains: true,
            force_agent: forceAgent,
          },
          token,
        )
        setGraphSearch(searchResponse)

        const seedEntityIds = searchResponse.results
          .slice(0, MAX_SEEDED_SEARCH_RESULTS)
          .map((result) => result.entity_id)

        if (seedEntityIds.length === 0) {
          setRawGraph(emptyGraphModel())
          setSubgraphMeta(null)
        } else {
          await fetchSubgraph({
            mode: 'seeded',
            seed_entity_ids: seedEntityIds,
            depth: maxDepth,
            top_k: topK,
            max_nodes: MAX_RENDER_NODES,
            max_edges: MAX_RENDER_EDGES,
          })
        }

        if (syncUrl) {
          updateQueryParams(
            router,
            spaceId,
            normalizedQuestion,
            topK,
            maxDepth,
            forceAgent,
          )
        }
      } catch (error) {
        setGraphSearchError(
          toErrorMessage(error, 'Unable to execute graph search for this space.'),
        )
      } finally {
        setIsSearching(false)
      }
    },
    [fetchSubgraph, loadStarterSubgraph, router, spaceId, token],
  )

  useEffect(() => {
    if (bootstrapRef.current || !token) {
      return
    }
    bootstrapRef.current = true

    if (initialQuestion.trim().length > 0) {
      void runQuery({
        question: initialQuestion,
        topK: initialTopK,
        maxDepth: initialMaxDepth,
        forceAgent: initialForceAgent,
        syncUrl: false,
      })
      return
    }

    void loadStarterSubgraph()
  }, [
    initialForceAgent,
    initialMaxDepth,
    initialQuestion,
    initialTopK,
    loadStarterSubgraph,
    runQuery,
    token,
  ])

  const expandFromNode = useCallback(
    async (nodeId: string): Promise<void> => {
      if (!token) {
        setGraphError('Authentication token is unavailable.')
        return
      }

      setIsExpandingNodeId(nodeId)
      setGraphError(null)
      setGraphNotice(null)
      try {
        const expansionResponse = await fetchKernelSubgraph(
          spaceId,
          {
            mode: 'seeded',
            seed_entity_ids: [nodeId],
            depth: 1,
            top_k: Math.min(topK, DEFAULT_EXPAND_TOP_K),
            max_nodes: MAX_RENDER_NODES,
            max_edges: MAX_RENDER_EDGES,
          },
          token,
        )
        const incoming = buildGraphModel(expansionResponse)
        setRawGraph((current) => mergeGraphModels(current, incoming))
      } catch (error) {
        if (errorStatusCode(error) === 404) {
          try {
            const legacyNeighborhood = await fetchKernelNeighborhood(
              spaceId,
              nodeId,
              1,
              token,
            )
            const incoming = buildGraphModel(legacyNeighborhood)
            setRawGraph((current) => mergeGraphModels(current, incoming))
            setGraphNotice(
              'Subgraph endpoint unavailable. Expansion is using legacy neighborhood API.',
            )
            return
          } catch (legacyError) {
            setGraphError(
              toErrorMessage(
                legacyError,
                'Unable to expand neighborhood from legacy API.',
              ),
            )
            return
          }
        }
        setGraphError(
          toErrorMessage(
            error,
            'Unable to expand neighborhood for selected node.',
          ),
        )
      } finally {
        setIsExpandingNodeId(null)
      }
    },
    [spaceId, token, topK],
  )

  const onNodeClick = useCallback(
    (nodeId: string): void => {
      setSelectedNodeId(nodeId)
      void expandFromNode(nodeId)
    },
    [expandFromNode],
  )

  const availableRelationTypes = rawGraph.relationTypes
  const availableCurationStatuses = useMemo(() => {
    const merged = new Set<string>(DEFAULT_VISIBLE_CURATION_STATUSES)
    for (const status of rawGraph.curationStatuses) {
      merged.add(status)
    }
    return [...merged]
  }, [rawGraph.curationStatuses])

  const filteredGraph = useMemo(
    () => filterGraphModel(rawGraph, relationTypeFilter, curationStatusFilter),
    [curationStatusFilter, rawGraph, relationTypeFilter],
  )

  const prunedGraph = useMemo(
    () =>
      pruneGraphModelForRender(
        filteredGraph,
        MAX_RENDER_NODES,
        MAX_RENDER_EDGES,
        selectedNodeId ? [selectedNodeId] : [],
      ),
    [filteredGraph, selectedNodeId],
  )

  const renderGraph = prunedGraph.model
  const activeNeighborhoodNode = selectedNodeId ?? hoveredNodeId
  const neighborhood = useMemo(() => {
    if (!activeNeighborhoodNode) {
      return {
        nodeIds: new Set<string>(),
        edgeIds: new Set<string>(),
      }
    }
    return getNeighborhood(renderGraph, activeNeighborhoodNode)
  }, [activeNeighborhoodNode, renderGraph])

  const runSearch = useCallback(
    async (syncUrl = true): Promise<void> => {
      await runQuery({
        question: questionInput,
        topK,
        maxDepth,
        forceAgent,
        syncUrl,
      })
    },
    [forceAgent, maxDepth, questionInput, runQuery, topK],
  )

  const resetToStarter = useCallback((): void => {
    setQuestionInput('')
    setTopKInput(String(initialTopK))
    setMaxDepthInput(String(initialMaxDepth))
    setForceAgent(false)
    setGraphSearch(null)
    setGraphSearchError(null)
    updateQueryParams(
      router,
      spaceId,
      '',
      topK,
      maxDepth,
      false,
    )
    void loadStarterSubgraph()
  }, [initialMaxDepth, initialTopK, loadStarterSubgraph, maxDepth, router, spaceId, topK])

  const clearSelection = useCallback((): void => {
    setSelectedNodeId(null)
    setHoveredNodeId(null)
  }, [])

  const resetFilters = useCallback((): void => {
    setRelationTypeFilter(new Set())
    setCurationStatusFilter(new Set(DEFAULT_VISIBLE_CURATION_STATUSES))
  }, [])

  const toggleRelationType = useCallback((relationType: string, checked: boolean): void => {
    setRelationTypeFilter((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(relationType)
      } else {
        next.delete(relationType)
      }
      return next
    })
  }, [])

  const toggleCurationStatus = useCallback((status: string, checked: boolean): void => {
    setCurationStatusFilter((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(status)
      } else {
        next.delete(status)
      }
      return next
    })
  }, [])

  const graphSearchResults = graphSearch?.results ?? []
  const isLoading = isLoadingGraph || isSearching
  const truncationNotice =
    prunedGraph.truncatedEdges ||
    prunedGraph.truncatedNodes ||
    subgraphMeta?.truncated_edges ||
    subgraphMeta?.truncated_nodes

  return {
    questionInput,
    topKInput,
    maxDepthInput,
    forceAgent,
    setQuestionInput,
    setTopKInput,
    setMaxDepthInput,
    setForceAgent,
    topK,
    maxDepth,
    minDepth: MIN_DEPTH,
    maxDepthLimit: MAX_DEPTH,
    minTopK: MIN_TOP_K,
    maxTopKLimit: MAX_TOP_K,
    graphSearch,
    graphSearchResults,
    graphSearchError,
    graphError,
    graphNotice,
    isLoading,
    isExpandingNodeId,
    filteredGraph,
    renderGraph,
    neighborhood,
    selectedNodeId,
    subgraphMeta,
    truncationNotice,
    preCapNodeCount: prunedGraph.preCapNodeCount,
    preCapEdgeCount: prunedGraph.preCapEdgeCount,
    availableRelationTypes,
    availableCurationStatuses,
    relationTypeFilter,
    curationStatusFilter,
    showRelationTable,
    showEntityTable,
    setShowRelationTable,
    setShowEntityTable,
    onNodeClick,
    onHoverNodeChange: setHoveredNodeId,
    clearSelection,
    runSearch,
    resetToStarter,
    resetFilters,
    toggleRelationType,
    toggleCurationStatus,
  }
}
