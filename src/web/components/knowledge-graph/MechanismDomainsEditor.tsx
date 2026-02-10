'use client'

import { Button } from '@/components/ui/button'
import { MechanismDomainRow } from '@/components/knowledge-graph/MechanismDomainRow'
import type { DomainFormState } from '@/lib/knowledge-graph/mechanism-form'
import type { ProteinDomainType } from '@/types/mechanisms'

interface MechanismDomainsEditorProps {
  domains: DomainFormState[]
  setDomainField: (
    index: number,
    field: keyof DomainFormState,
    value: string | ProteinDomainType,
  ) => void
  addDomain: () => void
  removeDomain: (index: number) => void
}

export function MechanismDomainsEditor({
  domains,
  setDomainField,
  addDomain,
  removeDomain,
}: MechanismDomainsEditorProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium">Protein domains</div>
          <p className="text-xs text-muted-foreground">
            Optional. Use when the mechanism is resolved to specific domains.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={addDomain}>
          Add domain
        </Button>
      </div>
      {domains.length === 0 ? (
        <div className="rounded border border-dashed px-4 py-6 text-sm text-muted-foreground">
          No domains added yet.
        </div>
      ) : (
        <div className="space-y-4">
          {domains.map((domain, index) => (
            <MechanismDomainRow
              key={`${domain.name}-${index}`}
              index={index}
              domain={domain}
              setDomainField={setDomainField}
              removeDomain={removeDomain}
            />
          ))}
        </div>
      )}
    </div>
  )
}
