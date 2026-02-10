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
import { MechanismBasicsFields } from '@/components/knowledge-graph/MechanismBasicsFields'
import { MechanismEvidenceFields } from '@/components/knowledge-graph/MechanismEvidenceFields'
import { MechanismDomainsEditor } from '@/components/knowledge-graph/MechanismDomainsEditor'
import {
  buildDomainState,
  buildFormState,
  normalizeDomains,
  type MechanismFormState,
} from '@/lib/knowledge-graph/mechanism-form'
import type {
  Mechanism,
  MechanismCreateRequest,
  MechanismUpdateRequest,
  ProteinDomainType,
} from '@/types/mechanisms'

interface MechanismEditorDialogProps {
  open: boolean
  setOpen: (open: boolean) => void
  mechanism: Mechanism | null
  spaceId: string
  submitAction: (payload: MechanismCreateRequest | MechanismUpdateRequest) => Promise<void>
  isSubmitting: boolean
}

export function MechanismEditorDialog({
  open,
  setOpen,
  mechanism,
  spaceId,
  submitAction,
  isSubmitting,
}: MechanismEditorDialogProps) {
  const [form, setForm] = useState<MechanismFormState>(buildFormState(mechanism ?? undefined))

  useEffect(() => {
    if (open) {
      setForm(buildFormState(mechanism ?? undefined))
    }
  }, [open, mechanism])

  const setField = <K extends keyof MechanismFormState>(
    field: K,
    value: MechanismFormState[K],
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const setDomainField = (
    index: number,
    field: keyof MechanismFormState['domains'][number],
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
    if (!form.name.trim()) {
      toast.error('Mechanism name is required')
      return
    }
    if (!form.description.trim()) {
      toast.error('Mechanism description is required')
      return
    }

    if (form.phenotype_ids.length === 0) {
      toast.error('At least one phenotype ID is required')
      return
    }

    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      evidence_tier: form.evidence_tier,
      confidence_score: confidence,
      source: form.source.trim() || 'manual_curation',
      lifecycle_state: form.lifecycle_state,
      protein_domains: normalizeDomains(form.domains),
      phenotype_ids: form.phenotype_ids,
    }

    if (mechanism) {
      const updatePayload: MechanismUpdateRequest = {
        name: payload.name,
        description: payload.description,
        evidence_tier: payload.evidence_tier,
        confidence_score: payload.confidence_score,
        source: payload.source,
        lifecycle_state: payload.lifecycle_state,
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
            {mechanism ? 'Edit canonical mechanism' : 'Create canonical mechanism'}
          </DialogTitle>
          <DialogDescription>
            Promote well-supported explanations into reusable, reviewable knowledge.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <MechanismBasicsFields
            name={form.name}
            source={form.source}
            description={form.description}
            setName={(value) => setField('name', value)}
            setSource={(value) => setField('source', value)}
            setDescription={(value) => setField('description', value)}
          />
          <MechanismEvidenceFields
            evidenceTier={form.evidence_tier}
            confidenceScore={form.confidence_score}
            phenotypeIds={form.phenotype_ids}
            lifecycleState={form.lifecycle_state}
            setEvidenceTier={(value) => setField('evidence_tier', value)}
            setConfidenceScore={(value) => setField('confidence_score', value)}
            setPhenotypeIds={(value) => setField('phenotype_ids', value)}
            setLifecycleState={(value) => setField('lifecycle_state', value)}
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
              'Save Mechanism'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
