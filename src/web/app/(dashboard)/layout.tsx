import { redirect } from 'next/navigation'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { SidebarWrapper } from '@/components/navigation/sidebar/SidebarWrapper'
import { getServerSession } from 'next-auth'
import axios from 'axios'
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

function extractAxiosErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return 'Request failed'
  }

  if (error.response?.status === 401) {
    const responseData = error.response.data
    if (typeof responseData === 'string' && responseData.trim()) {
      return responseData
    }
    if (responseData && typeof responseData === 'object') {
      const detail = (responseData as Record<string, unknown>).detail
      if (typeof detail === 'string' && detail.trim()) {
        return detail
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const firstDetail = detail[0]
        if (typeof firstDetail === 'string') {
          return firstDetail
        }
        if (firstDetail && typeof firstDetail === 'object') {
          const firstDetailMessage = (firstDetail as Record<string, unknown>).msg
          if (typeof firstDetailMessage === 'string' && firstDetailMessage.trim()) {
            return firstDetailMessage
          }
        }
      }
    }
    return 'Session is not valid. Please sign in again.'
  }

  return 'Request failed'
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
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        const message = extractAxiosErrorMessage(error)
        redirect(
          `/auth/login?error=${encodeURIComponent('SessionExpired')}&message=${encodeURIComponent(message)}`,
        )
      } else {
        // Non-auth failures are surfaced via application-level UI state in child routes.
        // Keep the layout resilient by falling back to an empty initial state.
      }
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
