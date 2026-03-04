'use client'

import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  createUserHypothesisAction,
  listHypothesisClaimsAction,
} from '@/app/actions/kernel-hybrid-duplicates'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { RelationClaimResponse } from '@/types/kernel'

interface CurationHypothesesCardProps {
  spaceId: string
  canEdit: boolean
}

export default function CurationHypothesesCard({ spaceId, canEdit }: CurationHypothesesCardProps) {
  const [hypotheses, setHypotheses] = useState<RelationClaimResponse[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [statement, setStatement] = useState('')
  const [rationale, setRationale] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadHypotheses = useCallback(async (): Promise<void> => {
    setIsLoading(true)
    const result = await listHypothesisClaimsAction(spaceId)
    setIsLoading(false)
    if (!result.success) {
      setError(result.error)
      setHypotheses([])
      return
    }
    setError(null)
    setHypotheses(result.data)
  }, [spaceId])

  useEffect(() => {
    void loadHypotheses()
  }, [loadHypotheses])

  async function submitHypothesis(): Promise<void> {
    if (!canEdit) {
      toast.error('You do not have permission to create hypotheses.')
      return
    }
    setIsSubmitting(true)
    const result = await createUserHypothesisAction(spaceId, statement, rationale)
    setIsSubmitting(false)
    if (!result.success) {
      toast.error(result.error)
      return
    }
    toast.success(`Hypothesis logged in decision ledger (${result.data.decisionId.slice(0, 8)}...).`)
    setStatement('')
    setRationale('')
    void loadHypotheses()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Hypotheses</CardTitle>
        <CardDescription>
          Capture and review hypotheses directly in data curation, alongside extraction-claim triage.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="curation-hypothesis-statement">Hypothesis statement</Label>
            <Input
              id="curation-hypothesis-statement"
              value={statement}
              onChange={(event) => setStatement(event.target.value)}
              placeholder="e.g. Gene X modulates pathway Y under condition Z"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="curation-hypothesis-rationale">Rationale</Label>
            <Input
              id="curation-hypothesis-rationale"
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Why this should be investigated now"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void submitHypothesis()} disabled={!canEdit || isSubmitting}>
            Generate hypothesis
          </Button>
          <Button variant="outline" onClick={() => void loadHypotheses()} disabled={isLoading}>
            Refresh hypotheses
          </Button>
        </div>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        {hypotheses.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hypothesis claims available in this space yet.</p>
        ) : (
          <div className="space-y-3">
            {hypotheses.map((claim) => (
              <Card key={claim.id} className="border-border/70">
                <CardContent className="space-y-2 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">Hypothesis</Badge>
                    <Badge variant="outline">{claim.claim_status}</Badge>
                    <Badge variant="outline">{claim.validation_state}</Badge>
                  </div>
                  <p className="text-sm font-medium">
                    {(claim.source_label || claim.source_type) + ' -> ' + claim.relation_type + ' -> '}
                    {claim.target_label || claim.target_type}
                  </p>
                  {claim.claim_text ? (
                    <p className="text-sm text-muted-foreground">{claim.claim_text}</p>
                  ) : null}
                  <p className="font-mono text-xs text-muted-foreground">
                    Claim {claim.id.slice(0, 8)}... • Created {new Date(claim.created_at).toLocaleString()}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
