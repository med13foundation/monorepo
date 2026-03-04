import { fireEvent, render, screen } from '@testing-library/react'

import SpaceCurationClient from '@/app/(dashboard)/spaces/[spaceId]/space-curation-client'

const routerPushMock = jest.fn()
const routerRefreshMock = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: routerPushMock,
    replace: jest.fn(),
    refresh: routerRefreshMock,
  }),
}))

jest.mock('@/app/actions/kernel-relations', () => ({
  searchKernelRelationNodesAction: jest.fn().mockResolvedValue({
    success: true,
    data: { options: [], hasMore: false, nextOffset: 0 },
  }),
  updateKernelRelationStatusAction: jest.fn().mockResolvedValue({ success: true, data: {} }),
  updateRelationClaimStatusAction: jest.fn().mockResolvedValue({ success: true, data: {} }),
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}))

describe('SpaceCurationClient', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  const baseProps = {
    spaceId: 'space-1',
    relations: {
      relations: [
        {
          id: 'rel-1',
          research_space_id: 'space-1',
          source_id: 'ent-1',
          relation_type: 'ASSOCIATED_WITH',
          target_id: 'ent-2',
          confidence: 0.86,
          aggregate_confidence: 0.86,
          source_count: 1,
          highest_evidence_tier: 'LITERATURE',
          curation_status: 'DRAFT',
          provenance_id: null,
          reviewed_by: null,
          reviewed_at: null,
          created_at: '2026-02-26T00:00:00Z',
          updated_at: '2026-02-27T00:00:00Z',
          evidence_summary: 'Evidence summary',
          evidence_tier: 'LITERATURE',
        },
      ],
      total: 1,
      offset: 0,
      limit: 25,
    },
    relationsError: null,
    claims: {
      claims: [
        {
          id: 'claim-1',
          research_space_id: 'space-1',
          source_document_id: 'doc-1',
          agent_run_id: 'run-1',
          source_type: 'pubmed',
          relation_type: 'ASSOCIATED_WITH',
          target_type: 'DISEASE',
          source_label: 'MED13',
          target_label: 'Cardiomyopathy',
          confidence: 0.45,
          validation_state: 'FORBIDDEN',
          validation_reason: 'Out of ontology constraints',
          persistability: 'NON_PERSISTABLE' as const,
          claim_status: 'OPEN' as const,
          polarity: 'UNCERTAIN' as const,
          claim_text: 'MED13 was associated with cardiomyopathy in one cohort.',
          claim_section: 'results',
          linked_relation_id: null,
          metadata: {},
          triaged_by: null,
          triaged_at: null,
          created_at: '2026-02-27T00:00:00Z',
          updated_at: '2026-02-27T00:00:00Z',
        },
      ],
      total: 1,
      offset: 0,
      limit: 25,
    },
    claimsError: null,
    relationConflicts: {
      conflicts: [],
      total: 0,
      offset: 0,
      limit: 50,
    },
    entityLabelsById: {
      'ent-1': 'MED13',
      'ent-2': 'Cardiomyopathy',
    },
    canCurate: true,
    relationFilters: {
      relationType: '',
      curationStatus: '',
      validationState: '',
      sourceDocumentId: '',
      certaintyBand: '',
      nodeQuery: '',
      nodeIds: [],
      offset: 0,
      limit: 25,
    },
    claimFilters: {
      claimStatus: '',
      validationState: '',
      persistability: '',
      polarity: '',
      relationType: '',
      sourceDocumentId: '',
      linkedRelationId: '',
      certaintyBand: '',
      offset: 0,
      limit: 25,
    },
  }

  it('renders graph relations tab with certainty and graph filters', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="graph" />)

    expect(screen.getByText('Graph Relations')).toBeInTheDocument()
    expect(screen.getByText('Extraction Claims')).toBeInTheDocument()
    expect(screen.getByText('AI High certainty')).toBeInTheDocument()
    expect(screen.getByText('Node IDs (optional)')).toBeInTheDocument()
    expect(screen.getByText('Approve')).toBeInTheDocument()
  })

  it('renders extraction claims tab with certainty and claim filters', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="claims" />)

    expect(screen.getByText('AI Low certainty')).toBeInTheDocument()
    expect(screen.getByText('Claim Status')).toBeInTheDocument()
    expect(screen.getByText('Validation State')).toBeInTheDocument()
    expect(screen.getByText('Polarity')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Needs mapping/i }),
    ).toBeInTheDocument()
  })

  it('renders conflict badge on graph cards when relation is conflicting', () => {
    render(
      <SpaceCurationClient
        {...baseProps}
        activeTab="graph"
        relationConflicts={{
          conflicts: [
            {
              relation_id: 'rel-1',
              support_count: 3,
              refute_count: 1,
              support_claim_ids: ['claim-a', 'claim-b', 'claim-c'],
              refute_claim_ids: ['claim-d'],
            },
          ],
          total: 1,
          offset: 0,
          limit: 50,
        }}
      />,
    )

    expect(screen.getByText('Conflict 3/1')).toBeInTheDocument()
  })

  it('renders evidence sentence details and paper links in graph cards', () => {
    const propsWithSentence = {
      ...baseProps,
      relations: {
        ...baseProps.relations,
        relations: [
          {
            ...baseProps.relations.relations[0],
            evidence_summary: null,
            evidence_sentence:
              'MED13 variation was associated with cardiomyopathy in the study cohort.',
            evidence_sentence_source: 'artana_generated',
            paper_links: [
              {
                label: 'PubMed',
                url: 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
                source: 'external_record_id',
              },
            ],
          },
        ],
      },
    }

    render(<SpaceCurationClient {...propsWithSentence} activeTab="graph" />)

    expect(
      screen.getByText(
        'MED13 variation was associated with cardiomyopathy in the study cohort.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('AI-generated (not verbatim span)'),
    ).toBeInTheDocument()
    const sourceLink = screen.getByRole('link', { name: 'PubMed' })
    expect(sourceLink).toHaveAttribute(
      'href',
      'https://pubmed.ncbi.nlm.nih.gov/12345678/',
    )
    expect(sourceLink).toHaveAttribute('target', '_blank')
  })

  it('routes to claims tab when tab button is selected', () => {
    render(<SpaceCurationClient {...baseProps} activeTab="graph" />)

    fireEvent.click(screen.getByRole('button', { name: 'Extraction Claims' }))

    expect(routerPushMock).toHaveBeenCalled()
    const lastCall = routerPushMock.mock.calls[routerPushMock.mock.calls.length - 1]?.[0]
    expect(String(lastCall)).toContain('/spaces/space-1/curation?')
    expect(String(lastCall)).toContain('tab=claims')
  })
})
