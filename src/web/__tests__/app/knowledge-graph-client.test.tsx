import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import KnowledgeGraphClient from '@/app/(dashboard)/spaces/[spaceId]/knowledge-graph-client'
import { fetchKernelSubgraph, fetchRelationClaims, searchKernelGraph } from '@/lib/api/kernel'
import { useSession } from 'next-auth/react'
import type { GraphSearchResponse, KernelGraphSubgraphResponse } from '@/types/kernel'

jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
}))

const routerReplaceMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
    push: jest.fn(),
    refresh: jest.fn(),
  }),
}))

jest.mock('@/lib/api/kernel', () => ({
  fetchKernelSubgraph: jest.fn(),
  fetchRelationClaims: jest.fn(),
  searchKernelGraph: jest.fn(),
}))

jest.mock('@/components/knowledge-graph/KnowledgeGraphCanvas', () => ({
  __esModule: true,
  default: ({
    graph,
    onNodeClick,
  }: {
    graph: {
      stats: { nodeCount: number; edgeCount: number }
      nodes: { id: string }[]
    }
    onNodeClick: (nodeId: string) => void
  }) => (
    <div data-testid="mock-graph-canvas">
      <div data-testid="mock-graph-node-count">{graph.stats.nodeCount}</div>
      <div data-testid="mock-graph-edge-count">{graph.stats.edgeCount}</div>
      {graph.nodes.map((node) => (
        <button key={node.id} onClick={() => onNodeClick(node.id)} type="button">
          expand-{node.id}
        </button>
      ))}
    </div>
  ),
}))

class ResizeObserverMock {
  public observe(): void {}
  public unobserve(): void {}
  public disconnect(): void {}
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
})

function buildSubgraphResponse(
  overrides: Partial<KernelGraphSubgraphResponse> = {},
): KernelGraphSubgraphResponse {
  return {
    nodes: [
      {
        id: 'n1',
        research_space_id: 'space-1',
        entity_type: 'GENE',
        display_label: 'MED13',
        metadata: {},
        created_at: '2026-02-20T00:00:00Z',
        updated_at: '2026-02-20T00:00:00Z',
      },
      {
        id: 'n2',
        research_space_id: 'space-1',
        entity_type: 'PHENOTYPE',
        display_label: 'Cardiomyopathy',
        metadata: {},
        created_at: '2026-02-21T00:00:00Z',
        updated_at: '2026-02-21T00:00:00Z',
      },
      {
        id: 'n3',
        research_space_id: 'space-1',
        entity_type: 'PHENOTYPE',
        display_label: 'Arrhythmia',
        metadata: {},
        created_at: '2026-02-22T00:00:00Z',
        updated_at: '2026-02-22T00:00:00Z',
      },
    ],
    edges: [
      {
        id: 'e1',
        research_space_id: 'space-1',
        source_id: 'n1',
        relation_type: 'ASSOCIATED_WITH',
        target_id: 'n2',
        aggregate_confidence: 0.91,
        source_count: 2,
        highest_evidence_tier: 'LITERATURE',
        curation_status: 'APPROVED',
        provenance_id: null,
        reviewed_by: null,
        reviewed_at: null,
        created_at: '2026-02-22T00:00:00Z',
        updated_at: '2026-02-22T00:00:00Z',
      },
      {
        id: 'e2',
        research_space_id: 'space-1',
        source_id: 'n1',
        relation_type: 'CO_OCCURS_WITH',
        target_id: 'n3',
        aggregate_confidence: 0.55,
        source_count: 1,
        highest_evidence_tier: 'COMPUTATIONAL',
        curation_status: 'DRAFT',
        provenance_id: null,
        reviewed_by: null,
        reviewed_at: null,
        created_at: '2026-02-21T00:00:00Z',
        updated_at: '2026-02-21T00:00:00Z',
      },
    ],
    meta: {
      mode: 'starter',
      seed_entity_ids: [],
      requested_depth: 2,
      requested_top_k: 25,
      pre_cap_node_count: 3,
      pre_cap_edge_count: 2,
      truncated_nodes: false,
      truncated_edges: false,
    },
    ...overrides,
  }
}

function buildSearchResponse(): GraphSearchResponse {
  return {
    confidence_score: 0.82,
    rationale: 'deterministic',
    evidence: [],
    decision: 'generated',
    research_space_id: 'space-1',
    original_query: 'med13 query',
    interpreted_intent: 'med13',
    query_plan_summary: 'summary',
    total_results: 6,
    results: [
      { entity_id: 'n1', entity_type: 'GENE', display_label: 'MED13', relevance_score: 0.9, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n2', entity_type: 'PHENOTYPE', display_label: 'P1', relevance_score: 0.8, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n3', entity_type: 'PHENOTYPE', display_label: 'P2', relevance_score: 0.7, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n4', entity_type: 'PHENOTYPE', display_label: 'P3', relevance_score: 0.6, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n5', entity_type: 'PHENOTYPE', display_label: 'P4', relevance_score: 0.5, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
      { entity_id: 'n6', entity_type: 'PHENOTYPE', display_label: 'P5', relevance_score: 0.4, matching_observation_ids: [], matching_relation_ids: [], evidence_chain: [], explanation: '', support_summary: '' },
    ],
    executed_path: 'deterministic',
    warnings: [],
    agent_run_id: null,
  }
}

describe('KnowledgeGraphClient', () => {
  const mockUseSession = useSession as jest.MockedFunction<typeof useSession>
  const mockFetchKernelSubgraph = fetchKernelSubgraph as jest.MockedFunction<typeof fetchKernelSubgraph>
  const mockFetchRelationClaims = fetchRelationClaims as jest.MockedFunction<
    typeof fetchRelationClaims
  >
  const mockSearchKernelGraph = searchKernelGraph as jest.MockedFunction<typeof searchKernelGraph>

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetchRelationClaims.mockResolvedValue({
      claims: [],
      total: 0,
      offset: 0,
      limit: 200,
    })
    mockUseSession.mockReturnValue({
      data: {
        expires: new Date(Date.now() + 60_000).toISOString(),
        user: {
          id: 'user-1',
          email: 'user@example.com',
          username: 'user',
          full_name: 'Test User',
          role: 'researcher',
          email_verified: true,
          access_token: 'token-123',
          expires_at: Date.now() + 60_000,
        },
      },
      status: 'authenticated',
      update: jest.fn(),
    })
  })

  it('auto-loads starter subgraph on first render when no query exists', async () => {
    mockFetchKernelSubgraph.mockResolvedValue(buildSubgraphResponse())

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelSubgraph).toHaveBeenCalledWith(
        'space-1',
        expect.objectContaining({
          mode: 'starter',
          seed_entity_ids: [],
        }),
        'token-123',
      )
    })
  })

  it('uses top 5 search results as seeds for seeded subgraph retrieval', async () => {
    mockSearchKernelGraph.mockResolvedValue(buildSearchResponse())
    mockFetchKernelSubgraph.mockResolvedValue(
      buildSubgraphResponse({
        meta: {
          mode: 'seeded',
          seed_entity_ids: ['n1', 'n2', 'n3', 'n4', 'n5'],
          requested_depth: 2,
          requested_top_k: 25,
          pre_cap_node_count: 5,
          pre_cap_edge_count: 4,
          truncated_nodes: false,
          truncated_edges: false,
        },
      }),
    )

    render(
      <KnowledgeGraphClient
        spaceId="space-1"
        initialQuestion="med13 query"
        initialTopK={25}
        initialMaxDepth={2}
      />,
    )

    await waitFor(() => {
      expect(mockSearchKernelGraph).toHaveBeenCalled()
      expect(mockFetchKernelSubgraph).toHaveBeenCalled()
    })

    const payload = mockFetchKernelSubgraph.mock.calls[0]?.[1]
    expect(payload).toEqual(
      expect.objectContaining({
        mode: 'seeded',
        seed_entity_ids: ['n1', 'n2', 'n3', 'n4', 'n5'],
      }),
    )
  })

  it('expands from node click and merges without duplicating edges', async () => {
    mockFetchKernelSubgraph
      .mockResolvedValueOnce(
        buildSubgraphResponse({
          nodes: buildSubgraphResponse().nodes.slice(0, 2),
          edges: buildSubgraphResponse().edges.slice(0, 1),
        }),
      )
      .mockResolvedValueOnce(
        buildSubgraphResponse({
          nodes: buildSubgraphResponse().nodes,
          edges: [
            buildSubgraphResponse().edges[0],
            {
              ...buildSubgraphResponse().edges[0],
              id: 'e3',
              target_id: 'n3',
              relation_type: 'ASSOCIATED_WITH',
            },
          ],
        }),
      )

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelSubgraph).toHaveBeenCalledTimes(1)
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('1')
    })

    fireEvent.click(screen.getByRole('button', { name: 'expand-n1' }))

    await waitFor(() => {
      expect(mockFetchKernelSubgraph).toHaveBeenCalledTimes(2)
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('2')
    })
  })

  it('applies relation filter and updates visible graph edges', async () => {
    mockFetchKernelSubgraph.mockResolvedValue(buildSubgraphResponse())

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelSubgraph).toHaveBeenCalledTimes(1)
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('2')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByLabelText('ASSOCIATED_WITH'))

    await waitFor(() => {
      expect(screen.getByTestId('mock-graph-edge-count')).toHaveTextContent('1')
    })
  })

  it('uses trust preset as backend curation_statuses filter', async () => {
    mockFetchKernelSubgraph
      .mockResolvedValueOnce(buildSubgraphResponse())
      .mockResolvedValueOnce(buildSubgraphResponse())

    render(<KnowledgeGraphClient spaceId="space-1" />)

    await waitFor(() => {
      expect(mockFetchKernelSubgraph).toHaveBeenCalledTimes(1)
      expect(mockFetchKernelSubgraph.mock.calls[0]?.[1]).toEqual(
        expect.objectContaining({
          curation_statuses: null,
        }),
      )
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByRole('button', { name: 'Approved only' }))

    await waitFor(() => {
      expect(mockFetchKernelSubgraph).toHaveBeenCalledTimes(2)
      expect(mockFetchKernelSubgraph.mock.calls[1]?.[1]).toEqual(
        expect.objectContaining({
          curation_statuses: ['APPROVED'],
        }),
      )
    })
  })
})
