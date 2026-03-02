import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataSourcesList } from '@/components/data-sources/DataSourcesList'
import { DiscoverSourcesDialog } from '@/components/data-sources/DiscoverSourcesDialog'
import {
  fetchSourceWorkflowCardStatusAction,
  fetchSourceWorkflowEventsAction,
} from '@/app/actions/kernel-ingest'
import type { DataSource } from '@/types/data-source'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { OrchestratedSessionState } from '@/types/generated'
import type {
  SpaceWorkflowBootstrapPayload,
  SpaceWorkflowSourceCardPayload,
} from '@/types/kernel'

const mockRefresh = jest.fn()
const mockStreamBootstrapPayloadState: {
  current: SpaceWorkflowBootstrapPayload | null
} = { current: null }
const mockStreamCardPayloadsState: {
  current: SpaceWorkflowSourceCardPayload[]
} = { current: [] }
const mockStreamFallbackState: { current: boolean } = { current: false }

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

jest.mock('@/app/actions/kernel-ingest', () => ({
  cancelSpaceSourcePipelineRunAction: jest.fn(),
  fetchSourceWorkflowEventsAction: jest.fn(),
  fetchSourceWorkflowCardStatusAction: jest.fn(),
  runSpaceSourcePipelineAction: jest.fn(),
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

jest.mock('@/hooks/use-space-workflow-stream', () => {
  const React = require('react')
  return {
    useSpaceWorkflowStream: jest.fn((options) => {
      React.useEffect(() => {
        if (mockStreamBootstrapPayloadState.current !== null) {
          options.onBootstrap?.(mockStreamBootstrapPayloadState.current)
        }
        for (const payload of mockStreamCardPayloadsState.current) {
          options.onSourceCardStatus?.(payload)
        }
      }, [options.onBootstrap, options.onSourceCardStatus])
      return {
        isConnected: true,
        isFallbackActive: mockStreamFallbackState.current,
        lastError: null,
      }
    }),
  }
})

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

beforeEach(() => {
  mockStreamBootstrapPayloadState.current = null
  mockStreamCardPayloadsState.current = []
  mockStreamFallbackState.current = false
  ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockResolvedValue({
    success: true,
    data: {
      last_pipeline_status: 'completed',
      pending_paper_count: 0,
      pending_relation_review_count: 0,
      graph_edges_delta_last_run: 0,
      graph_edges_total: 0,
      last_failed_stage: null,
    },
  })
  ;(fetchSourceWorkflowEventsAction as jest.Mock).mockResolvedValue({
    success: true,
    data: { events: [] },
  })
})

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
  it('shows a consolidated Configure menu for any connector with query_agent_source_type', async () => {
    const user = userEvent.setup()
    const connectorSource: DataSource = {
      id: 'source-future-connector',
      name: 'Future Connector Source',
      description: 'Generic connector source',
      source_type: 'api',
      status: 'active',
      owner_id: 'user-123',
      research_space_id: 'space-123',
      config: {
        metadata: {
          agent_config: {
            is_ai_managed: true,
            query_agent_source_type: 'future_connector',
            agent_prompt: 'Use connector-specific terminology.',
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
          items: [connectorSource],
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

    const configureButton = screen.getByRole('button', {
      name: /configure future connector source/i,
    })
    expect(configureButton).toBeInTheDocument()

    await user.click(configureButton)

    expect(screen.getByRole('dialog', { name: /configure source/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^schedule$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ai config/i })).toBeInTheDocument()
  })

  it('shows a consolidated Configure menu for ClinVar AI-managed sources', async () => {
    const user = userEvent.setup()
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

    const configureButton = screen.getByRole('button', {
      name: /configure clinvar pathogenicity benchmark/i,
    })
    expect(configureButton).toBeInTheDocument()

    await user.click(configureButton)

    expect(screen.getByRole('dialog', { name: /configure source/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^schedule$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ai config/i })).toBeInTheDocument()
  })

  it('shows a consolidated Configure menu for ClinVar discovery sources without agent config', async () => {
    const user = userEvent.setup()
    const clinvarSource: DataSource = {
      id: 'source-clinvar-discovery',
      name: 'ClinVar (from Data Discovery)',
      description: 'Public archive connecting human genetic variants to phenotypes.',
      source_type: 'api',
      status: 'draft',
      owner_id: 'user-123',
      research_space_id: 'space-123',
      config: {
        metadata: {
          catalog_entry_id: 'clinvar',
          query: 'MED13 pathogenic variant',
        },
      },
      ingestion_schedule: {
        enabled: false,
        frequency: 'manual',
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

    const configureButton = screen.getByRole('button', {
      name: /configure clinvar \(from data discovery\)/i,
    })
    expect(configureButton).toBeInTheDocument()

    await user.click(configureButton)

    expect(screen.getByRole('dialog', { name: /configure source/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^schedule$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ai config/i })).toBeInTheDocument()
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

    expect(screen.queryByRole('button', { name: /^configure$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /configure schedule/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /configure ai/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /test ai/i })).not.toBeInTheDocument()
  })
})

describe('DataSourcesList - Artana progress display', () => {
  it('renders optional Artana stage progress badge when provided', () => {
    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'completed',
            pending_paper_count: 0,
            pending_relation_review_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 10,
            artana_progress: {
              extraction: {
                run_id: 'extract:run:1',
                status: 'running',
                percent: 45,
                current_stage: 'extract',
              },
            },
          },
        }}
      />,
    )

    expect(screen.getByText(/Artana extraction 45%/i)).toBeInTheDocument()
  })
})

describe('DataSourcesList - Workflow streaming and fallback', () => {
  it('applies stream bootstrap updates to live workflow UI', async () => {
    mockStreamBootstrapPayloadState.current = {
      generated_at: '2026-03-02T20:00:00+00:00',
      sources: [
        {
          source_id: 'source-1',
          generated_at: '2026-03-02T20:00:00+00:00',
          workflow_status: {
            last_pipeline_status: 'running',
            last_failed_stage: null,
            pending_paper_count: 2,
            pending_relation_review_count: 1,
            graph_edges_delta_last_run: 3,
            graph_edges_total: 10,
          },
          events: [
            {
              event_id: 'stream-event-1',
              occurred_at: '2026-03-02T20:00:00+00:00',
              category: 'run',
              stage: 'ingestion',
              status: 'running',
              message: 'Pipeline running from stream',
            },
          ],
        },
      ],
    }
    const draftDataSource: DataSource = {
      ...mockDataSources[0],
      status: 'draft',
    }

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={{
          items: [draftDataSource],
          total: 1,
          page: 1,
          limit: 20,
          has_next: false,
          has_prev: false,
        }}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'running',
            pending_paper_count: 0,
            pending_relation_review_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 0,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(/Live run in progress/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/Pipeline running from stream/i)).toBeInTheDocument()
  })

  it('keeps polling updates working when stream fallback is active', async () => {
    mockStreamFallbackState.current = true
    ;(fetchSourceWorkflowCardStatusAction as jest.Mock).mockResolvedValue({
      success: true,
      data: {
        last_pipeline_status: 'running',
        pending_paper_count: 1,
        pending_relation_review_count: 0,
        graph_edges_delta_last_run: 0,
        graph_edges_total: 4,
        last_failed_stage: null,
      },
    })
    ;(fetchSourceWorkflowEventsAction as jest.Mock).mockResolvedValue({
      success: true,
      data: {
        events: [
          {
            event_id: 'poll-event-1',
            occurred_at: '2026-03-02T20:00:04+00:00',
            category: 'run',
            stage: 'ingestion',
            status: 'running',
            message: 'Poll backend event',
          },
        ],
      },
    })

    render(
      <DataSourcesList
        spaceId="space-123"
        dataSources={dataSourcesResponse}
        discoveryState={discoveryState}
        discoveryCatalog={[]}
        workflowStatusBySource={{
          'source-1': {
            last_pipeline_status: 'running',
            pending_paper_count: 1,
            pending_relation_review_count: 0,
            graph_edges_delta_last_run: 0,
            graph_edges_total: 4,
            last_failed_stage: null,
          },
        }}
      />,
    )

    await waitFor(() => {
      expect(fetchSourceWorkflowCardStatusAction).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByText(/Poll backend event/i)).toBeInTheDocument()
    })
  })
})
