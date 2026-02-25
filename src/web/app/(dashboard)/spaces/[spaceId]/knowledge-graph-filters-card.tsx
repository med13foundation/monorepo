import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

interface KnowledgeGraphFiltersCardProps {
  availableRelationTypes: string[]
  availableCurationStatuses: string[]
  relationTypeFilter: Set<string>
  curationStatusFilter: Set<string>
  onRelationTypeToggle: (relationType: string, checked: boolean) => void
  onCurationStatusToggle: (status: string, checked: boolean) => void
}

export function KnowledgeGraphFiltersCard({
  availableRelationTypes,
  availableCurationStatuses,
  relationTypeFilter,
  curationStatusFilter,
  onRelationTypeToggle,
  onCurationStatusToggle,
}: KnowledgeGraphFiltersCardProps) {
  const selectedRelationCount = relationTypeFilter.size
  const selectedStatusCount = curationStatusFilter.size

  return (
    <Card className="border-border/80 bg-gradient-to-br from-card to-muted/25">
      <CardContent className="space-y-4 py-4">
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
                {selectedRelationCount}/{availableRelationTypes.length || 0}
              </div>
            </div>
            <div className="grid max-h-44 gap-2 overflow-auto rounded-lg border border-border/70 bg-background/65 p-2">
              {availableRelationTypes.length === 0 ? (
                <div className="text-xs text-muted-foreground">No relation types loaded yet.</div>
              ) : (
                availableRelationTypes.map((relationType) => (
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
      </CardContent>
    </Card>
  )
}
