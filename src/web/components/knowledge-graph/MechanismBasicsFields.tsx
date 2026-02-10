'use client'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface MechanismBasicsFieldsProps {
  name: string
  source: string
  description: string
  setName: (value: string) => void
  setSource: (value: string) => void
  setDescription: (value: string) => void
}

export function MechanismBasicsFields({
  name,
  source,
  description,
  setName,
  setSource,
  setDescription,
}: MechanismBasicsFieldsProps) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="mechanism-name">Mechanism name *</Label>
          <Input
            id="mechanism-name"
            value={name}
            placeholder="e.g., Mediator complex disruption"
            onChange={(event) => setName(event.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="mechanism-source">Source</Label>
          <Input
            id="mechanism-source"
            value={source}
            placeholder="manual_curation"
            onChange={(event) => setSource(event.target.value)}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="mechanism-description">Description *</Label>
        <Textarea
          id="mechanism-description"
          value={description}
          placeholder="Plain language explanation of the biological mechanism."
          onChange={(event) => setDescription(event.target.value)}
          required
        />
        <p className="text-xs text-muted-foreground">
          Required. Mechanisms are canonical explanations, not early hypotheses.
        </p>
      </div>
    </>
  )
}
