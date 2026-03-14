const LOCAL_GRAPH_HARNESS_API_BASE_URL = 'http://localhost:8091'
const ADMIN_HOST_PREFIX = 'med13-admin'
const GRAPH_HARNESS_API_HOST_PREFIX = 'med13-graph-harness-api'

function isLocalRuntime(): boolean {
  return process.env.NODE_ENV === 'development' || process.env.NODE_ENV === 'test'
}

function inferGraphHarnessApiBaseUrlFromHostname(hostname: string): string | null {
  if (!hostname.startsWith(ADMIN_HOST_PREFIX)) {
    return null
  }

  const harnessHostname = hostname.replace(
    ADMIN_HOST_PREFIX,
    GRAPH_HARNESS_API_HOST_PREFIX,
  )
  return `https://${harnessHostname}`
}

function inferGraphHarnessApiBaseUrlFromNextAuthUrl(
  nextAuthUrl: string,
): string | null {
  try {
    return inferGraphHarnessApiBaseUrlFromHostname(new URL(nextAuthUrl).hostname)
  } catch {
    return null
  }
}

export function resolveGraphHarnessApiBaseUrl(): string {
  const runtimeHarnessApiUrl =
    process.env.GRAPH_HARNESS_API_BASE_URL ||
    process.env.INTERNAL_GRAPH_HARNESS_API_URL
  if (
    typeof runtimeHarnessApiUrl === 'string' &&
    runtimeHarnessApiUrl.trim().length > 0
  ) {
    return runtimeHarnessApiUrl
  }

  const configuredHarnessApiUrl = process.env.NEXT_PUBLIC_GRAPH_HARNESS_API_URL
  if (
    typeof configuredHarnessApiUrl === 'string' &&
    configuredHarnessApiUrl.trim().length > 0
  ) {
    return configuredHarnessApiUrl
  }

  const nextAuthUrl = process.env.NEXTAUTH_URL
  if (typeof nextAuthUrl === 'string' && nextAuthUrl.trim().length > 0) {
    const inferredFromNextAuth =
      inferGraphHarnessApiBaseUrlFromNextAuthUrl(nextAuthUrl)
    if (inferredFromNextAuth) {
      return inferredFromNextAuth
    }
  }

  if (typeof window !== 'undefined') {
    const inferredFromHostname = inferGraphHarnessApiBaseUrlFromHostname(
      window.location.hostname,
    )
    if (inferredFromHostname) {
      return inferredFromHostname
    }
    if (!isLocalRuntime()) {
      throw new Error(
        'NEXT_PUBLIC_GRAPH_HARNESS_API_URL is required outside local development for browser harness calls',
      )
    }
  }

  if (!isLocalRuntime()) {
    throw new Error(
      'INTERNAL_GRAPH_HARNESS_API_URL or GRAPH_HARNESS_API_BASE_URL is required outside local development',
    )
  }

  return LOCAL_GRAPH_HARNESS_API_BASE_URL
}
