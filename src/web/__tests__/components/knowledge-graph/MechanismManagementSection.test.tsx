import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MechanismManagementSection } from '@/components/knowledge-graph/MechanismManagementSection'
import type { PaginatedResponse, PhenotypeResponse } from '@/types/generated'
import type { Mechanism } from '@/types/mechanisms'

const mockCreateMechanismAction = jest.fn()
const mockUpdateMechanismAction = jest.fn()
const mockDeleteMechanismAction = jest.fn()
const mockSearchPhenotypes = jest.fn()
const mockLookupPhenotypes = jest.fn()

jest.mock('@/app/actions/mechanisms', () => ({
  createMechanismAction: (...args: unknown[]) => mockCreateMechanismAction(...args),
  updateMechanismAction: (...args: unknown[]) => mockUpdateMechanismAction(...args),
  deleteMechanismAction: (...args: unknown[]) => mockDeleteMechanismAction(...args),
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

const baseMechanism: Mechanism = {
  id: 1,
  name: 'Mediator complex disruption',
  description: 'Test mechanism',
  evidence_tier: 'strong',
  confidence_score: 0.8,
  source: 'manual_curation',
  lifecycle_state: 'draft',
  protein_domains: [],
  phenotype_ids: [1],
  phenotype_count: 1,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const baseResponse: PaginatedResponse<Mechanism> = {
  items: [baseMechanism],
  total: 1,
  page: 1,
  per_page: 50,
  total_pages: 1,
  has_next: false,
  has_prev: false,
}

const phenotypeResult: PhenotypeResponse = {
  id: 1,
  hpo_id: 'HP:0000001',
  hpo_term: 'Test phenotype',
  name: 'Test phenotype',
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

describe('MechanismManagementSection', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateMechanismAction.mockResolvedValue({
      success: true,
      data: baseMechanism,
    })
    mockUpdateMechanismAction.mockResolvedValue({
      success: true,
      data: baseMechanism,
    })
    mockSearchPhenotypes.mockResolvedValue([phenotypeResult])
    mockLookupPhenotypes.mockResolvedValue([phenotypeResult])
  })

  it('renders mechanisms list', () => {
    render(
      <MechanismManagementSection
        mechanisms={baseResponse}
        spaceId="space-1"
        canManage
      />,
    )

    expect(screen.getByText('Canonical mechanisms')).toBeInTheDocument()
    expect(screen.getByText('Mediator complex disruption')).toBeInTheDocument()
  })

  it('creates a mechanism from the dialog', async () => {
    const user = userEvent.setup()
    render(
      <MechanismManagementSection
        mechanisms={baseResponse}
        spaceId="space-1"
        canManage
      />,
    )

    await user.click(screen.getByRole('button', { name: /Add Canonical Mechanism/i }))
    await user.type(screen.getByLabelText(/Mechanism name/i), 'Ciliary transport defect')
    await user.type(
      screen.getByLabelText(/Description/i),
      'Disrupts ciliary transport and leads to neurodevelopmental phenotypes.',
    )
    await user.type(screen.getByLabelText(/Linked phenotypes/i), 'HP:0000001')
    await waitFor(() => {
      expect(mockSearchPhenotypes).toHaveBeenCalled()
    })
    await user.click(screen.getByRole('button', { name: /HP:0000001/i }))
    await user.clear(screen.getByLabelText(/Confidence score/i))
    await user.type(screen.getByLabelText(/Confidence score/i), '0.72')

    await user.click(screen.getByRole('button', { name: /Save Mechanism/i }))

    await waitFor(() => {
      expect(mockCreateMechanismAction).toHaveBeenCalledWith('space-1', {
        name: 'Ciliary transport defect',
        description: 'Disrupts ciliary transport and leads to neurodevelopmental phenotypes.',
        evidence_tier: 'supporting',
        confidence_score: 0.72,
        source: 'manual_curation',
        lifecycle_state: 'draft',
        protein_domains: [],
        phenotype_ids: [1],
      })
    })
  })

  it('updates a mechanism from the dialog', async () => {
    const user = userEvent.setup()
    render(
      <MechanismManagementSection
        mechanisms={baseResponse}
        spaceId="space-1"
        canManage
      />,
    )

    await user.click(screen.getByRole('button', { name: /Edit/i }))
    const nameInput = screen.getByLabelText(/Mechanism name/i)
    await user.clear(nameInput)
    await user.type(nameInput, 'Updated mechanism name')

    await user.click(screen.getByRole('button', { name: /Save Mechanism/i }))

    await waitFor(() => {
      expect(mockUpdateMechanismAction).toHaveBeenCalledWith(
        'space-1',
        baseMechanism.id,
        expect.objectContaining({ name: 'Updated mechanism name' }),
      )
    })
  })
})
