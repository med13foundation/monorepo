'use client'

import type { ConceptMemberResponse } from '@/types/concepts'

import { ConceptNearDuplicatesCard } from './concept-near-duplicates-card'

interface ConceptResearchTriagePanelProps {
  spaceId: string
  canEdit: boolean
  conceptMembers: ConceptMemberResponse[]
}

export function ConceptResearchTriagePanel({
  spaceId,
  canEdit,
  conceptMembers,
}: ConceptResearchTriagePanelProps) {
  return (
    <ConceptNearDuplicatesCard
      spaceId={spaceId}
      canEdit={canEdit}
      conceptMembers={conceptMembers}
    />
  )
}
