'use server'

import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'
import { proposeSpaceConceptDecision } from '@/lib/api/concepts'
import { createKernelRelation, suggestKernelRelations } from '@/lib/api/kernel'
import type { KernelRelationSuggestionRequest } from '@/types/kernel'

import {
  type ActionResult,
  type EdgeSuggestionCandidate,
  type EdgeSuggestionDecisionInput,
  decisionTypeForEdge,
  fetchEntityIndex,
  normalizeLabel,
  revalidateHybridPaths,
} from './kernel-hybrid-shared'

export async function fetchEdgeSuggestionCandidatesAction(
  spaceId: string,
  request: KernelRelationSuggestionRequest,
): Promise<ActionResult<EdgeSuggestionCandidate[]>> {
  try {
    const token = await requireAccessToken()
    const response = await suggestKernelRelations(spaceId, request, token)
    const ids = new Set<string>()
    for (const suggestion of response.suggestions) {
      ids.add(suggestion.source_entity_id)
      ids.add(suggestion.target_entity_id)
    }
    const entityIndex = await fetchEntityIndex(spaceId, Array.from(ids), token)
    const candidates = response.suggestions.map((suggestion) => {
      const source = entityIndex.get(suggestion.source_entity_id)
      const target = entityIndex.get(suggestion.target_entity_id)
      const sourceLabel = normalizeLabel(source?.display_label, suggestion.source_entity_id)
      const targetLabel = normalizeLabel(target?.display_label, suggestion.target_entity_id)
      const lowOverlap = suggestion.score_breakdown.graph_overlap_score < 0.1
      return {
        source_entity_id: suggestion.source_entity_id,
        source_display_label: sourceLabel,
        source_entity_type: suggestion.constraint_check.source_entity_type,
        target_entity_id: suggestion.target_entity_id,
        target_display_label: targetLabel,
        target_entity_type: suggestion.constraint_check.target_entity_type,
        relation_type: suggestion.relation_type,
        final_score: suggestion.final_score,
        vector_score: suggestion.score_breakdown.vector_score,
        graph_overlap_score: suggestion.score_breakdown.graph_overlap_score,
        relation_prior_score: suggestion.score_breakdown.relation_prior_score,
        plausible_message:
          `Plausible edge because dictionary allows ${suggestion.constraint_check.source_entity_type} -> ` +
          `${suggestion.relation_type} -> ${suggestion.constraint_check.target_entity_type}, vector ${suggestion.score_breakdown.vector_score.toFixed(2)}, ` +
          `graph overlap ${suggestion.score_breakdown.graph_overlap_score.toFixed(2)}, prior ${suggestion.score_breakdown.relation_prior_score.toFixed(2)}.`,
        risk_note: lowOverlap
          ? 'Potential false positive risk: low graph neighborhood overlap.'
          : 'Review supporting evidence before accepting into draft graph.',
      }
    })
    return { success: true, data: candidates }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchEdgeSuggestionCandidatesAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to fetch edge suggestions'),
    }
  }
}

export async function submitEdgeSuggestionDecisionAction(
  spaceId: string,
  payload: EdgeSuggestionDecisionInput,
): Promise<ActionResult<{ decisionId: string; relationId: string | null }>> {
  const reason = payload.reason.trim()
  if (reason.length === 0) {
    return { success: false, error: 'Reason is required for decision logging.' }
  }
  try {
    const token = await requireAccessToken()
    const decision = await proposeSpaceConceptDecision(
      spaceId,
      {
        decision_type: decisionTypeForEdge(payload.action),
        rationale: reason,
        confidence: payload.finalScore,
        decision_payload: {
          workflow: 'edge_suggestion',
          action: payload.action,
          source_entity_id: payload.sourceEntityId,
          target_entity_id: payload.targetEntityId,
          relation_type: payload.relationType,
          source_entity_type: payload.sourceEntityType,
          target_entity_type: payload.targetEntityType,
        },
        evidence_payload: {
          vector_score: payload.vectorScore,
          graph_overlap_score: payload.graphOverlapScore,
          relation_prior_score: payload.relationPriorScore,
        },
      },
      token,
    )

    let relationId: string | null = null
    if (payload.action === 'ACCEPT_AS_DRAFT') {
      const relation = await createKernelRelation(
        spaceId,
        {
          source_id: payload.sourceEntityId,
          relation_type: payload.relationType,
          target_id: payload.targetEntityId,
          confidence: payload.finalScore,
          evidence_summary: `Accepted from constrained suggestion with rationale: ${reason}`,
        },
        token,
      )
      relationId = relation.id
    }

    revalidateHybridPaths(spaceId)
    return { success: true, data: { decisionId: decision.id, relationId } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] submitEdgeSuggestionDecisionAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to submit edge suggestion decision'),
    }
  }
}
