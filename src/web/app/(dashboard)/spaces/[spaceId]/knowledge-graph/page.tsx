import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import KnowledgeGraphClient from '../knowledge-graph-client'
import { fetchMechanisms } from '@/lib/api/mechanisms'
import { fetchStatements } from '@/lib/api/statements'
import { fetchMyMembership } from '@/lib/api/research-spaces'
import { canManageMechanisms, canManageStatements } from '@/components/research-spaces/role-utils'
import { MembershipRole } from '@/types/research-space'
import { UserRole } from '@/types/auth'
import type { PaginatedResponse } from '@/types/generated'
import type { Mechanism } from '@/types/mechanisms'
import type { Statement } from '@/types/statements'

interface KnowledgeGraphPageProps {
  params: {
    spaceId: string
  }
}

export default async function KnowledgeGraphPage({ params }: KnowledgeGraphPageProps) {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let mechanisms: PaginatedResponse<Mechanism> | null = null
  let mechanismsError: string | null = null
  let statements: PaginatedResponse<Statement> | null = null
  let statementsError: string | null = null
  let canManageMechanismsValue = false
  let canManageStatementsValue = false
  let currentMembershipRole: MembershipRole | null = null

  try {
    mechanisms = await fetchMechanisms(params.spaceId, { page: 1, per_page: 50 }, token)
  } catch (error) {
    mechanismsError =
      error instanceof Error ? error.message : 'Unable to load mechanisms for this space.'
    console.error('[KnowledgeGraphPage] Failed to fetch mechanisms', error)
  }

  try {
    statements = await fetchStatements(params.spaceId, { page: 1, per_page: 50 }, token)
  } catch (error) {
    statementsError =
      error instanceof Error ? error.message : 'Unable to load statements for this space.'
    console.error('[KnowledgeGraphPage] Failed to fetch statements', error)
  }

  try {
    const membership = await fetchMyMembership(params.spaceId, token)
    currentMembershipRole = membership?.role ?? null
  } catch (error) {
    console.error('[KnowledgeGraphPage] Failed to fetch membership', error)
  }

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  const effectiveRole =
    currentMembershipRole ?? (isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER)
  canManageMechanismsValue = isPlatformAdmin || canManageMechanisms(effectiveRole)
  canManageStatementsValue = isPlatformAdmin || canManageStatements(effectiveRole)

  return (
    <KnowledgeGraphClient
      spaceId={params.spaceId}
      mechanisms={mechanisms}
      mechanismsError={mechanismsError}
      statements={statements}
      statementsError={statementsError}
      canManageMechanisms={canManageMechanismsValue}
      canManageStatements={canManageStatementsValue}
    />
  )
}
