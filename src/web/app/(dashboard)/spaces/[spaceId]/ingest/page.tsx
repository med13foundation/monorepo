import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceIngestClient from '../space-ingest-client'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import type { DataSource } from '@/types/data-source'

interface SpaceIngestPageProps {
  params: Promise<{ spaceId: string }>
}

export default async function SpaceIngestPage({ params }: SpaceIngestPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let dataSources: DataSource[] = []
  try {
    const response = await fetchDataSourcesBySpace(spaceId, {}, token)
    dataSources = response.items
  } catch (error: unknown) {
    console.error('[SpaceIngestPage] Failed to fetch data sources for ingest page', error)
  }

  return <SpaceIngestClient spaceId={spaceId} dataSources={dataSources} />
}
