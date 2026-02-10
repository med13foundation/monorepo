'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { MechanismDomainsEditor } from '@/components/knowledge-graph/MechanismDomainsEditor'
import { StatementBasicsFields } from '@/components/knowledge-graph/StatementBasicsFields'
import { StatementEvidenceFields } from '@/components/knowledge-graph/StatementEvidenceFields'
import {
  buildDomainState,
  normalizeDomains,
} from '@/lib/knowledge-graph/mechanism-form'
import {
  buildStatementFormState,
  type StatementFormState,
} from '@/lib/knowledge-graph/statement-form'
import type { ProteinDomainType } from '@/types/mechanisms'
import type {
  Statement,
  StatementCreateRequest,
  StatementUpdateRequest,
} from '@/types/statements'

interface StatementEditorDialogProps {
  open: boolean
  setOpen: (open: boolean) => void
  statement: Statement | null
  spaceId: string
  submitAction: (payload: StatementCreateRequest | StatementUpdateRequest) => Promise<void>
  isSubmitting: boolean
}

export function StatementEditorDialog({
  open,
  setOpen,
  statement,
  spaceId,
  submitAction,
  isSubmitting,
}: StatementEditorDialogProps) {
  const [form, setForm] = useState<StatementFormState>(
    buildStatementFormState(statement ?? undefined),
  )

  useEffect(() => {
    if (open) {
      setForm(buildStatementFormState(statement ?? undefined))
    }
  }, [open, statement])

  const setField = <K extends keyof StatementFormState>(
    field: K,
    value: StatementFormState[K],
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const setDomainField = (
    index: number,
    field: keyof StatementFormState['domains'][number],
    value: string | ProteinDomainType,
  ) => {
    setForm((prev) => {
      const next = [...prev.domains]
      next[index] = { ...next[index], [field]: value }
      return { ...prev, domains: next }
    })
  }

  const addDomain = () => {
    setForm((prev) => ({ ...prev, domains: [...prev.domains, buildDomainState()] }))
  }

  const removeDomain = (index: number) => {
    setForm((prev) => {
      const next = [...prev.domains]
      next.splice(index, 1)
      return { ...prev, domains: next }
    })
  }

  const submitForm = async () => {
    const confidence = Number.parseFloat(form.confidence_score)
    if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
      toast.error('Confidence score must be between 0 and 1')
      return
    }
    if (!form.title.trim()) {
      toast.error('Statement title is required')
      return
    }
    if (!form.summary.trim()) {
      toast.error('Statement summary is required')
      return
    }

    const payload = {
      title: form.title.trim(),
      summary: form.summary.trim(),
      evidence_tier: form.evidence_tier,
      confidence_score: confidence,
      status: form.status,
      source: form.source.trim() || 'manual_curation',
      protein_domains: normalizeDomains(form.domains),
      phenotype_ids: form.phenotype_ids,
    }

    if (statement) {
      const updatePayload: StatementUpdateRequest = {
        title: payload.title,
        summary: payload.summary,
        evidence_tier: payload.evidence_tier,
        confidence_score: payload.confidence_score,
        status: payload.status,
        source: payload.source,
        protein_domains: payload.protein_domains,
        phenotype_ids: payload.phenotype_ids,
      }
      await submitAction(updatePayload)
    } else {
      await submitAction(payload)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {statement ? 'Edit statement of understanding' : 'Create statement of understanding'}
          </DialogTitle>
          <DialogDescription>
            Capture evolving hypotheses before promoting them into canonical mechanisms.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <StatementBasicsFields
            title={form.title}
            source={form.source}
            summary={form.summary}
            setTitle={(value) => setField('title', value)}
            setSource={(value) => setField('source', value)}
            setSummary={(value) => setField('summary', value)}
          />
          <StatementEvidenceFields
            evidenceTier={form.evidence_tier}
            confidenceScore={form.confidence_score}
            phenotypeIds={form.phenotype_ids}
            status={form.status}
            setEvidenceTier={(value) => setField('evidence_tier', value)}
            setConfidenceScore={(value) => setField('confidence_score', value)}
            setPhenotypeIds={(value) => setField('phenotype_ids', value)}
            setStatus={(value) => setField('status', value)}
            spaceId={spaceId}
          />
          <MechanismDomainsEditor
            domains={form.domains}
            setDomainField={setDomainField}
            addDomain={addDomain}
            removeDomain={removeDomain}
          />
        </div>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={submitForm} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Saving…
              </>
            ) : (
              'Save Statement'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
