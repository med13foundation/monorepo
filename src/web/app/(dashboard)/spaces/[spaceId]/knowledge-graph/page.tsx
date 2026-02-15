import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import KnowledgeGraphClient from '../knowledge-graph-client'
import { fetchKernelGraphExport, searchKernelGraph } from '@/lib/api/kernel'
import type { GraphSearchResponse, KernelGraphExportResponse } from '@/types/kernel'

interface KnowledgeGraphPageProps {
  params: Promise<{
    spaceId: string
  }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

function parseSearchParam(
  value: string | string[] | undefined,
): string | undefined {
  if (Array.isArray(value)) {
    return value[0]
  }
  return value
}

function parsePositiveInt(
  value: string | undefined,
  fallback: number,
): number {
  if (!value) {
    return fallback
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export default async function KnowledgeGraphPage({
  params,
  searchParams,
}: KnowledgeGraphPageProps) {
  const { spaceId } = await params
  const resolvedSearchParams = await searchParams
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let graph: KernelGraphExportResponse | null = null
  let graphError: string | null = null
  let graphSearch: GraphSearchResponse | null = null
  let graphSearchError: string | null = null

  const question = parseSearchParam(resolvedSearchParams.q)?.trim() ?? ''
  const topK = parsePositiveInt(parseSearchParam(resolvedSearchParams.top_k), 25)
  const maxDepth = parsePositiveInt(parseSearchParam(resolvedSearchParams.max_depth), 2)
  const forceAgent = parseSearchParam(resolvedSearchParams.force_agent) === '1'

  try {
    graph = await fetchKernelGraphExport(spaceId, token)
  } catch (error) {
    graphError =
      error instanceof Error ? error.message : 'Unable to load knowledge graph for this space.'
    console.error('[KnowledgeGraphPage] Failed to fetch graph export', error)
  }

  if (question.length > 0) {
    try {
      graphSearch = await searchKernelGraph(
        spaceId,
        {
          question,
          top_k: topK,
          max_depth: maxDepth,
          include_evidence_chains: true,
          force_agent: forceAgent,
        },
        token,
      )
    } catch (error) {
      graphSearchError =
        error instanceof Error
          ? error.message
          : 'Unable to execute graph search for this space.'
      console.error('[KnowledgeGraphPage] Failed to execute graph search', error)
    }
  }

  return (
    <KnowledgeGraphClient
      spaceId={spaceId}
      graph={graph}
      graphError={graphError}
      graphSearch={graphSearch}
      graphSearchError={graphSearchError}
      initialQuestion={question}
      initialTopK={topK}
      initialMaxDepth={maxDepth}
      initialForceAgent={forceAgent}
    />
  )
}
