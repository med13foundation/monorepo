import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface KnowledgeGraphQueryCardProps {
  questionInput: string
  topKInput: string
  maxDepthInput: string
  forceAgent: boolean
  minDepth: number
  maxDepth: number
  minTopK: number
  maxTopK: number
  isLoading: boolean
  onQuestionInputChange: (value: string) => void
  onTopKInputChange: (value: string) => void
  onMaxDepthInputChange: (value: string) => void
  onForceAgentChange: (checked: boolean) => void
  onSearch: () => Promise<void>
  onLoadStarter: () => void
  onResetFilters: () => void
}

export function KnowledgeGraphQueryCard({
  questionInput,
  topKInput,
  maxDepthInput,
  forceAgent,
  minDepth,
  maxDepth,
  minTopK,
  maxTopK,
  isLoading,
  onQuestionInputChange,
  onTopKInputChange,
  onMaxDepthInputChange,
  onForceAgentChange,
  onSearch,
  onLoadStarter,
  onResetFilters,
}: KnowledgeGraphQueryCardProps) {
  return (
    <Card>
      <CardContent className="py-4">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            void onSearch()
          }}
        >
          <div className="grid gap-3 lg:grid-cols-4">
            <div className="space-y-1 lg:col-span-2">
              <Label htmlFor="graph-query">Graph Search Query</Label>
              <Input
                id="graph-query"
                value={questionInput}
                onChange={(event) => onQuestionInputChange(event.target.value)}
                placeholder="What evidence links MED13 to cardiac phenotypes?"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="graph-max-depth">Max Depth</Label>
              <Input
                id="graph-max-depth"
                type="number"
                min={minDepth}
                max={maxDepth}
                value={maxDepthInput}
                onChange={(event) => onMaxDepthInputChange(event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="graph-top-k">Top K</Label>
              <Input
                id="graph-top-k"
                type="number"
                min={minTopK}
                max={maxTopK}
                value={topKInput}
                onChange={(event) => onTopKInputChange(event.target.value)}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="graph-force-agent"
              checked={forceAgent}
              onCheckedChange={(checked) => onForceAgentChange(checked === true)}
            />
            <Label htmlFor="graph-force-agent">Force agent fallback</Label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={isLoading}>
              {isLoading ? 'Running…' : 'Run Graph Search'}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={isLoading}
              onClick={onLoadStarter}
            >
              Load Starter Subgraph
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={isLoading}
              onClick={onResetFilters}
            >
              Reset Filters
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
