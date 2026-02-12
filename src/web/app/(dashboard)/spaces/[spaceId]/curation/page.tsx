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
  params: Promise<{
    spaceId: string
  }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
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
  const { spaceId } = await params
  const resolvedSearchParams = searchParams ? await searchParams : undefined
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
    const membership = await fetchMyMembership(spaceId, token)
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

  const relationType = firstString(resolvedSearchParams?.relation_type)
  const curationStatus = firstString(resolvedSearchParams?.curation_status)
  const offset = parseIntParam(firstString(resolvedSearchParams?.offset), 0)
  const limit = Math.min(parseIntParam(firstString(resolvedSearchParams?.limit), 50), 200)

  try {
    relations = await fetchKernelRelations(
      spaceId,
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
      spaceId={spaceId}
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
