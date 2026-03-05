'use client'

import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  fetchNearDuplicateCandidatesAction,
  refreshEntityEmbeddingsAction,
  submitNearDuplicateDecisionAction,
} from '@/app/actions/kernel-hybrid-duplicates'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { ConceptMemberResponse } from '@/types/concepts'

interface NearDuplicateCandidate {
  source_entity_id: string
  source_display_label: string
  source_entity_type: string
  target_entity_id: string
  target_display_label: string
  target_entity_type: string
  similarity_score: number
  vector_score: number
  graph_overlap_score: number
  shared_neighbor_count: number
  shared_identifier_count: number
  provenance_overlap_count: number
  plausible_message: string
  risk_note: string
}

interface ConceptNearDuplicatesCardProps {
  spaceId: string
  canEdit: boolean
  conceptMembers: ConceptMemberResponse[]
}

function scorePercent(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
}

function deriveKernelEntityId(member: ConceptMemberResponse): string | null {
  const metadata = member.metadata_payload
  const keys = ['kernel_entity_id', 'entity_id', 'kernelEntityId', 'entityId']
  for (const key of keys) {
    const value = metadata[key]
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim()
    }
  }
  return null
}

export function ConceptNearDuplicatesCard({
  spaceId,
  canEdit,
  conceptMembers,
}: ConceptNearDuplicatesCardProps) {
  const [sourceEntityId, setSourceEntityId] = useState('')
  const [minSimilarity, setMinSimilarity] = useState('0.72')
  const [loading, setLoading] = useState(false)
  const [candidates, setCandidates] = useState<NearDuplicateCandidate[]>([])
  const [candidateError, setCandidateError] = useState<string | null>(null)
  const [reasonByTargetId, setReasonByTargetId] = useState<Record<string, string>>({})
  const [pendingTargetId, setPendingTargetId] = useState<string | null>(null)

  const kernelEntityOptions = useMemo(() => {
    const options: Array<{ entityId: string; label: string }> = []
    const seen = new Set<string>()
    for (const member of conceptMembers) {
      const entityId = deriveKernelEntityId(member)
      if (!entityId || seen.has(entityId)) {
        continue
      }
      seen.add(entityId)
      options.push({ entityId, label: member.canonical_label })
    }
    return options
  }, [conceptMembers])

  async function loadCandidates(): Promise<void> {
    const normalizedSourceId = sourceEntityId.trim()
    if (!normalizedSourceId) {
      toast.error('Source entity ID is required.')
      return
    }
    const parsedMinSimilarity = Number.parseFloat(minSimilarity)
    if (!Number.isFinite(parsedMinSimilarity) || parsedMinSimilarity < 0 || parsedMinSimilarity > 1) {
      toast.error('Minimum similarity must be between 0.0 and 1.0.')
      return
    }

    setLoading(true)
    setCandidateError(null)
    const result = await fetchNearDuplicateCandidatesAction(spaceId, normalizedSourceId, parsedMinSimilarity)
    setLoading(false)

    if (!result.success) {
      setCandidates([])
      setCandidateError(result.error)
      return
    }

    setCandidates(result.data)
    if (result.data.length === 0) {
      toast.info('No near-duplicate candidates found for this entity.')
    }
  }

  async function refreshEmbeddings(): Promise<void> {
    const normalizedSourceId = sourceEntityId.trim()
    if (!normalizedSourceId) {
      toast.error('Source entity ID is required to refresh embeddings.')
      return
    }
    setLoading(true)
    const refreshResult = await refreshEntityEmbeddingsAction(spaceId, [normalizedSourceId])
    setLoading(false)
    if (!refreshResult.success) {
      toast.error(refreshResult.error)
      return
    }
    toast.success(
      `Embeddings refreshed: ${refreshResult.data.refreshed} updated, ${refreshResult.data.unchanged} unchanged.`,
    )
  }

  async function submitDecision(
    candidate: NearDuplicateCandidate,
    action: 'MERGE' | 'LINK_AS_RELATED' | 'NOT_DUPLICATE' | 'SNOOZE',
  ): Promise<void> {
    const reason = (reasonByTargetId[candidate.target_entity_id] ?? '').trim()
    if (!reason) {
      toast.error('Decision reason is required.')
      return
    }
    setPendingTargetId(candidate.target_entity_id)
    const result = await submitNearDuplicateDecisionAction(spaceId, {
      sourceEntityId: candidate.source_entity_id,
      targetEntityId: candidate.target_entity_id,
      sourceEntityType: candidate.source_entity_type,
      targetEntityType: candidate.target_entity_type,
      similarityScore: candidate.similarity_score,
      vectorScore: candidate.vector_score,
      graphOverlapScore: candidate.graph_overlap_score,
      sharedIdentifierCount: candidate.shared_identifier_count,
      provenanceOverlapCount: candidate.provenance_overlap_count,
      reason,
      action,
    })
    setPendingTargetId(null)
    if (!result.success) {
      toast.error(result.error)
      return
    }
    toast.success(`Decision logged at ${new Date(result.data.createdAt).toLocaleString()}.`)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Near-Duplicate Triage</CardTitle>
        <CardDescription>
          Review possible duplicates in the existing concept workflow with required rationale and audit logging.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="near-dup-source-id">Source Kernel Entity ID</Label>
            <Input
              id="near-dup-source-id"
              value={sourceEntityId}
              onChange={(event) => setSourceEntityId(event.target.value)}
              placeholder="UUID of the source entity"
              list="concept-kernel-entity-options"
            />
            <datalist id="concept-kernel-entity-options">
              {kernelEntityOptions.map((option) => (
                <option key={option.entityId} value={option.entityId}>
                  {option.label}
                </option>
              ))}
            </datalist>
          </div>
          <div className="space-y-1">
            <Label htmlFor="near-dup-min-similarity">Min Similarity</Label>
            <Input
              id="near-dup-min-similarity"
              value={minSimilarity}
              onChange={(event) => setMinSimilarity(event.target.value)}
              placeholder="0.72"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void loadCandidates()} disabled={loading}>
            Find Near Duplicates
          </Button>
          <Button variant="outline" onClick={() => void refreshEmbeddings()} disabled={loading}>
            Refresh Embeddings
          </Button>
        </div>

        {candidateError ? <p className="text-sm text-destructive">{candidateError}</p> : null}

        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No candidate cards loaded yet.</p>
        ) : (
          <div className="space-y-3">
            {candidates.map((candidate) => (
              <Card key={`${candidate.source_entity_id}-${candidate.target_entity_id}`} className="border-border/70">
                <CardContent className="space-y-3 p-4">
                  <p className="font-semibold">
                    Possible duplicate: {candidate.source_display_label} ↔ {candidate.target_display_label}
                  </p>
                  <p className="text-sm text-muted-foreground">{candidate.plausible_message}</p>

                  <div className="flex flex-wrap gap-2 text-xs">
                    <Badge variant="outline">Vector score: {scorePercent(candidate.vector_score)}</Badge>
                    <Badge variant="outline">Graph overlap: {scorePercent(candidate.graph_overlap_score)}</Badge>
                    <Badge variant="outline">Shared neighbors: {candidate.shared_neighbor_count}</Badge>
                    <Badge variant="outline">
                      Shared identifiers: {candidate.shared_identifier_count}
                    </Badge>
                    <Badge variant="outline">
                      Provenance overlap: {candidate.provenance_overlap_count}
                    </Badge>
                  </div>

                  <p className="text-xs text-amber-700 dark:text-amber-300">{candidate.risk_note}</p>

                  <div className="space-y-1">
                    <Label htmlFor={`reason-${candidate.target_entity_id}`}>Decision reason (required)</Label>
                    <Input
                      id={`reason-${candidate.target_entity_id}`}
                      value={reasonByTargetId[candidate.target_entity_id] ?? ''}
                      onChange={(event) =>
                        setReasonByTargetId((current) => ({
                          ...current,
                          [candidate.target_entity_id]: event.target.value,
                        }))
                      }
                      placeholder="Why this action is appropriate"
                    />
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      disabled={!canEdit || pendingTargetId === candidate.target_entity_id}
                      onClick={() => void submitDecision(candidate, 'MERGE')}
                    >
                      Merge
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!canEdit || pendingTargetId === candidate.target_entity_id}
                      onClick={() => void submitDecision(candidate, 'LINK_AS_RELATED')}
                    >
                      Link as Related
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={!canEdit || pendingTargetId === candidate.target_entity_id}
                      onClick={() => void submitDecision(candidate, 'NOT_DUPLICATE')}
                    >
                      Not Duplicate
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!canEdit || pendingTargetId === candidate.target_entity_id}
                      onClick={() => void submitDecision(candidate, 'SNOOZE')}
                    >
                      Snooze
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
