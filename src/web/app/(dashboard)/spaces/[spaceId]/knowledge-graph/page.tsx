import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import KnowledgeGraphClient from '../knowledge-graph-client'

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

  const question = parseSearchParam(resolvedSearchParams.q)?.trim() ?? ''
  const topK = parsePositiveInt(parseSearchParam(resolvedSearchParams.top_k), 25)
  const maxDepth = parsePositiveInt(parseSearchParam(resolvedSearchParams.max_depth), 2)
  const forceAgent = parseSearchParam(resolvedSearchParams.force_agent) === '1'

  return (
    <KnowledgeGraphClient
      spaceId={spaceId}
      initialQuestion={question}
      initialTopK={topK}
      initialMaxDepth={maxDepth}
      initialForceAgent={forceAgent}
    />
  )
}
