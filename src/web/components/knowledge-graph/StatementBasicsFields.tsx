'use client'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface StatementBasicsFieldsProps {
  title: string
  source: string
  summary: string
  setTitle: (value: string) => void
  setSource: (value: string) => void
  setSummary: (value: string) => void
}

export function StatementBasicsFields({
  title,
  source,
  summary,
  setTitle,
  setSource,
  setSummary,
}: StatementBasicsFieldsProps) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="statement-title">Statement title *</Label>
          <Input
            id="statement-title"
            value={title}
            placeholder="e.g., MED13 disruption impairs mediator stability"
            onChange={(event) => setTitle(event.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="statement-source">Source</Label>
          <Input
            id="statement-source"
            value={source}
            placeholder="manual_curation"
            onChange={(event) => setSource(event.target.value)}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="statement-summary">Summary *</Label>
        <Textarea
          id="statement-summary"
          value={summary}
          placeholder="Describe the mechanistic explanation and supporting evidence."
          onChange={(event) => setSummary(event.target.value)}
          required
        />
        <p className="text-xs text-muted-foreground">
          Required. Statements are the hypothesis workspace, not canonical knowledge.
        </p>
      </div>
    </>
  )
}
