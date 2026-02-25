import { apiPost } from '@/lib/api/client'
import { fetchKernelSubgraph } from '@/lib/api/kernel'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPut: jest.fn(),
  apiDelete: jest.fn(),
}))

describe('kernel api', () => {
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>
  const token = 'space-token'

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('calls bounded subgraph endpoint with auth token', async () => {
    const mockResponse = {
      nodes: [],
      edges: [],
      meta: {
        mode: 'starter',
        seed_entity_ids: [],
        requested_depth: 2,
        requested_top_k: 25,
        pre_cap_node_count: 0,
        pre_cap_edge_count: 0,
        truncated_nodes: false,
        truncated_edges: false,
      },
    }
    mockApiPost.mockResolvedValue(mockResponse)

    const payload = {
      mode: 'starter' as const,
      seed_entity_ids: [],
      max_nodes: 180,
      max_edges: 260,
    }
    const result = await fetchKernelSubgraph('space-1', payload, token)

    expect(mockApiPost).toHaveBeenCalledWith(
      '/research-spaces/space-1/graph/subgraph',
      payload,
      { token },
    )
    expect(result).toEqual(mockResponse)
  })

  it('throws when token is not provided', async () => {
    await expect(
      fetchKernelSubgraph(
        'space-1',
        {
          mode: 'starter',
          seed_entity_ids: [],
        },
        undefined,
      ),
    ).rejects.toThrow('Authentication token is required for fetchKernelSubgraph')
  })
})
