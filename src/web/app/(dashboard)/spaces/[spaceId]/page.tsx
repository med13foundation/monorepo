import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import {
  fetchMyMembership,
  fetchResearchSpace,
  fetchSpaceCurationQueue,
  fetchSpaceCurationStats,
  fetchSpaceMembers,
} from '@/lib/api/research-spaces'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import { canManageMembers } from '@/components/research-spaces/role-utils'
import { MembershipRole, type ResearchSpace, type ResearchSpaceMembership } from '@/types/research-space'
import { UserRole } from '@/types/auth'
import SpaceDetailClient from './space-detail-client'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { CurationQueueResponse, CurationStats } from '@/lib/api/research-spaces'

interface SpaceDetailPageProps {
  params: Promise<{
    spaceId: string
  }>
}

export default async function SpaceDetailPage({ params }: SpaceDetailPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let space: ResearchSpace | null = null
  let memberships: ResearchSpaceMembership[] = []
  let membersError: string | null = null
  let dataSources: DataSourceListResponse | null = null
  let curationStats: CurationStats | null = null
  let curationQueue: CurationQueueResponse | null = null
  let currentMembership: ResearchSpaceMembership | null = null

  try {
    space = await fetchResearchSpace(spaceId, token)
  } catch (error) {
    console.error('[SpaceDetailPage] Failed to fetch research space', error)
  }

  try {
    const membershipResponse = await fetchSpaceMembers(spaceId, undefined, token)
    memberships = membershipResponse.memberships
  } catch (error) {
    membersError =
      error instanceof Error ? error.message : 'Unable to load members for this space.'
    console.error('[SpaceDetailPage] Failed to fetch members', error)
  }

  try {
    currentMembership = await fetchMyMembership(spaceId, token)
  } catch (error) {
    console.error('[SpaceDetailPage] Failed to fetch membership', error)
  }

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  const hasSpaceAccess = isPlatformAdmin || Boolean(currentMembership)

  if (hasSpaceAccess) {
    try {
      dataSources = await fetchDataSourcesBySpace(spaceId, { page: 1, limit: 5 }, token)
    } catch (error) {
      console.error('[SpaceDetailPage] Failed to fetch data sources', error)
    }

    try {
      curationStats = await fetchSpaceCurationStats(spaceId, token)
      curationQueue = await fetchSpaceCurationQueue(spaceId, { limit: 5 }, token)
    } catch (error) {
      console.error('[SpaceDetailPage] Failed to fetch curation data', error)
    }
  }

  const matchedMembership = memberships.find(
    (membership) => membership.user_id === session.user.id,
  )
  const effectiveRole =
    matchedMembership?.role ??
    currentMembership?.role ??
    (isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER)
  const canManageMembersFlag = isPlatformAdmin || canManageMembers(effectiveRole)
  const isOwner = effectiveRole === MembershipRole.OWNER
  const canEditSpace = isOwner || isPlatformAdmin
  const showMembershipNotice = !currentMembership && !isPlatformAdmin

  return (
    <SpaceDetailClient
      spaceId={spaceId}
      space={space}
      memberships={memberships}
      membersError={membersError}
      dataSources={dataSources}
      curationStats={curationStats}
      curationQueue={curationQueue}
      access={{
        hasSpaceAccess,
        canManageMembers: canManageMembersFlag,
        canEditSpace,
        isOwner,
        showMembershipNotice,
      }}
    />
  )
}
