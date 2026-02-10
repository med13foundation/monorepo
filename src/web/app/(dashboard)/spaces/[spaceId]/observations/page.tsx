import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { fetchKernelObservations } from '@/lib/api/kernel'
import SpaceObservationsClient from '../space-observations-client'
import type { KernelObservationListResponse } from '@/types/kernel'

type SearchParams = Record<string, string | string[] | undefined>

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

interface SpaceObservationsPageProps {
  params: { spaceId: string }
  searchParams?: SearchParams
}

export default async function SpaceObservationsPage({ params, searchParams }: SpaceObservationsPageProps) {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  const subjectId = firstString(searchParams?.subject_id)
  const variableId = firstString(searchParams?.variable_id)
  const offset = parseIntParam(firstString(searchParams?.offset), 0)
  const limit = Math.min(parseIntParam(firstString(searchParams?.limit), 50), 200)

  let observations: KernelObservationListResponse | null = null
  let observationsError: string | null = null

  try {
    observations = await fetchKernelObservations(
      params.spaceId,
      {
        ...(subjectId ? { subject_id: subjectId } : {}),
        ...(variableId ? { variable_id: variableId } : {}),
        offset,
        limit,
      },
      token,
    )
  } catch (error) {
    observationsError =
      error instanceof Error ? error.message : 'Unable to load observations for this space.'
    console.error('[SpaceObservationsPage] Failed to fetch observations', error)
  }

  return (
    <SpaceObservationsClient
      spaceId={params.spaceId}
      observations={observations}
      observationsError={observationsError}
      filters={{
        subjectId: subjectId ?? '',
        variableId: variableId ?? '',
        offset,
        limit,
      }}
    />
  )
}
