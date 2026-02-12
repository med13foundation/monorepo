import { redirect } from 'next/navigation'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { SidebarWrapper } from '@/components/navigation/sidebar/SidebarWrapper'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { SpaceContextProvider } from '@/components/space-context-provider'
import { fetchMyMembership, fetchResearchSpaces } from '@/lib/api/research-spaces'
import type { ResearchSpaceMembership } from '@/types/research-space'

type DashboardLayoutProps = {
  children: React.ReactNode
  params?: Promise<{
    spaceId?: string
  }>
}

function isValidUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

export default async function DashboardLayout({ children, params }: DashboardLayoutProps) {
  const resolvedParams = params ? await params : undefined
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token
  const expiresAt = session?.user?.expires_at
  const isExpired = typeof expiresAt !== 'number' || Date.now() >= expiresAt

  if (!session || !token || isExpired) {
    redirect('/auth/login?error=SessionExpired')
  }

  let initialSpaces: Awaited<ReturnType<typeof fetchResearchSpaces>>['spaces'] = []
  let initialTotal = 0
  let initialSpaceId: string | null = null
  let currentMembership: ResearchSpaceMembership | null = null

  if (token) {
    try {
      const response = await fetchResearchSpaces(undefined, token)
      initialSpaces = response.spaces
      initialTotal = response.total
      const spaceIdFromParams =
        typeof resolvedParams?.spaceId === 'string' && isValidUuid(resolvedParams.spaceId)
          ? resolvedParams.spaceId
          : null
      initialSpaceId = spaceIdFromParams ?? initialSpaces[0]?.id ?? null

      if (spaceIdFromParams) {
        currentMembership = await fetchMyMembership(spaceIdFromParams, token)
      }
    } catch (error) {
      console.error('[DashboardLayout] Failed to fetch research spaces', error)
    }
  }

  return (
    <ErrorBoundary>
      <ProtectedRoute>
        <SpaceContextProvider
          initialSpaces={initialSpaces}
          initialSpaceId={initialSpaceId}
          initialTotal={initialTotal}
        >
          <SidebarWrapper currentMembership={currentMembership}>
            {children}
          </SidebarWrapper>
        </SpaceContextProvider>
      </ProtectedRoute>
    </ErrorBoundary>
  )
}
