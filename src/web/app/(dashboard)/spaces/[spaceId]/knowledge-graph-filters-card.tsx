import { type UIEvent, useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface KnowledgeGraphFiltersCardProps {
  availableRelationTypes: string[]
  availableCurationStatuses: string[]
  relationTypeFilter: Set<string>
  curationStatusFilter: Set<string>
  onRelationTypeToggle: (relationType: string, checked: boolean) => void
  onEnableAllRelationTypes: () => void
  onCurationStatusToggle: (status: string, checked: boolean) => void
  variant?: 'default' | 'embedded'
  className?: string
}

const RELATION_TYPE_INITIAL_BATCH = 80
const RELATION_TYPE_BATCH_SIZE = 120

export function KnowledgeGraphFiltersCard({
  availableRelationTypes,
  availableCurationStatuses,
  relationTypeFilter,
  curationStatusFilter,
  onRelationTypeToggle,
  onEnableAllRelationTypes,
  onCurationStatusToggle,
  variant = 'default',
  className,
}: KnowledgeGraphFiltersCardProps) {
  const [relationTypeSearchInput, setRelationTypeSearchInput] = useState('')
  const [visibleRelationTypeCount, setVisibleRelationTypeCount] = useState(RELATION_TYPE_INITIAL_BATCH)

  const deferredRelationTypeSearch = useDeferredValue(relationTypeSearchInput.trim().toUpperCase())
  const filteredRelationTypes = useMemo(() => {
    if (deferredRelationTypeSearch.length === 0) {
      return availableRelationTypes
    }
    return availableRelationTypes.filter((relationType) =>
      relationType.toUpperCase().includes(deferredRelationTypeSearch),
    )
  }, [availableRelationTypes, deferredRelationTypeSearch])

  useEffect(() => {
    setVisibleRelationTypeCount(RELATION_TYPE_INITIAL_BATCH)
  }, [deferredRelationTypeSearch, availableRelationTypes.length])

  const visibleRelationTypes = filteredRelationTypes.slice(0, visibleRelationTypeCount)
  const hasMoreRelationTypes = visibleRelationTypeCount < filteredRelationTypes.length

  const loadMoreRelationTypes = useCallback((): void => {
    if (!hasMoreRelationTypes) {
      return
    }
    setVisibleRelationTypeCount((current) =>
      Math.min(filteredRelationTypes.length, current + RELATION_TYPE_BATCH_SIZE),
    )
  }, [filteredRelationTypes.length, hasMoreRelationTypes])

  const onRelationTypeListScroll = useCallback(
    (event: UIEvent<HTMLDivElement>): void => {
      const element = event.currentTarget
      if (element.scrollTop + element.clientHeight < element.scrollHeight - 24) {
        return
      }
      loadMoreRelationTypes()
    },
    [loadMoreRelationTypes],
  )

  const selectedRelationCount = relationTypeFilter.size
  const selectedStatusCount = curationStatusFilter.size
  const body = (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">Local Filters</div>
        <div className="text-xs text-muted-foreground">
          {selectedRelationCount} relation types • {selectedStatusCount} statuses selected
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <div className="font-semibold uppercase text-muted-foreground">Relation Type</div>
            <div className="text-muted-foreground">
              {selectedRelationCount === 0
                ? `All enabled (${availableRelationTypes.length || 0})`
                : `${selectedRelationCount}/${availableRelationTypes.length || 0}`}
            </div>
          </div>
          <div className="space-y-2 rounded-lg border border-border/70 bg-background/65 p-2">
            <Input
              value={relationTypeSearchInput}
              onChange={(event) => setRelationTypeSearchInput(event.target.value)}
              placeholder="Search relation types..."
              className="h-8"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7"
                onClick={onEnableAllRelationTypes}
                disabled={relationTypeFilter.size === 0}
              >
                Enable all
              </Button>
              <div className="text-xs text-muted-foreground">
                Showing {visibleRelationTypes.length} of {filteredRelationTypes.length}
              </div>
            </div>
            <div
              className="grid max-h-44 gap-2 overflow-auto rounded-md border border-border/70 bg-background/70 p-2"
              onScroll={onRelationTypeListScroll}
            >
              {availableRelationTypes.length === 0 ? (
                <div className="text-xs text-muted-foreground">No relation types loaded yet.</div>
              ) : filteredRelationTypes.length === 0 ? (
                <div className="text-xs text-muted-foreground">
                  No relation types match your search.
                </div>
              ) : (
                visibleRelationTypes.map((relationType) => (
                  <div
                    key={relationType}
                    className="flex items-center gap-2 rounded-md border border-transparent px-2 py-1 transition-colors hover:border-border hover:bg-muted/55"
                  >
                    <Checkbox
                      id={`relation-filter-${relationType}`}
                      checked={relationTypeFilter.has(relationType)}
                      onCheckedChange={(checked) =>
                        onRelationTypeToggle(relationType, checked === true)
                      }
                    />
                    <Label htmlFor={`relation-filter-${relationType}`} className="font-mono text-xs">
                      {relationType}
                    </Label>
                  </div>
                ))
              )}
              {hasMoreRelationTypes ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="mx-auto mt-1 h-7 w-full text-xs"
                  onClick={loadMoreRelationTypes}
                >
                  Load more relation types
                </Button>
              ) : null}
            </div>
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <div className="font-semibold uppercase text-muted-foreground">Status</div>
            <div className="text-muted-foreground">
              {selectedStatusCount}/{availableCurationStatuses.length || 0}
            </div>
          </div>
          <div className="grid max-h-44 gap-2 overflow-auto rounded-lg border border-border/70 bg-background/65 p-2">
            {availableCurationStatuses.map((status) => (
              <div
                key={status}
                className="flex items-center gap-2 rounded-md border border-transparent px-2 py-1 transition-colors hover:border-border hover:bg-muted/55"
              >
                <Checkbox
                  id={`status-filter-${status}`}
                  checked={curationStatusFilter.has(status)}
                  onCheckedChange={(checked) => onCurationStatusToggle(status, checked === true)}
                />
                <Label htmlFor={`status-filter-${status}`} className="font-mono text-xs">
                  {status}
                </Label>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )

  if (variant === 'embedded') {
    return <div className={cn('py-1', className)}>{body}</div>
  }

  return (
    <Card className={cn('border-border/80 bg-gradient-to-br from-card to-muted/25', className)}>
      <CardContent className="py-4">
        {body}
      </CardContent>
    </Card>
  )
}
