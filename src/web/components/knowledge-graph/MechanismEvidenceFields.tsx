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
import {
  EVIDENCE_TIER_LABELS,
  MECHANISM_LIFECYCLE_LABELS,
} from '@/lib/knowledge-graph/mechanism-constants'
import type { EvidenceTier, MechanismLifecycleState } from '@/types/mechanisms'

interface MechanismEvidenceFieldsProps {
  spaceId: string
  evidenceTier: EvidenceTier
  confidenceScore: string
  phenotypeIds: number[]
  lifecycleState: MechanismLifecycleState
  setEvidenceTier: (value: EvidenceTier) => void
  setConfidenceScore: (value: string) => void
  setPhenotypeIds: (value: number[]) => void
  setLifecycleState: (value: MechanismLifecycleState) => void
}

export function MechanismEvidenceFields({
  spaceId,
  evidenceTier,
  confidenceScore,
  phenotypeIds,
  lifecycleState,
  setEvidenceTier,
  setConfidenceScore,
  setPhenotypeIds,
  setLifecycleState,
}: MechanismEvidenceFieldsProps) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <Label htmlFor="mechanism-evidence">Evidence tier</Label>
          <Select
            value={evidenceTier}
            onValueChange={(value) => setEvidenceTier(value as EvidenceTier)}
          >
            <SelectTrigger id="mechanism-evidence">
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
            Recommended: Moderate or higher before promotion.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="mechanism-confidence">Confidence score</Label>
          <Input
            id="mechanism-confidence"
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={confidenceScore}
            onChange={(event) => setConfidenceScore(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="mechanism-lifecycle">Lifecycle state</Label>
          <Select
            value={lifecycleState}
            onValueChange={(value) => setLifecycleState(value as MechanismLifecycleState)}
          >
            <SelectTrigger id="mechanism-lifecycle">
              <SelectValue placeholder="Select state" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(MECHANISM_LIFECYCLE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <PhenotypeMultiSelect
        spaceId={spaceId}
        label="Linked phenotypes"
        description="Required. Search by HPO ID, term, synonym, or definition."
        selectedIds={phenotypeIds}
        onChange={setPhenotypeIds}
      />
    </>
  )
}
