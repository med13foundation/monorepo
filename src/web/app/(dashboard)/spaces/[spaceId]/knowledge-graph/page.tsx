import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import KnowledgeGraphClient from '../knowledge-graph-client'
import { fetchKernelGraphExport } from '@/lib/api/kernel'
import type { KernelGraphExportResponse } from '@/types/kernel'

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

  let graph: KernelGraphExportResponse | null = null
  let graphError: string | null = null

  try {
    graph = await fetchKernelGraphExport(params.spaceId, token)
  } catch (error) {
    graphError =
      error instanceof Error ? error.message : 'Unable to load knowledge graph for this space.'
    console.error('[KnowledgeGraphPage] Failed to fetch graph export', error)
  }

  return (
    <KnowledgeGraphClient
      spaceId={params.spaceId}
      graph={graph}
      graphError={graphError}
    />
  )
}
