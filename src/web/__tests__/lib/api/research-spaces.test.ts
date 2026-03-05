import type { AxiosError } from 'axios'
import { apiClient, authHeaders } from '@/lib/api/client'
import { fetchResearchSpace } from '@/lib/api/research-spaces'
import { SpaceStatus, type ResearchSpace } from '@/types/research-space'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
  authHeaders: jest.fn(),
}))

const mockApiClientGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>
const mockAuthHeaders = authHeaders as jest.MockedFunction<typeof authHeaders>

function httpError(status: number): AxiosError {
  return { response: { status } } as AxiosError
}

function buildSpace(overrides?: Partial<ResearchSpace>): ResearchSpace {
  return {
    id: '1f84fede-e7eb-4e0c-b25e-72df5dd97d73',
    slug: 'team-alpha',
    name: 'Team Alpha',
    description: 'Test space',
    owner_id: 'f2158ff8-b679-448a-8853-f7f13f7d5c3d',
    status: SpaceStatus.ACTIVE,
    settings: {},
    tags: [],
    created_at: '2026-03-03T00:00:00Z',
    updated_at: '2026-03-03T00:00:00Z',
    ...overrides,
  }
}

describe('research spaces api', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockAuthHeaders.mockImplementation((token?: string) => ({
      headers: { Authorization: `Bearer ${token ?? ''}` },
    }))
  })

  it('falls back to slug endpoint when id lookup returns 404', async () => {
    const expected = buildSpace()
    mockApiClientGet
      .mockRejectedValueOnce(httpError(404))
      .mockResolvedValueOnce({ data: expected } as never)

    const result = await fetchResearchSpace('team-alpha', 'test-token')

    expect(result).toEqual(expected)
    expect(mockApiClientGet).toHaveBeenNthCalledWith(
      1,
      '/research-spaces/team-alpha',
      { headers: { Authorization: 'Bearer test-token' } },
    )
    expect(mockApiClientGet).toHaveBeenNthCalledWith(
      2,
      '/research-spaces/slug/team-alpha',
      { headers: { Authorization: 'Bearer test-token' } },
    )
  })

  it('falls back to list lookup when slug endpoint is unavailable', async () => {
    const expected = buildSpace()
    mockApiClientGet
      .mockRejectedValueOnce(httpError(404))
      .mockRejectedValueOnce(httpError(404))
      .mockResolvedValueOnce({
        data: {
          spaces: [expected],
          total: 1,
          skip: 0,
          limit: 200,
        },
      } as never)

    const result = await fetchResearchSpace('team-alpha', 'test-token')

    expect(result).toEqual(expected)
    expect(mockApiClientGet).toHaveBeenNthCalledWith(
      3,
      '/research-spaces',
      {
        params: { limit: 200 },
        headers: { Authorization: 'Bearer test-token' },
      },
    )
  })

  it('does not attempt slug fallback for UUID identifiers', async () => {
    const uuid = '1f84fede-e7eb-4e0c-b25e-72df5dd97d73'
    const expectedError = httpError(404)
    mockApiClientGet.mockRejectedValueOnce(expectedError)

    await expect(fetchResearchSpace(uuid, 'test-token')).rejects.toBe(expectedError)
    expect(mockApiClientGet).toHaveBeenCalledTimes(1)
  })
})
