import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceCurationClient from '../space-curation-client'
import { fetchKernelEntities, fetchKernelRelations } from '@/lib/api/kernel'
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

function parseStringList(value: string | string[] | undefined): string[] {
  if (value === undefined) {
    return []
  }
  const raw = typeof value === 'string' ? [value] : value
  return raw
    .flatMap((entry) => entry.split(','))
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
}

function parseIntParam(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

function isTimeoutLikeError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) {
    return false
  }
  const payload = error as Record<string, unknown>
  const code = payload.code
  if (typeof code === 'string' && code === 'ECONNABORTED') {
    return true
  }
  const message = payload.message
  if (typeof message === 'string') {
    return message.toLowerCase().includes('timeout')
  }
  return false
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message
  }
  return 'Unable to load relations for this space.'
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
  let entityLabelsById: Record<string, string> = {}

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  let effectiveRole: MembershipRole = isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER

  const relationType = firstString(resolvedSearchParams?.relation_type)
  const curationStatus = firstString(resolvedSearchParams?.curation_status)
  const nodeQuery = firstString(resolvedSearchParams?.node_query)
  const nodeIds = parseStringList(resolvedSearchParams?.node_ids)
  const offset = parseIntParam(firstString(resolvedSearchParams?.offset), 0)
  const limit = Math.min(parseIntParam(firstString(resolvedSearchParams?.limit), 25), 200)
  const membershipPromise = fetchMyMembership(spaceId, token)

  try {
    relations = await fetchKernelRelations(
      spaceId,
      {
        ...(relationType ? { relation_type: relationType } : {}),
        ...(curationStatus ? { curation_status: curationStatus } : {}),
        ...(nodeQuery ? { node_query: nodeQuery } : {}),
        ...(nodeIds.length > 0 ? { node_ids: nodeIds } : {}),
        offset,
        limit,
      },
      token,
    )
  } catch (error) {
    const timeoutLikeError = isTimeoutLikeError(error)
    if (timeoutLikeError && limit > 20) {
      try {
        relations = await fetchKernelRelations(
          spaceId,
          {
            ...(relationType ? { relation_type: relationType } : {}),
            ...(curationStatus ? { curation_status: curationStatus } : {}),
            ...(nodeQuery ? { node_query: nodeQuery } : {}),
            ...(nodeIds.length > 0 ? { node_ids: nodeIds } : {}),
            offset,
            limit: 20,
          },
          token,
        )
      } catch (retryError) {
        relationsError = errorMessage(retryError)
        console.warn(`[SpaceCurationPage] Relation lookup retry failed: ${relationsError}`)
      }
    } else {
      relationsError = errorMessage(error)
      console.warn(`[SpaceCurationPage] Relation lookup failed: ${relationsError}`)
    }
  }

  try {
    const membership = await membershipPromise
    if (membership?.role) {
      effectiveRole = membership.role
    }
  } catch (error) {
    console.warn('[SpaceCurationPage] Membership lookup unavailable; using fallback role')
  }

  const canCurate =
    isPlatformAdmin ||
    effectiveRole === MembershipRole.OWNER ||
    effectiveRole === MembershipRole.ADMIN ||
    effectiveRole === MembershipRole.CURATOR

  const uniqueEntityIds = new Set<string>(nodeIds)
  if (relations?.relations && relations.relations.length > 0) {
    for (const relation of relations.relations) {
      uniqueEntityIds.add(relation.source_id)
      uniqueEntityIds.add(relation.target_id)
    }
  }

  if (uniqueEntityIds.size > 0) {
    const entityIds = Array.from(uniqueEntityIds).slice(0, 80)
    const labelById: Record<string, string> = {}
    for (const entityId of entityIds) {
      labelById[entityId] = `Entity ${entityId.slice(0, 8)}`
    }
    try {
      const entities = await fetchKernelEntities(
        spaceId,
        {
          ids: entityIds,
          offset: 0,
          limit: entityIds.length,
        },
        token,
      )
      for (const entity of entities.entities) {
        const resolved =
          entity.display_label && entity.display_label.trim().length > 0
            ? entity.display_label.trim()
            : entity.entity_type
        labelById[entity.id] = resolved
      }
    } catch (error) {
      console.warn('[SpaceCurationPage] Failed to fetch entity labels in bulk', error)
    }
    entityLabelsById = labelById
  }

  return (
    <SpaceCurationClient
      spaceId={spaceId}
      relations={relations}
      relationsError={relationsError}
      entityLabelsById={entityLabelsById}
      canCurate={canCurate}
      filters={{
        relationType: relationType ?? '',
        curationStatus: curationStatus ?? '',
        nodeIds,
        offset,
        limit,
      }}
    />
  )
}
