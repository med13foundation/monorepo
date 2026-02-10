import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceCurationClient from '../space-curation-client'
import { fetchKernelRelations } from '@/lib/api/kernel'
import { fetchMyMembership } from '@/lib/api/research-spaces'
import { MembershipRole } from '@/types/research-space'
import { UserRole } from '@/types/auth'
import type { KernelRelationListResponse } from '@/types/kernel'

interface SpaceCurationPageProps {
  params: {
    spaceId: string
  }
  searchParams?: Record<string, string | string[] | undefined>
}

function firstString(value: string | string[] | undefined): string | undefined {
  if (typeof value === 'string') {
    return value
  }
  return Array.isArray(value) ? value[0] : undefined
}

function parseIntParam(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

export default async function SpaceCurationPage({ params, searchParams }: SpaceCurationPageProps) {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let relations: KernelRelationListResponse | null = null
  let relationsError: string | null = null

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  let effectiveRole: MembershipRole = isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER

  try {
    const membership = await fetchMyMembership(params.spaceId, token)
    if (membership?.role) {
      effectiveRole = membership.role
    }
  } catch (error) {
    console.error('[SpaceCurationPage] Failed to fetch membership', error)
  }

  const canCurate =
    isPlatformAdmin ||
    effectiveRole === MembershipRole.OWNER ||
    effectiveRole === MembershipRole.ADMIN ||
    effectiveRole === MembershipRole.CURATOR

  const relationType = firstString(searchParams?.relation_type)
  const curationStatus = firstString(searchParams?.curation_status)
  const offset = parseIntParam(firstString(searchParams?.offset), 0)
  const limit = Math.min(parseIntParam(firstString(searchParams?.limit), 50), 200)

  try {
    relations = await fetchKernelRelations(
      params.spaceId,
      {
        ...(relationType ? { relation_type: relationType } : {}),
        ...(curationStatus ? { curation_status: curationStatus } : {}),
        offset,
        limit,
      },
      token,
    )
  } catch (error) {
    relationsError =
      error instanceof Error ? error.message : 'Unable to load relations for this space.'
    console.error('[SpaceCurationPage] Failed to fetch relations', error)
  }

  return (
    <SpaceCurationClient
      spaceId={params.spaceId}
      relations={relations}
      relationsError={relationsError}
      canCurate={canCurate}
      filters={{
        relationType: relationType ?? '',
        curationStatus: curationStatus ?? '',
        offset,
        limit,
      }}
    />
  )
}
