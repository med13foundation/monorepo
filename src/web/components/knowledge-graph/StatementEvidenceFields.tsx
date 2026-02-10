'use client'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PhenotypeMultiSelect } from '@/components/knowledge-graph/PhenotypeMultiSelect'
import { EVIDENCE_TIER_LABELS } from '@/lib/knowledge-graph/mechanism-constants'
import { STATEMENT_STATUS_LABELS } from '@/lib/knowledge-graph/statement-constants'
import type { EvidenceTier } from '@/types/mechanisms'
import type { StatementStatus } from '@/types/statements'

interface StatementEvidenceFieldsProps {
  spaceId: string
  evidenceTier: EvidenceTier
  confidenceScore: string
  phenotypeIds: number[]
  status: StatementStatus
  setEvidenceTier: (value: EvidenceTier) => void
  setConfidenceScore: (value: string) => void
  setPhenotypeIds: (value: number[]) => void
  setStatus: (value: StatementStatus) => void
}

export function StatementEvidenceFields({
  spaceId,
  evidenceTier,
  confidenceScore,
  phenotypeIds,
  status,
  setEvidenceTier,
  setConfidenceScore,
  setPhenotypeIds,
  setStatus,
}: StatementEvidenceFieldsProps) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <Label htmlFor="statement-evidence">Evidence tier</Label>
          <Select
            value={evidenceTier}
            onValueChange={(value) => setEvidenceTier(value as EvidenceTier)}
          >
            <SelectTrigger id="statement-evidence">
              <SelectValue placeholder="Select tier" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(EVIDENCE_TIER_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Promotion requires Moderate or higher evidence.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="statement-confidence">Confidence score</Label>
          <Input
            id="statement-confidence"
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={confidenceScore}
            onChange={(event) => setConfidenceScore(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="statement-status">Status</Label>
          <Select
            value={status}
            onValueChange={(value) => setStatus(value as StatementStatus)}
          >
            <SelectTrigger id="statement-status">
              <SelectValue placeholder="Select status" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(STATEMENT_STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Set to Well supported before promotion.
          </p>
        </div>
      </div>
      <PhenotypeMultiSelect
        spaceId={spaceId}
        label="Linked phenotypes"
        description="Required for promotion. Search by HPO ID, term, synonym, or definition."
        selectedIds={phenotypeIds}
        onChange={setPhenotypeIds}
      />
    </>
  )
}
