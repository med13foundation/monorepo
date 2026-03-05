'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  getClaimParticipantCoverageAction,
  listClaimsByEntityAction,
  listClaimParticipantsAction,
  listClaimRelationsAction,
  runClaimParticipantBackfillAction,
  updateClaimRelationReviewAction,
} from '@/app/actions/kernel-claim-relations'
import { listHypothesesAction } from '@/app/actions/kernel-hypotheses'
import type {
  ClaimParticipantCoverageResponse,
  ClaimParticipantResponse,
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  RelationClaimResponse,
  HypothesisResponse,
} from '@/types/kernel'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import {
  ClaimOverlayToolbar,
  type ReviewStatusFilter,
} from './claim-overlay/claim-overlay-toolbar'
import { ClaimOverlayRelationList } from './claim-overlay/claim-overlay-relation-list'
import { ClaimOverlayParticipantPanel } from './claim-overlay/claim-overlay-participant-panel'

interface ClaimOverlayGraphPanelProps {
  spaceId: string
  canCurate: boolean
  openClaimsTab: () => void
  openCanonicalGraphRelation: (relationId: string) => void
}

interface ClaimOverlayPanelState {
  isLoading: boolean
  isParticipantLoading: boolean
  pendingRelationId: string | null
  reviewFilter: ReviewStatusFilter
  relations: ClaimRelationResponse[]
  claimsById: Record<string, HypothesisResponse>
  selectedClaimId: string | null
  selectedParticipants: ClaimParticipantResponse[]
  coverage: ClaimParticipantCoverageResponse | null
  isBackfillRunning: boolean
  error: string | null
}

const INITIAL_STATE: ClaimOverlayPanelState = {
  isLoading: false,
  isParticipantLoading: false,
  pendingRelationId: null,
  reviewFilter: 'ALL',
  relations: [],
  claimsById: {},
  selectedClaimId: null,
  selectedParticipants: [],
  coverage: null,
  isBackfillRunning: false,
  error: null,
}

interface TraversalEdge {
  nextClaimId: string
  relationId: string
}

interface TraversalPath {
  claimIds: string[]
  relationIds: string[]
}

function compactId(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`
}

function buildClaimTraversalIndex(
  relations: ClaimRelationResponse[],
): Record<string, TraversalEdge[]> {
  const index: Record<string, TraversalEdge[]> = {}
  for (const relation of relations) {
    const source = relation.source_claim_id
    const target = relation.target_claim_id
    if (!index[source]) {
      index[source] = []
    }
    if (!index[target]) {
      index[target] = []
    }
    index[source].push({ nextClaimId: target, relationId: relation.id })
    index[target].push({ nextClaimId: source, relationId: relation.id })
  }
  return index
}

function toClaimIdSet(claims: RelationClaimResponse[]): Set<string> {
  return new Set(
    claims
      .map((claim) => claim.id.trim())
      .filter((claimId) => claimId.length > 0),
  )
}

function findShortestTraversalPath({
  relations,
  sourceClaimIds,
  targetClaimIds,
}: {
  relations: ClaimRelationResponse[]
  sourceClaimIds: Set<string>
  targetClaimIds: Set<string>
}): TraversalPath | null {
  if (sourceClaimIds.size === 0 || targetClaimIds.size === 0) {
    return null
  }
  for (const sourceClaimId of sourceClaimIds) {
    if (targetClaimIds.has(sourceClaimId)) {
      return { claimIds: [sourceClaimId], relationIds: [] }
    }
  }
  const adjacency = buildClaimTraversalIndex(relations)
  const queue: string[] = []
  const parentClaimById: Record<string, string | null> = {}
  const parentRelationByClaimId: Record<string, string> = {}
  const visited = new Set<string>()

  for (const sourceClaimId of sourceClaimIds) {
    queue.push(sourceClaimId)
    visited.add(sourceClaimId)
    parentClaimById[sourceClaimId] = null
  }

  let targetHit: string | null = null
  let offset = 0
  while (offset < queue.length && targetHit === null) {
    const current = queue[offset]
    offset += 1
    const neighbors = adjacency[current] ?? []
    for (const neighbor of neighbors) {
      const nextClaimId = neighbor.nextClaimId
      if (visited.has(nextClaimId)) {
        continue
      }
      visited.add(nextClaimId)
      parentClaimById[nextClaimId] = current
      parentRelationByClaimId[nextClaimId] = neighbor.relationId
      if (targetClaimIds.has(nextClaimId)) {
        targetHit = nextClaimId
        break
      }
      queue.push(nextClaimId)
    }
  }

  if (targetHit === null) {
    return null
  }

  const claimIds: string[] = []
  const relationIds: string[] = []
  let cursor: string | null = targetHit
  while (cursor !== null) {
    claimIds.push(cursor)
    const relationId = parentRelationByClaimId[cursor]
    if (typeof relationId === 'string' && relationId.trim().length > 0) {
      relationIds.push(relationId)
    }
    cursor = parentClaimById[cursor] ?? null
  }

  claimIds.reverse()
  relationIds.reverse()
  return { claimIds, relationIds }
}

export default function ClaimOverlayGraphPanel({
  spaceId,
  canCurate,
  openClaimsTab,
  openCanonicalGraphRelation,
}: ClaimOverlayGraphPanelProps) {
  const [state, setState] = useState<ClaimOverlayPanelState>(INITIAL_STATE)
  const [focusSourceEntityId, setFocusSourceEntityId] = useState('')
  const [focusTargetEntityId, setFocusTargetEntityId] = useState('')
  const [focusedClaimIds, setFocusedClaimIds] = useState<string[]>([])
  const [focusedRelationIds, setFocusedRelationIds] = useState<string[]>([])
  const [focusSummary, setFocusSummary] = useState<string | null>(null)
  const [isPathFinding, setIsPathFinding] = useState(false)

  const refreshOverlay = useCallback(async (): Promise<void> => {
    setState((previous) => ({ ...previous, isLoading: true }))
    const [relationsResult, claimsResult, coverageResult] = await Promise.all([
      listClaimRelationsAction(spaceId, { offset: 0, limit: 200 }),
      listHypothesesAction(spaceId),
      getClaimParticipantCoverageAction(spaceId),
    ])

    if (!relationsResult.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: relationsResult.error,
      }))
      return
    }
    if (!claimsResult.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: claimsResult.error,
      }))
      return
    }
    if (!coverageResult.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: coverageResult.error,
      }))
      return
    }

    const claimIndex: Record<string, HypothesisResponse> = {}
    for (const claim of claimsResult.data) {
      claimIndex[claim.claim_id] = claim
    }

    setState((previous) => ({
      ...previous,
      isLoading: false,
      error: null,
      relations: relationsResult.data,
      claimsById: claimIndex,
      coverage: coverageResult.data,
    }))
  }, [spaceId])

  useEffect(() => {
    void refreshOverlay()
  }, [refreshOverlay])

  const filteredRelations = useMemo(() => {
    if (state.reviewFilter === 'ALL') {
      return state.relations
    }
    return state.relations.filter((relation) => relation.review_status === state.reviewFilter)
  }, [state.relations, state.reviewFilter])
  const highlightedClaimIds = useMemo(
    () => new Set(focusedClaimIds),
    [focusedClaimIds],
  )
  const highlightedRelationIds = useMemo(
    () => new Set(focusedRelationIds),
    [focusedRelationIds],
  )

  async function selectClaimParticipants(claimId: string): Promise<void> {
    setState((previous) => ({
      ...previous,
      selectedClaimId: claimId,
      isParticipantLoading: true,
    }))

    const result = await listClaimParticipantsAction(spaceId, claimId)
    if (!result.success) {
      setState((previous) => ({
        ...previous,
        isParticipantLoading: false,
        selectedParticipants: [],
        error: result.error,
      }))
      toast.error(result.error)
      return
    }

    setState((previous) => ({
      ...previous,
      isParticipantLoading: false,
      selectedParticipants: result.data,
      error: null,
    }))
  }

  async function updateReviewStatus(
    relation: ClaimRelationResponse,
    reviewStatus: ClaimRelationReviewStatus,
  ): Promise<void> {
    if (!canCurate) {
      toast.error('You do not have permission to review claim relations.')
      return
    }
    setState((previous) => ({ ...previous, pendingRelationId: relation.id }))

    const result = await updateClaimRelationReviewAction(spaceId, relation.id, reviewStatus)
    if (!result.success) {
      setState((previous) => ({
        ...previous,
        pendingRelationId: null,
        error: result.error,
      }))
      toast.error(result.error)
      return
    }

    setState((previous) => ({
      ...previous,
      pendingRelationId: null,
      error: null,
      relations: previous.relations.map((candidate) =>
        candidate.id === relation.id ? result.data : candidate,
      ),
    }))
    toast.success(`Claim edge moved to ${reviewStatus.toLowerCase()}.`)
  }

  async function runBackfill(dryRun: boolean): Promise<void> {
    if (!canCurate) {
      toast.error('You do not have permission to run participant backfill.')
      return
    }

    setState((previous) => ({ ...previous, isBackfillRunning: true }))
    const result = await runClaimParticipantBackfillAction(spaceId, dryRun)
    if (!result.success) {
      setState((previous) => ({
        ...previous,
        isBackfillRunning: false,
        error: result.error,
      }))
      toast.error(result.error)
      return
    }

    setState((previous) => ({ ...previous, isBackfillRunning: false, error: null }))
    toast.success(
      `Backfill ${dryRun ? 'dry run' : 'apply run'}: scanned ${result.data.scanned_claims}, created ${result.data.created_participants}.`,
    )
    await refreshOverlay()
  }

  async function findFocusPath(): Promise<void> {
    const sourceEntityId = focusSourceEntityId.trim()
    const targetEntityId = focusTargetEntityId.trim()
    if (sourceEntityId.length === 0 || targetEntityId.length === 0) {
      toast.error('Enter both source and target entity IDs to find a path.')
      return
    }
    if (sourceEntityId === targetEntityId) {
      toast.error('Source and target entity IDs must be different.')
      return
    }
    setIsPathFinding(true)
    setFocusSummary(null)

    const [sourceClaimsResult, targetClaimsResult] = await Promise.all([
      listClaimsByEntityAction(spaceId, sourceEntityId, { offset: 0, limit: 200 }),
      listClaimsByEntityAction(spaceId, targetEntityId, { offset: 0, limit: 200 }),
    ])
    setIsPathFinding(false)

    if (!sourceClaimsResult.success) {
      setFocusedClaimIds([])
      setFocusedRelationIds([])
      setFocusSummary(sourceClaimsResult.error)
      toast.error(sourceClaimsResult.error)
      return
    }
    if (!targetClaimsResult.success) {
      setFocusedClaimIds([])
      setFocusedRelationIds([])
      setFocusSummary(targetClaimsResult.error)
      toast.error(targetClaimsResult.error)
      return
    }

    const sourceClaimIds = toClaimIdSet(sourceClaimsResult.data.claims)
    const targetClaimIds = toClaimIdSet(targetClaimsResult.data.claims)
    if (sourceClaimIds.size === 0 || targetClaimIds.size === 0) {
      setFocusedClaimIds([])
      setFocusedRelationIds([])
      setFocusSummary('No claim endpoints were found for one or both entities.')
      return
    }

    const traversalRelations =
      state.reviewFilter === 'ALL'
        ? state.relations
        : state.relations.filter((relation) => relation.review_status === state.reviewFilter)
    const traversalPath = findShortestTraversalPath({
      relations: traversalRelations,
      sourceClaimIds,
      targetClaimIds,
    })
    if (traversalPath === null) {
      setFocusedClaimIds([])
      setFocusedRelationIds([])
      setFocusSummary('No claim path found with the current overlay review filter.')
      return
    }

    setFocusedClaimIds(traversalPath.claimIds)
    setFocusedRelationIds(traversalPath.relationIds)
    setFocusSummary(
      `Focused path with ${traversalPath.claimIds.length} claims across ${traversalPath.relationIds.length} links.`,
    )
  }

  function clearFocusPath(): void {
    setFocusedClaimIds([])
    setFocusedRelationIds([])
    setFocusSummary(null)
  }

  return (
    <div className="space-y-4">
      <ClaimOverlayToolbar
        canCurate={canCurate}
        isLoading={state.isLoading}
        isBackfillRunning={state.isBackfillRunning}
        coverage={state.coverage}
        reviewFilter={state.reviewFilter}
        refreshOverlay={() => void refreshOverlay()}
        runDryBackfill={() => void runBackfill(true)}
        runBackfill={() => void runBackfill(false)}
        openClaimsTab={openClaimsTab}
        changeReviewFilter={(value) =>
          setState((previous) => ({
            ...previous,
            reviewFilter: value,
          }))
        }
      />

      <Card className="border-border/80 bg-card">
        <CardContent className="space-y-3 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">Focus Path</p>
            <p className="text-xs text-muted-foreground">
              Find shortest claim-link path between two entities (using current review filter).
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto_auto]">
            <div className="space-y-1">
              <Label htmlFor="claim-overlay-focus-source">From entity ID</Label>
              <Input
                id="claim-overlay-focus-source"
                value={focusSourceEntityId}
                onChange={(event) => setFocusSourceEntityId(event.target.value)}
                placeholder="UUID"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="claim-overlay-focus-target">To entity ID</Label>
              <Input
                id="claim-overlay-focus-target"
                value={focusTargetEntityId}
                onChange={(event) => setFocusTargetEntityId(event.target.value)}
                placeholder="UUID"
              />
            </div>
            <Button type="button" className="self-end" disabled={isPathFinding} onClick={() => void findFocusPath()}>
              {isPathFinding ? 'Finding path...' : 'Find path'}
            </Button>
            <Button type="button" variant="outline" className="self-end" onClick={clearFocusPath}>
              Clear path
            </Button>
          </div>
          {focusSummary ? <p className="text-xs text-muted-foreground">{focusSummary}</p> : null}
          {focusedClaimIds.length > 0 ? (
            <p className="font-mono text-xs text-muted-foreground">
              {focusedClaimIds.map((claimId) => compactId(claimId)).join(' -> ')}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {state.error ? (
        <Card>
          <CardContent className="py-6 text-sm text-destructive">{state.error}</CardContent>
        </Card>
      ) : null}

      {filteredRelations.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              No claim overlay edges exist yet. Create/review links from the hypotheses workflow.
            </p>
            <Button type="button" onClick={openClaimsTab}>
              Create Or Review Claim Links
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <ClaimOverlayRelationList
            relations={filteredRelations}
            claimsById={state.claimsById}
            canCurate={canCurate}
            pendingRelationId={state.pendingRelationId}
            highlightedRelationIds={highlightedRelationIds}
            highlightedClaimIds={highlightedClaimIds}
            openClaimsTab={openClaimsTab}
            openCanonicalGraphRelation={openCanonicalGraphRelation}
            selectClaimParticipants={(claimId) => void selectClaimParticipants(claimId)}
            updateReviewStatus={(relation, reviewStatus) =>
              void updateReviewStatus(relation, reviewStatus)
            }
          />
          <ClaimOverlayParticipantPanel
            spaceId={spaceId}
            openClaimsTab={openClaimsTab}
            selectedClaimId={state.selectedClaimId}
            isLoading={state.isParticipantLoading}
            participants={state.selectedParticipants}
          />
        </div>
      )}
    </div>
  )
}
