'use client'

import { type UIEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import {
  searchKernelRelationNodesAction,
  updateKernelRelationStatusAction,
  type NodeSearchOption,
} from '@/app/actions/kernel-relations'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { KernelRelationListResponse, KernelRelationResponse } from '@/types/kernel'

interface SpaceCurationClientProps {
  spaceId: string
  relations: KernelRelationListResponse | null
  relationsError?: string | null
  entityLabelsById: Record<string, string>
  canCurate: boolean
  filters: {
    relationType: string
    curationStatus: string
    nodeIds: string[]
    offset: number
    limit: number
  }
}

const ALL_CURATION_STATUSES = '__all__'
const NODE_SEARCH_MIN_CHARS = 2
const NODE_SEARCH_LIMIT = 40

function truncate(value: string, maxLen: number): string {
  if (value.length <= maxLen) {
    return value
  }
  return value.slice(0, maxLen - 1) + '…'
}

function humanizeToken(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function compactId(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}…${value.slice(-6)}`
}

function formatConfidence(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'Not scored'
  }
  if (value <= 1) {
    return `${Math.round(value * 100)}%`
  }
  return `${Math.round(value)}%`
}

function confidencePercent(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null
  }
  if (value <= 1) {
    return Math.max(0, Math.min(100, Math.round(value * 100)))
  }
  return Math.max(0, Math.min(100, Math.round(value)))
}

function confidenceToneClass(value: number | null): string {
  if (value === null) return 'bg-muted-foreground/35'
  if (value >= 80) return 'bg-primary'
  if (value >= 60) return 'bg-accent'
  return 'bg-destructive'
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }
  return date.toLocaleString()
}

function relationConnectorPhrase(relationType: string): string {
  const normalized = relationType.trim().toUpperCase()
  const predefined: Record<string, string> = {
    ASSOCIATED_WITH: 'is associated with',
    CAUSES: 'causes',
    RESULTS_IN: 'results in',
    PROTECTIVE_EFFECT: 'protects against',
    TREATS: 'treats',
    CONTRAINDICATED_FOR: 'is contraindicated for',
    LOSS_OF_FUNCTION_INCREASES_PHENOTYPE_SEVERITY: 'causes',
  }
  const mapped = predefined[normalized]
  if (mapped) return mapped
  return humanizeToken(relationType).toLowerCase()
}

function statusBadgeVariant(
  status: string,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'APPROVED') return 'default'
  if (status === 'REJECTED' || status === 'RETRACTED') return 'destructive'
  if (status === 'UNDER_REVIEW') return 'secondary'
  return 'outline'
}

function mergeNodeOptions(
  current: NodeSearchOption[],
  incoming: NodeSearchOption[],
): NodeSearchOption[] {
  const merged = [...current]
  const seenIds = new Set(current.map((option) => option.id))
  for (const option of incoming) {
    if (seenIds.has(option.id)) {
      continue
    }
    seenIds.add(option.id)
    merged.push(option)
  }
  return merged
}

export default function SpaceCurationClient({
  spaceId,
  relations,
  relationsError,
  entityLabelsById,
  canCurate,
  filters,
}: SpaceCurationClientProps) {
  const router = useRouter()
  const [relationType, setRelationType] = useState(filters.relationType)
  const [selectedNodeIds, setSelectedNodeIds] = useState(filters.nodeIds)
  const [nodeSearchInput, setNodeSearchInput] = useState('')
  const [nodeSearchOptions, setNodeSearchOptions] = useState<NodeSearchOption[]>([])
  const [nodeSearchHasMore, setNodeSearchHasMore] = useState(false)
  const [nodeSearchOffset, setNodeSearchOffset] = useState(0)
  const [nodeSearchLoading, setNodeSearchLoading] = useState(false)
  const [curationStatus, setCurationStatus] = useState(
    filters.curationStatus || ALL_CURATION_STATUSES,
  )
  const [pendingRelationId, setPendingRelationId] = useState<string | null>(null)
  const nodeSearchRequestIdRef = useRef(0)
  const [nodeLabelsById, setNodeLabelsById] = useState<Record<string, string>>(() => {
    const seeded: Record<string, string> = {}
    for (const [entityId, label] of Object.entries(entityLabelsById)) {
      const trimmedLabel = label.trim()
      if (trimmedLabel.length > 0) {
        seeded[entityId] = trimmedLabel
      }
    }
    for (const nodeId of filters.nodeIds) {
      if (seeded[nodeId]) {
        continue
      }
      seeded[nodeId] = `Entity ${compactId(nodeId)}`
    }
    return seeded
  })

  const appliedRelationType = useMemo(
    () => filters.relationType.trim().toUpperCase(),
    [filters.relationType],
  )
  const appliedCurationStatus = useMemo(() => {
    const raw = filters.curationStatus.trim().toUpperCase()
    return raw === ALL_CURATION_STATUSES ? '' : raw
  }, [filters.curationStatus])
  const appliedNodeIdSet = useMemo(
    () =>
      new Set(
        filters.nodeIds
          .map((nodeId) => nodeId.trim())
          .filter((nodeId) => nodeId.length > 0),
      ),
    [filters.nodeIds],
  )
  const rows = useMemo(() => {
    const baseRows = relations?.relations ?? []
    return baseRows.filter((relation) => {
      if (
        appliedRelationType.length > 0 &&
        relation.relation_type.trim().toUpperCase() !== appliedRelationType
      ) {
        return false
      }
      if (
        appliedCurationStatus.length > 0 &&
        relation.curation_status.trim().toUpperCase() !== appliedCurationStatus
      ) {
        return false
      }
      if (
        appliedNodeIdSet.size > 0 &&
        !appliedNodeIdSet.has(relation.source_id) &&
        !appliedNodeIdSet.has(relation.target_id)
      ) {
        return false
      }
      return true
    })
  }, [
    relations?.relations,
    appliedCurationStatus,
    appliedNodeIdSet,
    appliedRelationType,
  ])
  const selectedNodeIdSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds])

  useEffect(() => {
    setRelationType(filters.relationType)
  }, [filters.relationType])

  useEffect(() => {
    setCurationStatus(filters.curationStatus || ALL_CURATION_STATUSES)
  }, [filters.curationStatus])

  useEffect(() => {
    setSelectedNodeIds(filters.nodeIds)
  }, [filters.nodeIds])

  useEffect(() => {
    setNodeLabelsById((current) => {
      const merged = { ...current }
      for (const [entityId, label] of Object.entries(entityLabelsById)) {
        const trimmedLabel = label.trim()
        if (trimmedLabel.length === 0) {
          continue
        }
        merged[entityId] = trimmedLabel
      }
      return merged
    })
  }, [entityLabelsById])

  function resolveEntityLabel(entityId: string): string {
    const label = nodeLabelsById[entityId]
    if (typeof label === 'string' && label.trim().length > 0) {
      return label.trim()
    }
    return `Entity ${compactId(entityId)}`
  }

  const rememberNodeLabels = useCallback((options: NodeSearchOption[]) => {
    if (options.length === 0) {
      return
    }
    setNodeLabelsById((current) => {
      const merged = { ...current }
      for (const option of options) {
        merged[option.id] = option.label
      }
      return merged
    })
  }, [])

  const fetchNodeOptions = useCallback(
    async (
      query: string,
      requestedOffset: number,
      append: boolean,
    ): Promise<void> => {
      const normalizedQuery = query.trim()
      if (normalizedQuery.length < NODE_SEARCH_MIN_CHARS) {
        setNodeSearchOptions([])
        setNodeSearchHasMore(false)
        setNodeSearchOffset(0)
        setNodeSearchLoading(false)
        return
      }

      const requestId = nodeSearchRequestIdRef.current + 1
      nodeSearchRequestIdRef.current = requestId
      setNodeSearchLoading(true)

      const result = await searchKernelRelationNodesAction(
        spaceId,
        normalizedQuery,
        requestedOffset,
        NODE_SEARCH_LIMIT,
      )

      if (requestId !== nodeSearchRequestIdRef.current) {
        return
      }

      setNodeSearchLoading(false)

      if (!result.success) {
        if (!append) {
          setNodeSearchOptions([])
        }
        setNodeSearchHasMore(false)
        toast.error(result.error)
        return
      }

      rememberNodeLabels(result.data.options)
      setNodeSearchOptions((current) =>
        append ? mergeNodeOptions(current, result.data.options) : result.data.options,
      )
      setNodeSearchHasMore(result.data.hasMore)
      setNodeSearchOffset(result.data.nextOffset)
    },
    [rememberNodeLabels, spaceId],
  )

  useEffect(() => {
    const normalizedQuery = nodeSearchInput.trim()
    if (normalizedQuery.length < NODE_SEARCH_MIN_CHARS) {
      nodeSearchRequestIdRef.current += 1
      setNodeSearchOptions([])
      setNodeSearchHasMore(false)
      setNodeSearchOffset(0)
      setNodeSearchLoading(false)
      return
    }

    const timeoutId = window.setTimeout(() => {
      void fetchNodeOptions(normalizedQuery, 0, false)
    }, 180)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [fetchNodeOptions, nodeSearchInput])

  const onNodeOptionToggle = useCallback(
    (option: NodeSearchOption, checked: boolean) => {
      rememberNodeLabels([option])
      setSelectedNodeIds((current) => {
        const alreadySelected = current.includes(option.id)
        if (checked) {
          return alreadySelected ? current : [...current, option.id]
        }
        if (!alreadySelected) {
          return current
        }
        return current.filter((id) => id !== option.id)
      })
    },
    [rememberNodeLabels],
  )

  const removeSelectedNode = useCallback((nodeId: string) => {
    setSelectedNodeIds((current) => current.filter((id) => id !== nodeId))
  }, [])

  const onNodeOptionsScroll = useCallback(
    (event: UIEvent<HTMLDivElement>): void => {
      if (nodeSearchLoading || !nodeSearchHasMore) {
        return
      }
      const element = event.currentTarget
      if (element.scrollTop + element.clientHeight < element.scrollHeight - 24) {
        return
      }
      void fetchNodeOptions(nodeSearchInput, nodeSearchOffset, true)
    },
    [
      fetchNodeOptions,
      nodeSearchHasMore,
      nodeSearchInput,
      nodeSearchLoading,
      nodeSearchOffset,
    ],
  )

  async function copyEntityId(id: string, label: 'Source' | 'Target') {
    try {
      await navigator.clipboard.writeText(id)
      toast.success(`${label} entity ID copied`)
    } catch {
      toast.error('Failed to copy entity ID')
    }
  }

  async function updateStatus(relation: KernelRelationResponse, status: string) {
    setPendingRelationId(relation.id)
    const result = await updateKernelRelationStatusAction(spaceId, relation.id, status)
    setPendingRelationId(null)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success(`Relation marked ${status}`)
    router.refresh()
  }

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Data Curation"
        description="Review kernel relations and update curation status."
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setRelationType('')
                setSelectedNodeIds([])
                setNodeSearchInput('')
                setNodeSearchOptions([])
                setNodeSearchHasMore(false)
                setNodeSearchOffset(0)
                setCurationStatus(ALL_CURATION_STATUSES)
                router.push(`/spaces/${spaceId}/curation`)
              }}
            >
              Clear
            </Button>
            <Button
              onClick={() => {
                const params = new URLSearchParams()
                const relTrim = relationType.trim()
                const statusTrim =
                  curationStatus === ALL_CURATION_STATUSES
                    ? ''
                    : curationStatus.trim()
                const uniqueNodeIds = Array.from(
                  new Set(
                    selectedNodeIds
                      .map((nodeId) => nodeId.trim())
                      .filter((nodeId) => nodeId.length > 0),
                  ),
                )
                if (relTrim) params.set('relation_type', relTrim)
                if (uniqueNodeIds.length > 0) {
                  params.set('node_ids', uniqueNodeIds.join(','))
                }
                if (statusTrim) params.set('curation_status', statusTrim)
                router.push(
                  params.toString().length > 0
                    ? `/spaces/${spaceId}/curation?${params.toString()}`
                    : `/spaces/${spaceId}/curation`,
                )
              }}
            >
              Apply
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Card className="border-border/80 bg-card">
            <CardContent className="grid gap-4 py-6 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="relation_type" className="font-semibold text-foreground">
                  Relation Type (optional)
                </Label>
                <Input
                  id="relation_type"
                  value={relationType}
                  onChange={(e) => setRelationType(e.target.value)}
                  placeholder="e.g. ASSOCIATED_WITH"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="node_search" className="font-semibold text-foreground">
                  Node Filter (optional)
                </Label>
                <div className="space-y-2 rounded-md border border-border/70 bg-background/50 p-2">
                  <div className="flex min-h-11 flex-wrap items-center gap-2 rounded-md border border-input bg-background px-2 py-1">
                    {selectedNodeIds.map((nodeId) => (
                      <span
                        key={nodeId}
                        className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/35 bg-primary/10 px-2 py-0.5 text-xs"
                      >
                        <span className="truncate">
                          {resolveEntityLabel(nodeId)}
                        </span>
                        <button
                          type="button"
                          className="rounded px-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                          onClick={() => removeSelectedNode(nodeId)}
                          aria-label={`Remove ${resolveEntityLabel(nodeId)}`}
                        >
                          ×
                        </button>
                      </span>
                    ))}
                    <Input
                      id="node_search"
                      value={nodeSearchInput}
                      onChange={(event) => setNodeSearchInput(event.target.value)}
                      placeholder="Type to search nodes by label or ID"
                      className="h-7 min-w-48 flex-1 border-0 bg-transparent px-1 py-0 text-sm shadow-none focus-visible:ring-0"
                    />
                  </div>

                  <div
                    className="max-h-44 space-y-2 overflow-auto rounded-md border border-border/70 bg-background/70 p-2"
                    onScroll={onNodeOptionsScroll}
                  >
                    {nodeSearchInput.trim().length < NODE_SEARCH_MIN_CHARS ? (
                      <div className="text-xs text-muted-foreground">
                        Type at least {NODE_SEARCH_MIN_CHARS} characters to search nodes.
                      </div>
                    ) : nodeSearchOptions.length === 0 && !nodeSearchLoading ? (
                      <div className="text-xs text-muted-foreground">
                        No nodes match this query.
                      </div>
                    ) : (
                      nodeSearchOptions.map((option) => {
                        const isSelected = selectedNodeIdSet.has(option.id)
                        const optionLabel = `${option.label} (${option.entityType})`
                        return (
                          <div
                            key={option.id}
                            className="flex items-start gap-2 rounded-md border border-transparent px-2 py-1 transition-colors hover:border-border hover:bg-muted/55"
                          >
                            <Checkbox
                              id={`node-option-${option.id}`}
                              checked={isSelected}
                              onCheckedChange={(checked) =>
                                onNodeOptionToggle(option, checked === true)
                              }
                            />
                            <Label
                              htmlFor={`node-option-${option.id}`}
                              className="flex min-w-0 flex-1 cursor-pointer flex-col gap-1"
                            >
                              <span className="truncate text-xs font-medium text-foreground">
                                {optionLabel}
                              </span>
                              <span className="font-mono text-[10px] text-muted-foreground">
                                {compactId(option.id)}
                              </span>
                            </Label>
                          </div>
                        )
                      })
                    )}
                    {nodeSearchLoading ? (
                      <div className="px-1 text-xs text-muted-foreground">
                        Loading node options...
                      </div>
                    ) : null}
                    {nodeSearchHasMore && !nodeSearchLoading ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 w-full text-xs"
                        onClick={() => {
                          void fetchNodeOptions(nodeSearchInput, nodeSearchOffset, true)
                        }}
                      >
                        Load more nodes
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <Label className="font-semibold text-foreground">Curation Status (optional)</Label>
                <Select value={curationStatus} onValueChange={(value) => setCurationStatus(value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="All statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_CURATION_STATUSES}>All</SelectItem>
                    {(['DRAFT', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RETRACTED'] as const).map((s) => (
                      <SelectItem key={s} value={s}>
                        {humanizeToken(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {relationsError ? (
            <Card>
              <CardContent className="py-10 text-center text-destructive">
                {relationsError}
              </CardContent>
            </Card>
          ) : rows.length === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-muted-foreground">
                No relations found.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {rows.map((rel) => {
                const sourceLabel = resolveEntityLabel(rel.source_id)
                const targetLabel = resolveEntityLabel(rel.target_id)
                const confidence = confidencePercent(rel.confidence)
                const connector = relationConnectorPhrase(rel.relation_type)

                return (
                  <Card key={rel.id} className="border-border bg-card shadow-sm">
                    <CardContent className="space-y-4 p-5">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={statusBadgeVariant(rel.curation_status)}>
                            {humanizeToken(rel.curation_status)}
                          </Badge>
                          <span className="font-mono text-xs text-muted-foreground">
                            Claim ID: {compactId(rel.id)}
                          </span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          Updated {formatTimestamp(rel.updated_at)}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 md:gap-3">
                        <span className="rounded-lg border border-primary/35 bg-primary/10 px-3 py-1 text-base font-semibold text-foreground md:text-xl">
                          {sourceLabel}
                        </span>
                        <span className="font-serif text-lg italic text-foreground/80 md:text-2xl">
                          {connector}
                        </span>
                        <span className="rounded-lg border border-secondary/40 bg-secondary/15 px-3 py-1 text-base font-semibold text-foreground md:text-xl">
                          {targetLabel}
                        </span>
                      </div>

                      <p className="font-mono text-xs tracking-wide text-muted-foreground">
                        {humanizeToken(rel.relation_type)} ({rel.relation_type})
                      </p>

                      <div className="h-px bg-border" />

                      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-3 text-sm">
                            <div className="h-2.5 w-52 overflow-hidden rounded-full bg-muted">
                              <div
                                className={`h-full ${confidenceToneClass(confidence)}`}
                                style={{ width: `${confidence ?? 0}%` }}
                              />
                            </div>
                            <span className="font-medium text-foreground/85">
                              {formatConfidence(rel.confidence)} certainty
                            </span>
                          </div>

                          <p className="text-sm leading-6 text-foreground/80">
                            {rel.evidence_summary ? (
                              truncate(rel.evidence_summary, 220)
                            ) : (
                              'No evidence summary available yet.'
                            )}
                          </p>

                          <div className="flex flex-wrap items-center gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2.5 text-xs"
                              onClick={() => copyEntityId(rel.source_id, 'Source')}
                            >
                              Copy source ID
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2.5 text-xs"
                              onClick={() => copyEntityId(rel.target_id, 'Target')}
                            >
                              Copy target ID
                            </Button>
                          </div>
                        </div>

                        {canCurate && (
                          <div className="flex flex-wrap items-center justify-start gap-2 md:justify-end">
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={pendingRelationId === rel.id}
                              onClick={() => updateStatus(rel, 'UNDER_REVIEW')}
                            >
                              Needs Review
                            </Button>
                            <Button
                              size="sm"
                              disabled={pendingRelationId === rel.id}
                              onClick={() => updateStatus(rel, 'APPROVED')}
                            >
                              Support
                            </Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              disabled={pendingRelationId === rel.id}
                              onClick={() => updateStatus(rel, 'REJECTED')}
                            >
                              Contradict
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </div>
      </DashboardSection>
    </div>
  )
}
