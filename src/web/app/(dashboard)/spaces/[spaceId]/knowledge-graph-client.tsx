'use client'

import Link from 'next/link'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Waypoints } from 'lucide-react'
import type { GraphSearchResponse, KernelGraphExportResponse } from '@/types/kernel'

interface KnowledgeGraphClientProps {
  spaceId: string
  graph: KernelGraphExportResponse | null
  graphError?: string | null
  graphSearch?: GraphSearchResponse | null
  graphSearchError?: string | null
  initialQuestion?: string
  initialTopK?: number
  initialMaxDepth?: number
  initialForceAgent?: boolean
}

export default function KnowledgeGraphClient({
  spaceId,
  graph,
  graphError,
  graphSearch,
  graphSearchError,
  initialQuestion = '',
  initialTopK = 25,
  initialMaxDepth = 2,
  initialForceAgent = false,
}: KnowledgeGraphClientProps) {
  const nodes = graph?.nodes ?? []
  const edges = graph?.edges ?? []
  const graphSearchResults = graphSearch?.results ?? []

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Knowledge Graph"
        description="Explore the kernel graph (entities + relations) for this research space."
        actions={
          <Button asChild variant="outline">
            <Link href={`/spaces/${spaceId}/curation`}>Curation</Link>
          </Button>
        }
      >
        {graphError ? (
          <Card>
            <CardContent className="py-12 text-center text-destructive">
              {graphError}
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            <Card>
              <CardContent className="py-4">
                <form method="get" className="space-y-4">
                  <div className="grid gap-3 lg:grid-cols-4">
                    <div className="space-y-1 lg:col-span-2">
                      <Label htmlFor="graph-query">Graph Search Query</Label>
                      <Input
                        id="graph-query"
                        name="q"
                        defaultValue={initialQuestion}
                        placeholder="What evidence links MED13 to cardiac phenotypes?"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="graph-max-depth">Max Depth</Label>
                      <Input
                        id="graph-max-depth"
                        name="max_depth"
                        type="number"
                        min={1}
                        max={4}
                        defaultValue={initialMaxDepth}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="graph-top-k">Top K</Label>
                      <Input
                        id="graph-top-k"
                        name="top_k"
                        type="number"
                        min={1}
                        max={100}
                        defaultValue={initialTopK}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      id="graph-force-agent"
                      type="checkbox"
                      name="force_agent"
                      value="1"
                      defaultChecked={initialForceAgent}
                    />
                    <Label htmlFor="graph-force-agent">Force agent fallback</Label>
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit">Run Graph Search</Button>
                    {initialQuestion ? (
                      <Button asChild variant="outline">
                        <Link href={`/spaces/${spaceId}/knowledge-graph`}>
                          Clear
                        </Link>
                      </Button>
                    ) : null}
                  </div>
                </form>
              </CardContent>
            </Card>

            {initialQuestion ? (
              <Card>
                <CardContent className="py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium">Search Results</div>
                      <div className="text-xs text-muted-foreground">
                        Query: {initialQuestion}
                      </div>
                    </div>
                    {graphSearch ? (
                      <Badge variant="outline">
                        Path: {graphSearch.executed_path}
                      </Badge>
                    ) : null}
                  </div>
                  {graphSearchError ? (
                    <div className="text-sm text-destructive">{graphSearchError}</div>
                  ) : graphSearchResults.length === 0 ? (
                    <div className="text-sm text-muted-foreground">
                      No matching entities found.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Entity</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Relevance</TableHead>
                          <TableHead>Support</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {graphSearchResults.slice(0, 25).map((result) => (
                          <TableRow key={result.entity_id}>
                            <TableCell>
                              <div>{result.display_label ?? '—'}</div>
                              <div className="font-mono text-xs text-muted-foreground">
                                {result.entity_id}
                              </div>
                            </TableCell>
                            <TableCell>
                              <Badge variant="secondary">{result.entity_type}</Badge>
                            </TableCell>
                            <TableCell>
                              {(result.relevance_score * 100).toFixed(1)}%
                            </TableCell>
                            <TableCell className="text-xs">
                              <div>{result.support_summary}</div>
                              <div className="text-muted-foreground">
                                Evidence links: {result.evidence_chain.length}
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardContent className="py-6">
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Entities</div>
                      <div className="text-2xl font-semibold">{nodes.length}</div>
                    </div>
                    <Waypoints className="size-8 text-muted-foreground" />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-6">
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Relations</div>
                      <div className="text-2xl font-semibold">{edges.length}</div>
                    </div>
                    <Waypoints className="size-8 text-muted-foreground" />
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardContent className="py-4">
                {edges.length === 0 ? (
                  <div className="py-10 text-center text-muted-foreground">
                    No relations found.
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
                      {edges.slice(0, 50).map((edge) => (
                        <TableRow key={edge.id}>
                          <TableCell className="font-mono text-xs">{edge.relation_type}</TableCell>
                          <TableCell className="font-mono text-xs">{edge.source_id}</TableCell>
                          <TableCell className="font-mono text-xs">{edge.target_id}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{edge.curation_status}</Badge>
                          </TableCell>
                          <TableCell className="text-xs">{edge.confidence}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {edges.length > 50 && (
                  <div className="mt-3 text-xs text-muted-foreground">
                    Showing first 50 relations.
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent className="py-4">
                {nodes.length === 0 ? (
                  <div className="py-10 text-center text-muted-foreground">
                    No entities found.
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
                      {nodes.slice(0, 50).map((node) => (
                        <TableRow key={node.id}>
                          <TableCell>
                            <Badge variant="secondary">{node.entity_type}</Badge>
                          </TableCell>
                          <TableCell className="text-xs">{node.display_label ?? '—'}</TableCell>
                          <TableCell className="font-mono text-xs">{node.id}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {nodes.length > 50 && (
                  <div className="mt-3 text-xs text-muted-foreground">
                    Showing first 50 entities.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </DashboardSection>
    </div>
  )
}
