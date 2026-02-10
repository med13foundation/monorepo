'use client'

import { useState } from 'react'
import { MechanismManagementSection } from '@/components/knowledge-graph/MechanismManagementSection'
import { StatementManagementSection } from '@/components/knowledge-graph/StatementManagementSection'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Waypoints } from 'lucide-react'
import type { PaginatedResponse } from '@/types/generated'
import type { Mechanism } from '@/types/mechanisms'
import type { Statement } from '@/types/statements'

interface KnowledgeGraphClientProps {
  spaceId: string
  mechanisms: PaginatedResponse<Mechanism> | null
  mechanismsError?: string | null
  statements: PaginatedResponse<Statement> | null
  statementsError?: string | null
  canManageMechanisms: boolean
  canManageStatements: boolean
}

export default function KnowledgeGraphClient({
  spaceId,
  mechanisms,
  mechanismsError,
  statements,
  statementsError,
  canManageMechanisms,
  canManageStatements,
}: KnowledgeGraphClientProps) {
  const [promotedMechanism, setPromotedMechanism] = useState<Mechanism | null>(null)

  return (
    <div className="space-y-6">
      <StatementManagementSection
        statements={statements}
        spaceId={spaceId}
        error={statementsError}
        canManage={canManageStatements}
        canPromote={canManageMechanisms}
        onPromoted={setPromotedMechanism}
      />
      <MechanismManagementSection
        mechanisms={mechanisms}
        spaceId={spaceId}
        error={mechanismsError}
        canManage={canManageMechanisms}
        promotedMechanism={promotedMechanism}
        onPromotionHandled={() => setPromotedMechanism(null)}
      />
      <DashboardSection
        title="Knowledge Graph"
        description="Explore the knowledge graph for this research space."
      >
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <Waypoints className="mb-4 size-12 text-muted-foreground" />
          <h3 className="mb-2 text-lg font-semibold">Knowledge Graph</h3>
          <p className="text-muted-foreground">This page is under construction.</p>
        </div>
      </DashboardSection>
    </div>
  )
}
