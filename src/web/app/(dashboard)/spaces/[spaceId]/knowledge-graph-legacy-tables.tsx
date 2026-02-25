import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { GraphModel } from '@/lib/graph/model'

interface KnowledgeGraphLegacyTablesProps {
  renderGraph: GraphModel
  showRelationTable: boolean
  showEntityTable: boolean
  onShowRelationTableChange: (open: boolean) => void
  onShowEntityTableChange: (open: boolean) => void
}

function confidenceValue(confidence: number): string {
  return `${(confidence * 100).toFixed(1)}%`
}

export function KnowledgeGraphLegacyTables({
  renderGraph,
  showRelationTable,
  showEntityTable,
  onShowRelationTableChange,
  onShowEntityTableChange,
}: KnowledgeGraphLegacyTablesProps) {
  return (
    <>
      <Collapsible open={showRelationTable} onOpenChange={onShowRelationTableChange}>
        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">Relations Table (Legacy)</div>
              <CollapsibleTrigger asChild>
                <Button variant="outline" size="sm">
                  {showRelationTable ? 'Hide' : 'Show'}
                </Button>
              </CollapsibleTrigger>
            </div>
            <CollapsibleContent>
              {renderGraph.edges.length === 0 ? (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  No relations in the current view.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Target</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Confidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {renderGraph.edges.slice(0, 75).map((edge) => (
                      <TableRow key={edge.id}>
                        <TableCell className="font-mono text-xs">{edge.relationType}</TableCell>
                        <TableCell className="font-mono text-xs">{edge.sourceId}</TableCell>
                        <TableCell className="font-mono text-xs">{edge.targetId}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{edge.curationStatus}</Badge>
                        </TableCell>
                        <TableCell className="text-xs">{confidenceValue(edge.confidence)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CollapsibleContent>
          </CardContent>
        </Card>
      </Collapsible>

      <Collapsible open={showEntityTable} onOpenChange={onShowEntityTableChange}>
        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">Entities Table (Legacy)</div>
              <CollapsibleTrigger asChild>
                <Button variant="outline" size="sm">
                  {showEntityTable ? 'Hide' : 'Show'}
                </Button>
              </CollapsibleTrigger>
            </div>
            <CollapsibleContent>
              {renderGraph.nodes.length === 0 ? (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  No entities in the current view.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Label</TableHead>
                      <TableHead>ID</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {renderGraph.nodes.slice(0, 75).map((node) => (
                      <TableRow key={node.id}>
                        <TableCell>
                          <Badge variant="secondary">{node.entityType}</Badge>
                        </TableCell>
                        <TableCell className="text-xs">{node.label}</TableCell>
                        <TableCell className="font-mono text-xs">{node.id}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CollapsibleContent>
          </CardContent>
        </Card>
      </Collapsible>
    </>
  )
}
