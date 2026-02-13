import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataSourcesList } from '@/components/data-sources/DataSourcesList'
import { DiscoverSourcesDialog } from '@/components/data-sources/DiscoverSourcesDialog'
import type { DataSource } from '@/types/data-source'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { OrchestratedSessionState } from '@/types/generated'

const mockRefresh = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: mockRefresh,
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
  }),
}))

jest.mock('@/app/actions/data-sources', () => ({
  configureDataSourceScheduleAction: jest.fn(),
  createDataSourceInSpaceAction: jest.fn(),
  deleteDataSourceAction: jest.fn(),
  fetchIngestionJobHistoryAction: jest.fn(),
  testDataSourceAiConfigurationAction: jest.fn(),
  updateDataSourceAction: jest.fn(),
}))

jest.mock('@/components/data-discovery/DataDiscoveryContent', () => ({
  DataDiscoveryContent: ({ onComplete }: { onComplete?: () => void }) => (
    <div>
      <button
        onClick={() => onComplete?.()}
        data-testid="mock-add-source"
      >
        Mock Add Source
      </button>
    </div>
  ),
}))

const mockDataSources: DataSource[] = [
  {
    id: 'source-1',
    name: 'Test Source 1',
    description: 'Test description',
    source_type: 'api',
    status: 'active',
    owner_id: 'user-123',
    research_space_id: 'space-123',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
]

const discoveryState: OrchestratedSessionState | null = null
const dataSourcesResponse: DataSourceListResponse = {
  items: mockDataSources,
  total: 1,
  page: 1,
  limit: 20,
  has_next: false,
  has_prev: false,
}

describe('DataSourcesList - Auto-refresh on Source Addition', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('refreshes the router when onSourceAdded callback is triggered', async () => {
    const user = userEvent.setup()

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    // Open the discover dialog
    const addButton = screen.getByRole('button', { name: /add from library/i })
    await user.click(addButton)

    // Wait for dialog to open
    await waitFor(() => {
      expect(screen.getByText(/discover data sources/i)).toBeInTheDocument()
    })

    // Simulate adding a source (this would normally happen in DataDiscoveryContent)
    const mockAddButton = screen.getByTestId('mock-add-source')
    await user.click(mockAddButton)

    expect(mockRefresh).toHaveBeenCalled()
  })

  it('displays updated data sources after rerender', async () => {
    const updatedDataSources = [
      ...mockDataSources,
      {
        id: 'source-2',
        name: 'New Source',
        description: 'Newly added source',
        source_type: 'pubmed',
        status: 'draft',
        owner_id: 'user-123',
        research_space_id: 'space-123',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]

    // Initial render with 1 source
    const { rerender } = render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    expect(screen.getByText('Test Source 1')).toBeInTheDocument()

    rerender(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: updatedDataSources,
          total: 2,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    // Verify new source appears
    await waitFor(() => {
      expect(screen.getByText('New Source')).toBeInTheDocument()
    })
  })
})

describe('DiscoverSourcesDialog - onSourceAdded prop', () => {
  it('calls onSourceAdded callback when source is added', async () => {
    const user = userEvent.setup()
    const onSourceAdded = jest.fn()

    render(
      <DiscoverSourcesDialog
        spaceId="space-123"
        open={true}
        onOpenChange={jest.fn()}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        onSourceAdded={onSourceAdded}
      />,
    )

    // Simulate adding a source
    const mockAddButton = screen.getByTestId('mock-add-source')
    await user.click(mockAddButton)

    await waitFor(() => {
      expect(onSourceAdded).toHaveBeenCalled()
    })
  })
})

describe('DataSourcesList - AI Controls', () => {
  it('shows schedule and AI buttons for ClinVar AI-managed sources', () => {
    const clinvarSource: DataSource = {
      id: 'source-clinvar',
      name: 'ClinVar Pathogenicity Benchmark',
      description: 'Curated benchmark set for pathogenicity tasks',
      source_type: 'api',
      status: 'active',
      owner_id: 'user-123',
      research_space_id: 'space-123',
      config: {
        metadata: {
          agent_config: {
            is_ai_managed: true,
            query_agent_source_type: 'clinvar',
            agent_prompt: 'Use ClinVar terminology for variant queries.',
          },
        },
      },
      ingestion_schedule: {
        enabled: true,
        frequency: 'daily',
        timezone: 'UTC',
        start_time: null,
        cron_expression: null,
        backend_job_id: null,
        next_run_at: null,
        last_run_at: null,
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: [clinvarSource],
          total: 1,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    expect(screen.getByRole('button', { name: /configure schedule/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /configure ai/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /test ai/i })).toBeInTheDocument()
  })

  it('keeps AI buttons hidden for plain API sources without agent metadata', () => {
    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
      />,
    )

    expect(screen.queryByRole('button', { name: /configure schedule/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /configure ai/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /test ai/i })).not.toBeInTheDocument()
  })
})
