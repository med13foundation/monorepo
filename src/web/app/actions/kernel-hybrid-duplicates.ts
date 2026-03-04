'use server'

import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'
import { proposeSpaceConceptDecision } from '@/lib/api/concepts'
import {
  fetchKernelEntity,
  fetchKernelRelations,
  fetchKernelSimilarEntities,
  fetchRelationClaims,
  refreshKernelEntityEmbeddings,
} from '@/lib/api/kernel'
import type { RelationClaimResponse } from '@/types/kernel'

import {
  type ActionResult,
  type NearDuplicateCandidate,
  type NearDuplicateDecisionInput,
  decisionTypeForNearDuplicate,
  extractTokenSet,
  fetchEntityIndex,
  intersectionCount,
  normalizeForAlias,
  normalizeLabel,
  revalidateHybridPaths,
  toJsonObject,
} from './kernel-hybrid-shared'

async function fetchNeighborIndex(
  spaceId: string,
  entityIds: string[],
  token: string,
): Promise<Map<string, Set<string>>> {
  const neighborIndex = new Map<string, Set<string>>()
  for (const entityId of entityIds) {
    neighborIndex.set(entityId, new Set<string>())
  }
  if (entityIds.length === 0) {
    return neighborIndex
  }

  const response = await fetchKernelRelations(
    spaceId,
    { node_ids: entityIds, offset: 0, limit: 200 },
    token,
  )
  for (const relation of response.relations) {
    const sourceNeighbors = neighborIndex.get(relation.source_id) ?? new Set<string>()
    sourceNeighbors.add(relation.target_id)
    neighborIndex.set(relation.source_id, sourceNeighbors)

    const targetNeighbors = neighborIndex.get(relation.target_id) ?? new Set<string>()
    targetNeighbors.add(relation.source_id)
    neighborIndex.set(relation.target_id, targetNeighbors)
  }
  return neighborIndex
}

export async function fetchNearDuplicateCandidatesAction(
  spaceId: string,
  sourceEntityId: string,
  minSimilarity = 0.72,
): Promise<ActionResult<NearDuplicateCandidate[]>> {
  try {
    const token = await requireAccessToken()
    const sourceEntity = await fetchKernelEntity(spaceId, sourceEntityId, token)
    const similar = await fetchKernelSimilarEntities(
      spaceId,
      sourceEntityId,
      { min_similarity: minSimilarity, limit: 25 },
      token,
    )

    const targetIds = similar.results.map((item) => item.entity_id)
    const entityIndex = await fetchEntityIndex(spaceId, targetIds, token)
    const neighborIndex = await fetchNeighborIndex(
      spaceId,
      [sourceEntity.id, ...targetIds],
      token,
    )
    const sourceMetadata = toJsonObject(sourceEntity.metadata)
    const sourceIdentifiers = extractTokenSet(sourceMetadata, ['identifiers', 'identifier_values', 'external_ids'])
    const sourceProvenance = extractTokenSet(sourceMetadata, ['provenance_ids', 'source_refs', 'provenance'])
    const sourceNeighbors = neighborIndex.get(sourceEntity.id) ?? new Set<string>()

    const candidates = similar.results.map((item) => {
      const targetEntity = entityIndex.get(item.entity_id)
      const targetMetadata = toJsonObject(targetEntity?.metadata ?? {})
      const targetIdentifiers = extractTokenSet(targetMetadata, ['identifiers', 'identifier_values', 'external_ids'])
      const targetProvenance = extractTokenSet(targetMetadata, ['provenance_ids', 'source_refs', 'provenance'])
      const targetNeighbors = neighborIndex.get(item.entity_id) ?? new Set<string>()
      const sharedNeighborCount = intersectionCount(sourceNeighbors, targetNeighbors)
      const sharedIdentifierCount = intersectionCount(sourceIdentifiers, targetIdentifiers)
      const provenanceOverlapCount = intersectionCount(sourceProvenance, targetProvenance)
      const sourceLabel = normalizeLabel(sourceEntity.display_label, sourceEntity.id)
      const targetLabel = normalizeLabel(item.display_label, item.entity_id)
      const sameType = sourceEntity.entity_type === item.entity_type

      let riskNote = 'Potential false merge risk: review source evidence before applying merge.'
      if (normalizeForAlias(sourceLabel) === normalizeForAlias(targetLabel) && sourceLabel !== targetLabel) {
        riskNote = 'Potential false merge risk: labels differ by alias formatting only.'
      } else if (item.score_breakdown.graph_overlap_score < 0.1) {
        riskNote = 'Potential false merge risk: semantic similarity is high, but graph overlap is low.'
      }

      return {
        source_entity_id: sourceEntity.id,
        source_display_label: sourceLabel,
        source_entity_type: sourceEntity.entity_type,
        target_entity_id: item.entity_id,
        target_display_label: targetLabel,
        target_entity_type: item.entity_type,
        similarity_score: item.similarity_score,
        vector_score: item.score_breakdown.vector_score,
        graph_overlap_score: item.score_breakdown.graph_overlap_score,
        shared_neighbor_count: sharedNeighborCount,
        shared_identifier_count: sharedIdentifierCount,
        provenance_overlap_count: provenanceOverlapCount,
        plausible_message:
          `Plausible duplicate because ${sameType ? 'same entity type' : 'cross-type semantic match'}, ` +
          `high semantic similarity (${item.similarity_score.toFixed(2)}), shared identifiers (${sharedIdentifierCount}), ` +
          `and overlapping neighborhood (${sharedNeighborCount} shared neighbors).`,
        risk_note: riskNote,
      }
    })
    return { success: true, data: candidates }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchNearDuplicateCandidatesAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to fetch near-duplicate candidates'),
    }
  }
}

export async function refreshEntityEmbeddingsAction(
  spaceId: string,
  entityIds: string[],
): Promise<ActionResult<{ refreshed: number; unchanged: number; processed: number }>> {
  try {
    const token = await requireAccessToken()
    const response = await refreshKernelEntityEmbeddings(
      spaceId,
      { entity_ids: entityIds, limit: Math.max(entityIds.length, 50) },
      token,
    )
    revalidateHybridPaths(spaceId)
    return {
      success: true,
      data: {
        refreshed: response.refreshed,
        unchanged: response.unchanged,
        processed: response.processed,
      },
    }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] refreshEntityEmbeddingsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to refresh embeddings'),
    }
  }
}

export async function submitNearDuplicateDecisionAction(
  spaceId: string,
  payload: NearDuplicateDecisionInput,
): Promise<ActionResult<{ decisionId: string; createdAt: string }>> {
  const reason = payload.reason.trim()
  if (reason.length === 0) {
    return { success: false, error: 'Reason is required for decision logging.' }
  }
  try {
    const token = await requireAccessToken()
    const decision = await proposeSpaceConceptDecision(
      spaceId,
      {
        decision_type: decisionTypeForNearDuplicate(payload.action),
        rationale: reason,
        confidence: payload.similarityScore,
        decision_payload: {
          workflow: 'near_duplicate',
          action: payload.action,
          source_entity_id: payload.sourceEntityId,
          target_entity_id: payload.targetEntityId,
          source_entity_type: payload.sourceEntityType,
          target_entity_type: payload.targetEntityType,
        },
        evidence_payload: {
          vector_score: payload.vectorScore,
          graph_overlap_score: payload.graphOverlapScore,
          shared_identifier_count: payload.sharedIdentifierCount,
          provenance_overlap_count: payload.provenanceOverlapCount,
        },
      },
      token,
    )
    revalidateHybridPaths(spaceId)
    return { success: true, data: { decisionId: decision.id, createdAt: decision.created_at } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] submitNearDuplicateDecisionAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to log near-duplicate decision'),
    }
  }
}

export async function listHypothesisClaimsAction(spaceId: string): Promise<ActionResult<RelationClaimResponse[]>> {
  try {
    const token = await requireAccessToken()
    const claims = await fetchRelationClaims(spaceId, { polarity: 'HYPOTHESIS', limit: 50 }, token)
    return { success: true, data: claims.claims }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] listHypothesisClaimsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load hypotheses'),
    }
  }
}

export async function createUserHypothesisAction(
  spaceId: string,
  statement: string,
  rationale: string,
): Promise<ActionResult<{ decisionId: string }>> {
  const normalizedStatement = statement.trim()
  const normalizedRationale = rationale.trim()
  if (normalizedStatement.length === 0 || normalizedRationale.length === 0) {
    return { success: false, error: 'Hypothesis statement and rationale are required.' }
  }
  try {
    const token = await requireAccessToken()
    const decision = await proposeSpaceConceptDecision(
      spaceId,
      {
        decision_type: 'CREATE',
        rationale: normalizedRationale,
        decision_payload: {
          workflow: 'hypothesis',
          statement: normalizedStatement,
        },
      },
      token,
    )
    revalidateHybridPaths(spaceId)
    return { success: true, data: { decisionId: decision.id } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createUserHypothesisAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create hypothesis'),
    }
  }
}
