'use client'

import { ArrowUpRight, Pencil, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  EVIDENCE_TIER_LABELS,
  EVIDENCE_TIER_VARIANTS,
} from '@/lib/knowledge-graph/mechanism-constants'
import {
  STATEMENT_STATUS_LABELS,
  STATEMENT_STATUS_VARIANTS,
} from '@/lib/knowledge-graph/statement-constants'
import type { EvidenceTier } from '@/types/mechanisms'
import type { Statement } from '@/types/statements'

const PROMOTABLE_EVIDENCE: EvidenceTier[] = ['moderate', 'strong', 'definitive']

interface StatementTableProps {
  statements: Statement[]
  editAction: (statement: Statement) => void
  deleteAction: (statement: Statement) => void
  promoteAction: (statement: Statement) => void
  canManage: boolean
  canPromote: boolean
}

export function StatementTable({
  statements,
  editAction,
  deleteAction,
  promoteAction,
  canManage,
  canPromote,
}: StatementTableProps) {
  const showActions = canManage || canPromote

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Statement</TableHead>
            <TableHead>Evidence</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>Phenotypes</TableHead>
            <TableHead>Domains</TableHead>
            <TableHead>Updated</TableHead>
            {showActions && <TableHead className="text-right">Actions</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {statements.map((statement) => {
            const promotableEvidence = PROMOTABLE_EVIDENCE.includes(statement.evidence_tier)
            const promotableStatus = statement.status === 'well_supported'
            const promotablePhenotypes = statement.phenotype_ids.length > 0
            const isPromoted = Boolean(statement.promoted_mechanism_id)
            const canPromoteRow =
              canPromote && promotableEvidence && promotableStatus && promotablePhenotypes && !isPromoted

            return (
              <TableRow key={statement.id}>
                <TableCell>
                  <div className="flex flex-col">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{statement.title}</span>
                      {isPromoted && <Badge variant="secondary">Promoted</Badge>}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {statement.summary}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={EVIDENCE_TIER_VARIANTS[statement.evidence_tier]}>
                    {EVIDENCE_TIER_LABELS[statement.evidence_tier]}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={STATEMENT_STATUS_VARIANTS[statement.status]}>
                    {STATEMENT_STATUS_LABELS[statement.status]}
                  </Badge>
                </TableCell>
                <TableCell>{statement.confidence_score.toFixed(2)}</TableCell>
                <TableCell>{statement.phenotype_count}</TableCell>
                <TableCell>{statement.protein_domains.length}</TableCell>
                <TableCell>{formatDate(statement.updated_at)}</TableCell>
                {showActions && (
                  <TableCell>
                    <div className="flex items-center justify-end gap-2">
                      {canManage && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => editAction(statement)}
                          >
                            <Pencil className="mr-2 size-4" />
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => deleteAction(statement)}
                          >
                            <Trash2 className="mr-2 size-4" />
                            Delete
                          </Button>
                        </>
                      )}
                      {canPromote && (
                        <Button
                          variant="default"
                          size="sm"
                          disabled={!canPromoteRow}
                          onClick={() => promoteAction(statement)}
                        >
                          <ArrowUpRight className="mr-2 size-4" />
                          {isPromoted ? 'Promoted' : 'Promote'}
                        </Button>
                      )}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

function formatDate(value: string | null) {
  if (!value) {
    return '—'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleDateString()
}
