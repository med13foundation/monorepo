'use client'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DOMAIN_TYPE_OPTIONS } from '@/lib/knowledge-graph/mechanism-constants'
import type { DomainFormState } from '@/lib/knowledge-graph/mechanism-form'
import type { ProteinDomainType } from '@/types/mechanisms'

interface MechanismDomainRowProps {
  index: number
  domain: DomainFormState
  setDomainField: (
    index: number,
    field: keyof DomainFormState,
    value: string | ProteinDomainType,
  ) => void
  removeDomain: (index: number) => void
}

export function MechanismDomainRow({
  index,
  domain,
  setDomainField,
  removeDomain,
}: MechanismDomainRowProps) {
  return (
    <div className="space-y-4 rounded-lg border border-border/70 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Domain {index + 1}</div>
        <Button variant="ghost" size="sm" onClick={() => removeDomain(index)}>
          Remove
        </Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={`domain-name-${index}`}>Name</Label>
          <Input
            id={`domain-name-${index}`}
            value={domain.name}
            onChange={(event) => setDomainField(index, 'name', event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`domain-source-${index}`}>Source ID</Label>
          <Input
            id={`domain-source-${index}`}
            value={domain.source_id}
            onChange={(event) => setDomainField(index, 'source_id', event.target.value)}
          />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor={`domain-start-${index}`}>Start</Label>
          <Input
            id={`domain-start-${index}`}
            type="number"
            min={1}
            value={domain.start_residue}
            onChange={(event) => setDomainField(index, 'start_residue', event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`domain-end-${index}`}>End</Label>
          <Input
            id={`domain-end-${index}`}
            type="number"
            min={1}
            value={domain.end_residue}
            onChange={(event) => setDomainField(index, 'end_residue', event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`domain-type-${index}`}>Type</Label>
          <Select
            value={domain.domain_type}
            onValueChange={(value) =>
              setDomainField(index, 'domain_type', value as ProteinDomainType)
            }
          >
            <SelectTrigger id={`domain-type-${index}`}>
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              {DOMAIN_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor={`domain-description-${index}`}>Description</Label>
        <Textarea
          id={`domain-description-${index}`}
          value={domain.description}
          onChange={(event) => setDomainField(index, 'description', event.target.value)}
        />
      </div>
    </div>
  )
}
