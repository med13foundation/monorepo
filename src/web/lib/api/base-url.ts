const LOCAL_API_BASE_URL = 'http://localhost:8080'
const ADMIN_HOST_PREFIX = 'med13-admin'
const API_HOST_PREFIX = 'med13-resource-library'

function inferApiBaseUrlFromHostname(hostname: string): string | null {
  if (!hostname.startsWith(ADMIN_HOST_PREFIX)) {
    return null
  }

  const apiHostname = hostname.replace(ADMIN_HOST_PREFIX, API_HOST_PREFIX)
  return `https://${apiHostname}`
}

function inferApiBaseUrlFromNextAuthUrl(nextAuthUrl: string): string | null {
  try {
    const nextAuthHostname = new URL(nextAuthUrl).hostname
    return inferApiBaseUrlFromHostname(nextAuthHostname)
  } catch {
    return null
  }
}

export function resolveApiBaseUrl(): string {
  const runtimeApiUrl = process.env.API_BASE_URL || process.env.INTERNAL_API_URL
  if (typeof runtimeApiUrl === 'string' && runtimeApiUrl.trim().length > 0) {
    return runtimeApiUrl
  }

  const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL
  if (typeof configuredApiUrl === 'string' && configuredApiUrl.trim().length > 0) {
    return configuredApiUrl
  }

  const nextAuthUrl = process.env.NEXTAUTH_URL
  if (typeof nextAuthUrl === 'string' && nextAuthUrl.trim().length > 0) {
    const inferredFromNextAuth = inferApiBaseUrlFromNextAuthUrl(nextAuthUrl)
    if (inferredFromNextAuth) {
      return inferredFromNextAuth
    }
  }

  if (typeof window !== 'undefined') {
    const inferredFromBrowserHost = inferApiBaseUrlFromHostname(window.location.hostname)
    if (inferredFromBrowserHost) {
      return inferredFromBrowserHost
    }
  }

  return LOCAL_API_BASE_URL
}
