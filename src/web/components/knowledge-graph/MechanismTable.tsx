'use client'

import { Pencil, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  EVIDENCE_TIER_LABELS,
  EVIDENCE_TIER_VARIANTS,
  MECHANISM_LIFECYCLE_LABELS,
  MECHANISM_LIFECYCLE_VARIANTS,
} from '@/lib/knowledge-graph/mechanism-constants'
import type { Mechanism } from '@/types/mechanisms'

interface MechanismTableProps {
  mechanisms: Mechanism[]
  editAction: (mechanism: Mechanism) => void
  deleteAction: (mechanism: Mechanism) => void
  canManage: boolean
}

export function MechanismTable({
  mechanisms,
  editAction,
  deleteAction,
  canManage,
}: MechanismTableProps) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mechanism</TableHead>
            <TableHead>Evidence</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>Phenotypes</TableHead>
            <TableHead>Domains</TableHead>
            <TableHead>Updated</TableHead>
            {canManage && <TableHead className="text-right">Actions</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {mechanisms.map((mechanism) => (
            <TableRow key={mechanism.id}>
              <TableCell>
                <div className="flex flex-col">
                  <span className="font-medium">{mechanism.name}</span>
                  {mechanism.description && (
                    <span className="text-xs text-muted-foreground">
                      {mechanism.description}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant={EVIDENCE_TIER_VARIANTS[mechanism.evidence_tier]}>
                  {EVIDENCE_TIER_LABELS[mechanism.evidence_tier]}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant={MECHANISM_LIFECYCLE_VARIANTS[mechanism.lifecycle_state]}>
                  {MECHANISM_LIFECYCLE_LABELS[mechanism.lifecycle_state]}
                </Badge>
              </TableCell>
              <TableCell>{mechanism.confidence_score.toFixed(2)}</TableCell>
              <TableCell>{mechanism.phenotype_count}</TableCell>
              <TableCell>{mechanism.protein_domains.length}</TableCell>
              <TableCell>{formatDate(mechanism.updated_at)}</TableCell>
              {canManage && (
                <TableCell>
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => editAction(mechanism)}
                    >
                      <Pencil className="mr-2 size-4" />
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive"
                      onClick={() => deleteAction(mechanism)}
                    >
                      <Trash2 className="mr-2 size-4" />
                      Delete
                    </Button>
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
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
