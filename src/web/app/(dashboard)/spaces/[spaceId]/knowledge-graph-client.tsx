'use client'

import Link from 'next/link'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Waypoints } from 'lucide-react'
import type { KernelGraphExportResponse } from '@/types/kernel'

interface KnowledgeGraphClientProps {
  spaceId: string
  graph: KernelGraphExportResponse | null
  graphError?: string | null
}

export default function KnowledgeGraphClient({
  spaceId,
  graph,
  graphError,
}: KnowledgeGraphClientProps) {
  const nodes = graph?.nodes ?? []
  const edges = graph?.edges ?? []

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
