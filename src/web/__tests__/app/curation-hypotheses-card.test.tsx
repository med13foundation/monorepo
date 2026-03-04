import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import CurationHypothesesCard from '@/app/(dashboard)/spaces/[spaceId]/curation/curation-hypotheses-card'

const listHypothesesActionMock = jest.fn()
const createManualHypothesisActionMock = jest.fn()
const generateHypothesesActionMock = jest.fn()
const updateRelationClaimStatusActionMock = jest.fn()

jest.mock('@/app/actions/kernel-hypotheses', () => ({
  listHypothesesAction: (...args: unknown[]) => listHypothesesActionMock(...args),
  createManualHypothesisAction: (...args: unknown[]) => createManualHypothesisActionMock(...args),
  generateHypothesesAction: (...args: unknown[]) => generateHypothesesActionMock(...args),
}))

jest.mock('@/app/actions/kernel-relations', () => ({
  updateRelationClaimStatusAction: (...args: unknown[]) => updateRelationClaimStatusActionMock(...args),
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}))

const hypothesis = {
  claim_id: '11111111-1111-1111-1111-111111111111',
  polarity: 'HYPOTHESIS' as const,
  claim_status: 'OPEN' as const,
  validation_state: 'ALLOWED',
  persistability: 'PERSISTABLE' as const,
  confidence: 0.82,
  source_label: 'MED13',
  relation_type: 'ASSOCIATED_WITH',
  target_label: 'Autism',
  claim_text: 'MED13 may influence autism through transcription regulation.',
  origin: 'graph_agent',
  seed_entity_ids: ['22222222-2222-2222-2222-222222222222'],
  supporting_provenance_ids: ['33333333-3333-3333-3333-333333333333'],
  created_at: '2026-03-03T10:00:00Z',
  metadata: {
    origin: 'graph_agent',
  },
}

describe('CurationHypothesesCard', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    listHypothesesActionMock.mockResolvedValue({
      success: true,
      data: [hypothesis],
    })
    createManualHypothesisActionMock.mockResolvedValue({
      success: true,
      data: hypothesis,
    })
    generateHypothesesActionMock.mockResolvedValue({
      success: true,
      data: {
        run_id: 'run-1',
        requested_seed_count: 1,
        used_seed_count: 1,
        candidates_seen: 4,
        created_count: 1,
        deduped_count: 0,
        errors: [],
        hypotheses: [hypothesis],
      },
    })
    updateRelationClaimStatusActionMock.mockResolvedValue({
      success: true,
      data: {
        id: hypothesis.claim_id,
      },
    })
  })

  it('loads hypotheses on mount', async () => {
    render(
      <CurationHypothesesCard
        spaceId="space-1"
        canEdit={true}
        autoGenerationEnabled={true}
      />,
    )

    await waitFor(() => {
      expect(listHypothesesActionMock).toHaveBeenCalledWith('space-1')
    })
    expect(screen.getByText('MED13 -> ASSOCIATED_WITH -> Autism')).toBeInTheDocument()
  })

  it('logs a manual hypothesis', async () => {
    render(
      <CurationHypothesesCard
        spaceId="space-1"
        canEdit={true}
        autoGenerationEnabled={true}
      />,
    )

    fireEvent.change(screen.getByLabelText('Hypothesis statement'), {
      target: { value: 'Manual statement' },
    })
    fireEvent.change(screen.getByLabelText('Rationale'), {
      target: { value: 'Manual rationale' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Log hypothesis' }))

    await waitFor(() => {
      expect(createManualHypothesisActionMock).toHaveBeenCalledWith('space-1', {
        statement: 'Manual statement',
        rationale: 'Manual rationale',
        seedEntityIds: [],
        sourceType: 'manual',
      })
    })
  })

  it('hides auto-generate button when feature flag is disabled', async () => {
    render(
      <CurationHypothesesCard
        spaceId="space-1"
        canEdit={true}
        autoGenerationEnabled={false}
      />,
    )

    await waitFor(() => {
      expect(listHypothesesActionMock).toHaveBeenCalled()
    })
    expect(
      screen.queryByRole('button', { name: 'Auto-generate from graph' }),
    ).not.toBeInTheDocument()
  })

  it('runs auto-generation and triage action', async () => {
    render(
      <CurationHypothesesCard
        spaceId="space-1"
        canEdit={true}
        autoGenerationEnabled={true}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Auto-generate from graph' }))

    await waitFor(() => {
      expect(generateHypothesesActionMock).toHaveBeenCalledWith('space-1', {
        seed_entity_ids: null,
        source_type: 'pubmed',
        max_depth: 2,
        max_hypotheses: 20,
      })
    })

    fireEvent.click(screen.getByRole('button', { name: 'Needs mapping' }))
    await waitFor(() => {
      expect(updateRelationClaimStatusActionMock).toHaveBeenCalledWith(
        'space-1',
        hypothesis.claim_id,
        'NEEDS_MAPPING',
      )
    })
  })
})
