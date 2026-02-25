import {
  buildGraphModel,
  filterGraphModel,
  mergeGraphModels,
  pruneGraphModelForRender,
} from '@/lib/graph/model'
import type { KernelGraphSubgraphResponse } from '@/types/kernel'

function makeSubgraphResponse(): KernelGraphSubgraphResponse {
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
        aggregate_confidence: 0.52,
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
  }
}

describe('graph model', () => {
  it('normalizes nodes and edges from subgraph response', () => {
    const model = buildGraphModel(makeSubgraphResponse())
    expect(model.stats.nodeCount).toBe(3)
    expect(model.stats.edgeCount).toBe(2)
    expect(model.nodeById.n1.label).toBe('MED13')
    expect(model.edgeById.e1.confidence).toBeCloseTo(0.91)
  })

  it('merges incoming graph without duplicating existing nodes/edges', () => {
    const base = buildGraphModel(makeSubgraphResponse())
    const incoming = buildGraphModel({
      nodes: [
        ...makeSubgraphResponse().nodes,
        {
          id: 'n4',
          research_space_id: 'space-1',
          entity_type: 'PHENOTYPE',
          display_label: 'Bradycardia',
          metadata: {},
          created_at: '2026-02-23T00:00:00Z',
          updated_at: '2026-02-23T00:00:00Z',
        },
      ],
      edges: [
        ...makeSubgraphResponse().edges,
        {
          id: 'e3',
          research_space_id: 'space-1',
          source_id: 'n1',
          relation_type: 'ASSOCIATED_WITH',
          target_id: 'n4',
          aggregate_confidence: 0.74,
          source_count: 1,
          highest_evidence_tier: 'LITERATURE',
          curation_status: 'UNDER_REVIEW',
          provenance_id: null,
          reviewed_by: null,
          reviewed_at: null,
          created_at: '2026-02-23T00:00:00Z',
          updated_at: '2026-02-23T00:00:00Z',
        },
      ],
    })

    const merged = mergeGraphModels(base, incoming)
    expect(merged.stats.nodeCount).toBe(4)
    expect(merged.stats.edgeCount).toBe(3)
  })

  it('filters by relation type and curation status', () => {
    const model = buildGraphModel(makeSubgraphResponse())
    const filtered = filterGraphModel(
      model,
      new Set(['ASSOCIATED_WITH']),
      new Set(['APPROVED']),
    )
    expect(filtered.stats.edgeCount).toBe(1)
    expect(filtered.edges[0]?.relationType).toBe('ASSOCIATED_WITH')
    expect(filtered.edges[0]?.curationStatus).toBe('APPROVED')
  })

  it('prunes graph to render caps', () => {
    const model = buildGraphModel(makeSubgraphResponse())
    const pruned = pruneGraphModelForRender(model, 2, 1)
    expect(pruned.model.stats.nodeCount).toBeLessThanOrEqual(2)
    expect(pruned.model.stats.edgeCount).toBeLessThanOrEqual(1)
    expect(pruned.truncatedNodes || pruned.truncatedEdges).toBe(true)
  })
})
