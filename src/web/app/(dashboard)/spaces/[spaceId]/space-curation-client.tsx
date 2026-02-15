'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { updateKernelRelationStatusAction } from '@/app/actions/kernel-relations'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { KernelRelationListResponse, KernelRelationResponse } from '@/types/kernel'

interface SpaceCurationClientProps {
  spaceId: string
  relations: KernelRelationListResponse | null
  relationsError?: string | null
  canCurate: boolean
  filters: {
    relationType: string
    curationStatus: string
    offset: number
    limit: number
  }
}

const ALL_CURATION_STATUSES = '__all__'

function truncate(value: string, maxLen: number): string {
  if (value.length <= maxLen) {
    return value
  }
  return value.slice(0, maxLen - 1) + '…'
}

export default function SpaceCurationClient({
  spaceId,
  relations,
  relationsError,
  canCurate,
  filters,
}: SpaceCurationClientProps) {
  const router = useRouter()
  const [relationType, setRelationType] = useState(filters.relationType)
  const [curationStatus, setCurationStatus] = useState(
    filters.curationStatus || ALL_CURATION_STATUSES,
  )
  const [pendingRelationId, setPendingRelationId] = useState<string | null>(null)

  const rows = useMemo(() => relations?.relations ?? [], [relations?.relations])

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
                if (relTrim) params.set('relation_type', relTrim)
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
          <Card>
            <CardContent className="grid gap-4 py-6 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="relation_type">Relation Type (optional)</Label>
                <Input
                  id="relation_type"
                  value={relationType}
                  onChange={(e) => setRelationType(e.target.value)}
                  placeholder="e.g. ASSOCIATED_WITH"
                />
              </div>
              <div className="space-y-2">
                <Label>Curation Status (optional)</Label>
                <Select value={curationStatus} onValueChange={(value) => setCurationStatus(value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="All statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_CURATION_STATUSES}>All</SelectItem>
                    {(['DRAFT', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RETRACTED'] as const).map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
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
            <Card>
              <CardContent className="py-2">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Target</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Evidence</TableHead>
                      {canCurate && <TableHead className="text-right">Actions</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((rel) => (
                      <TableRow key={rel.id}>
                        <TableCell className="font-mono text-xs">{rel.relation_type}</TableCell>
                        <TableCell className="font-mono text-xs">{rel.source_id}</TableCell>
                        <TableCell className="font-mono text-xs">{rel.target_id}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{rel.curation_status}</Badge>
                        </TableCell>
                        <TableCell className="text-xs">{rel.confidence}</TableCell>
                        <TableCell className="text-xs">
                          {rel.evidence_summary ? truncate(rel.evidence_summary, 80) : '—'}
                        </TableCell>
                        {canCurate && (
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={pendingRelationId === rel.id}
                                onClick={() => updateStatus(rel, 'UNDER_REVIEW')}
                              >
                                Review
                              </Button>
                              <Button
                                size="sm"
                                disabled={pendingRelationId === rel.id}
                                onClick={() => updateStatus(rel, 'APPROVED')}
                              >
                                Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                disabled={pendingRelationId === rel.id}
                                onClick={() => updateStatus(rel, 'REJECTED')}
                              >
                                Reject
                              </Button>
                            </div>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      </DashboardSection>
    </div>
  )
}
