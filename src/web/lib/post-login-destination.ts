import { UserRole } from '@/types/auth'

const ADMIN_ONLY_PATH_PREFIXES = ['/dashboard', '/system-settings', '/admin']
const ADMIN_DEFAULT_DESTINATION = '/dashboard'
const NON_ADMIN_DEFAULT_DESTINATION = '/spaces'

function toCallbackPath(callbackUrl: string): string {
  try {
    const parsedUrl = new URL(callbackUrl, 'http://localhost:3000')
    const query = parsedUrl.search ?? ''
    return `${parsedUrl.pathname}${query}`
  } catch {
    return callbackUrl
  }
}

function isAdminOnlyPath(path: string): boolean {
  return ADMIN_ONLY_PATH_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  )
}

export function resolvePostLoginDestination(
  callbackUrl: string | null,
  role: UserRole | string | undefined,
): string {
  const isAdmin = role === UserRole.ADMIN
  const defaultDestination = isAdmin
    ? ADMIN_DEFAULT_DESTINATION
    : NON_ADMIN_DEFAULT_DESTINATION

  if (!callbackUrl) {
    return defaultDestination
  }

  const callbackPath = toCallbackPath(callbackUrl)

  if (!isAdmin && isAdminOnlyPath(callbackPath)) {
    return NON_ADMIN_DEFAULT_DESTINATION
  }

  return callbackUrl
}
