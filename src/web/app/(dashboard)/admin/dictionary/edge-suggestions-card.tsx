'use client'

import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  refreshEntityEmbeddingsAction,
} from '@/app/actions/kernel-hybrid-duplicates'
import {
  fetchEdgeSuggestionCandidatesAction,
  submitEdgeSuggestionDecisionAction,
} from '@/app/actions/kernel-hybrid-edges'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import { EdgeSuggestionsControls } from './edge-suggestions-controls'

interface EdgeSuggestionCandidate {
  source_entity_id: string
  source_display_label: string
  source_entity_type: string
  target_entity_id: string
  target_display_label: string
  target_entity_type: string
  relation_type: string
  final_score: number
  vector_score: number
  graph_overlap_score: number
  relation_prior_score: number
  plausible_message: string
  risk_note: string
}

function parseCsv(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
}

function scorePercent(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
}

export function EdgeSuggestionsCard() {
  const [spaceId, setSpaceId] = useState('')
  const [sourceEntityIds, setSourceEntityIds] = useState('')
  const [allowedRelationTypes, setAllowedRelationTypes] = useState('')
  const [targetEntityTypes, setTargetEntityTypes] = useState('')
  const [minScore, setMinScore] = useState('0.70')
  const [candidates, setCandidates] = useState<EdgeSuggestionCandidate[]>([])
  const [candidateError, setCandidateError] = useState<string | null>(null)
  const [reasonBySuggestion, setReasonBySuggestion] = useState<Record<string, string>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [pendingKey, setPendingKey] = useState<string | null>(null)

  const sourceIds = useMemo(() => parseCsv(sourceEntityIds), [sourceEntityIds])

  async function refreshEmbeddingsForSources(): Promise<void> {
    const normalizedSpaceId = spaceId.trim()
    if (!normalizedSpaceId) {
      toast.error('Research space ID is required.')
      return
    }
    if (sourceIds.length === 0) {
      toast.error('At least one source entity ID is required.')
      return
    }
    const result = await refreshEntityEmbeddingsAction(normalizedSpaceId, sourceIds)
    if (!result.success) {
      toast.error(result.error)
      return
    }
    toast.success(
      `Embeddings refreshed: ${result.data.refreshed} updated, ${result.data.unchanged} unchanged.`,
    )
  }

  async function loadSuggestions(): Promise<void> {
    const normalizedSpaceId = spaceId.trim()
    if (!normalizedSpaceId) {
      toast.error('Research space ID is required.')
      return
    }
    if (sourceIds.length === 0) {
      toast.error('At least one source entity ID is required.')
      return
    }
    const parsedMinScore = Number.parseFloat(minScore)
    if (!Number.isFinite(parsedMinScore) || parsedMinScore < 0 || parsedMinScore > 1) {
      toast.error('Minimum score must be between 0.0 and 1.0.')
      return
    }
    setIsLoading(true)
    setCandidateError(null)
    const result = await fetchEdgeSuggestionCandidatesAction(normalizedSpaceId, {
      source_entity_ids: sourceIds,
      limit_per_source: 10,
      min_score: parsedMinScore,
      allowed_relation_types: parseCsv(allowedRelationTypes),
      target_entity_types: parseCsv(targetEntityTypes),
      exclude_existing_relations: true,
    })
    setIsLoading(false)
    if (!result.success) {
      setCandidateError(result.error)
      setCandidates([])
      return
    }
    setCandidates(result.data)
    if (result.data.length === 0) {
      toast.info('No constrained edge suggestions found with current filters.')
    }
  }

  async function decideSuggestion(
    candidate: EdgeSuggestionCandidate,
    action: 'ACCEPT_AS_DRAFT' | 'REJECT' | 'SNOOZE',
  ): Promise<void> {
    const key = `${candidate.source_entity_id}:${candidate.relation_type}:${candidate.target_entity_id}`
    const reason = (reasonBySuggestion[key] ?? '').trim()
    if (!reason) {
      toast.error('Decision reason is required.')
      return
    }
    const normalizedSpaceId = spaceId.trim()
    if (!normalizedSpaceId) {
      toast.error('Research space ID is required.')
      return
    }

    setPendingKey(key)
    const result = await submitEdgeSuggestionDecisionAction(normalizedSpaceId, {
      sourceEntityId: candidate.source_entity_id,
      targetEntityId: candidate.target_entity_id,
      relationType: candidate.relation_type,
      sourceEntityType: candidate.source_entity_type,
      targetEntityType: candidate.target_entity_type,
      finalScore: candidate.final_score,
      vectorScore: candidate.vector_score,
      graphOverlapScore: candidate.graph_overlap_score,
      relationPriorScore: candidate.relation_prior_score,
      reason,
      action,
    })
    setPendingKey(null)
    if (!result.success) {
      toast.error(result.error)
      return
    }
    if (result.data.relationId) {
      toast.success(`Draft relation created (${result.data.relationId.slice(0, 8)}...).`)
      return
    }
    toast.success('Suggestion decision logged.')
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Edge Suggestion Review</CardTitle>
        <CardDescription>
          Review dictionary-constrained edge suggestions and triage them with required rationale.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <EdgeSuggestionsControls
          values={{
            spaceId,
            sourceEntityIds,
            allowedRelationTypes,
            targetEntityTypes,
            minScore,
          }}
          busy={isLoading}
          mutate={{
            setSpaceId,
            setSourceEntityIds,
            setAllowedRelationTypes,
            setTargetEntityTypes,
            setMinScore,
          }}
          commands={{
            generateSuggestions: () => void loadSuggestions(),
            refreshEmbeddings: () => void refreshEmbeddingsForSources(),
          }}
        />

        {candidateError ? <p className="text-sm text-destructive">{candidateError}</p> : null}

        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No suggestion cards loaded yet.</p>
        ) : (
          <div className="space-y-3">
            {candidates.map((candidate) => {
              const key = `${candidate.source_entity_id}:${candidate.relation_type}:${candidate.target_entity_id}`
              return (
                <Card key={key} className="border-border/70">
                  <CardContent className="space-y-3 p-4">
                    <p className="font-semibold">
                      Suggested edge: {candidate.source_display_label} —[{candidate.relation_type}]→ {candidate.target_display_label}
                    </p>
                    <p className="text-sm text-muted-foreground">{candidate.plausible_message}</p>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge variant="outline">Final: {scorePercent(candidate.final_score)}</Badge>
                      <Badge variant="outline">Vector: {scorePercent(candidate.vector_score)}</Badge>
                      <Badge variant="outline">Graph overlap: {scorePercent(candidate.graph_overlap_score)}</Badge>
                      <Badge variant="outline">Relation prior: {scorePercent(candidate.relation_prior_score)}</Badge>
                      <Badge variant="secondary">Constraint check passed</Badge>
                    </div>
                    <p className="text-xs text-amber-700 dark:text-amber-300">{candidate.risk_note}</p>

                    <div className="space-y-1">
                      <Label htmlFor={`edge-reason-${key}`}>Decision reason (required)</Label>
                      <Input
                        id={`edge-reason-${key}`}
                        value={reasonBySuggestion[key] ?? ''}
                        onChange={(event) =>
                          setReasonBySuggestion((current) => ({ ...current, [key]: event.target.value }))
                        }
                        placeholder="Why this decision is appropriate"
                      />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        disabled={pendingKey === key}
                        onClick={() => void decideSuggestion(candidate, 'ACCEPT_AS_DRAFT')}
                      >
                        Accept as Draft Edge
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={pendingKey === key}
                        onClick={() => void decideSuggestion(candidate, 'REJECT')}
                      >
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={pendingKey === key}
                        onClick={() => void decideSuggestion(candidate, 'SNOOZE')}
                      >
                        Snooze
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
