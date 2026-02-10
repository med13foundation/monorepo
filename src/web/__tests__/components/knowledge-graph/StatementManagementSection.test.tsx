import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StatementManagementSection } from '@/components/knowledge-graph/StatementManagementSection'
import type { PaginatedResponse, PhenotypeResponse } from '@/types/generated'
import type { Mechanism } from '@/types/mechanisms'
import type { Statement } from '@/types/statements'

const mockCreateStatementAction = jest.fn()
const mockUpdateStatementAction = jest.fn()
const mockDeleteStatementAction = jest.fn()
const mockPromoteStatementAction = jest.fn()
const mockSearchPhenotypes = jest.fn()
const mockLookupPhenotypes = jest.fn()

jest.mock('@/app/actions/statements', () => ({
  createStatementAction: (...args: unknown[]) => mockCreateStatementAction(...args),
  updateStatementAction: (...args: unknown[]) => mockUpdateStatementAction(...args),
  deleteStatementAction: (...args: unknown[]) => mockDeleteStatementAction(...args),
  promoteStatementAction: (...args: unknown[]) => mockPromoteStatementAction(...args),
}))

jest.mock('@/lib/api/phenotypes', () => ({
  searchPhenotypes: (...args: unknown[]) => mockSearchPhenotypes(...args),
  lookupPhenotypes: (...args: unknown[]) => mockLookupPhenotypes(...args),
}))

jest.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { access_token: 'test-token' } },
    status: 'authenticated',
  }),
}))

const refreshMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: refreshMock }),
}))

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

const baseStatement: Statement = {
  id: 7,
  title: 'MED13 disruption impairs mediator stability',
  summary: 'Evidence suggests mediator complex destabilization leads to phenotype.',
  evidence_tier: 'moderate',
  confidence_score: 0.74,
  status: 'well_supported',
  source: 'manual_curation',
  protein_domains: [],
  phenotype_ids: [1],
  phenotype_count: 1,
  promoted_mechanism_id: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const baseMechanism: Mechanism = {
  id: 21,
  name: baseStatement.title,
  description: baseStatement.summary,
  evidence_tier: baseStatement.evidence_tier,
  confidence_score: baseStatement.confidence_score,
  source: 'manual_curation',
  lifecycle_state: 'draft',
  protein_domains: [],
  phenotype_ids: [1],
  phenotype_count: 1,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const baseResponse: PaginatedResponse<Statement> = {
  items: [baseStatement],
  total: 1,
  page: 1,
  per_page: 50,
  total_pages: 1,
  has_next: false,
  has_prev: false,
}

const phenotypeResult: PhenotypeResponse = {
  id: 2,
  hpo_id: 'HP:0000002',
  hpo_term: 'Secondary phenotype',
  name: 'Secondary phenotype',
  definition: null,
  synonyms: [],
  category: 'neurological',
  parent_hpo_id: null,
  is_root_term: false,
  frequency_in_med13: null,
  severity_score: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('StatementManagementSection', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateStatementAction.mockResolvedValue({
      success: true,
      data: baseStatement,
    })
    mockUpdateStatementAction.mockResolvedValue({
      success: true,
      data: baseStatement,
    })
    mockPromoteStatementAction.mockResolvedValue({
      success: true,
      data: baseMechanism,
    })
    mockSearchPhenotypes.mockResolvedValue([phenotypeResult])
    mockLookupPhenotypes.mockResolvedValue([phenotypeResult])
  })

  it('renders statements list', () => {
    render(
      <StatementManagementSection
        statements={baseResponse}
        spaceId="space-1"
        canManage
        canPromote
      />,
    )

    expect(screen.getByText('Statements of Understanding')).toBeInTheDocument()
    expect(screen.getByText(baseStatement.title)).toBeInTheDocument()
  })

  it('creates a statement from the dialog', async () => {
    const user = userEvent.setup()
    render(
      <StatementManagementSection
        statements={baseResponse}
        spaceId="space-1"
        canManage
      />,
    )

    await user.click(screen.getByRole('button', { name: /Add Statement/i }))
    await user.type(
      screen.getByLabelText(/Statement title/i),
      'Ciliary transport impairment hypothesis',
    )
    await user.type(
      screen.getByLabelText(/Summary/i),
      'Ciliary transport disruption may explain neurodevelopmental phenotypes.',
    )
    await user.type(screen.getByLabelText(/Linked phenotypes/i), 'HP:0000002')
    await waitFor(() => {
      expect(mockSearchPhenotypes).toHaveBeenCalled()
    })
    await user.click(screen.getByRole('button', { name: /HP:0000002/i }))
    await user.clear(screen.getByLabelText(/Confidence score/i))
    await user.type(screen.getByLabelText(/Confidence score/i), '0.61')

    await user.click(screen.getByRole('button', { name: /Save Statement/i }))

    await waitFor(() => {
      expect(mockCreateStatementAction).toHaveBeenCalledWith('space-1', {
        title: 'Ciliary transport impairment hypothesis',
        summary: 'Ciliary transport disruption may explain neurodevelopmental phenotypes.',
        evidence_tier: 'supporting',
        confidence_score: 0.61,
        status: 'draft',
        source: 'manual_curation',
        protein_domains: [],
        phenotype_ids: [2],
      })
    })
  })

  it('promotes a statement and notifies the parent', async () => {
    const user = userEvent.setup()
    const promoted = jest.fn()

    render(
      <StatementManagementSection
        statements={baseResponse}
        spaceId="space-1"
        canManage
        canPromote
        onPromoted={promoted}
      />,
    )

    await user.click(screen.getByRole('button', { name: /Promote/i }))

    await waitFor(() => {
      expect(mockPromoteStatementAction).toHaveBeenCalledWith('space-1', baseStatement.id)
      expect(promoted).toHaveBeenCalledWith(baseMechanism)
    })
  })
})
