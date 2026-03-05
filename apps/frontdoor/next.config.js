const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3010'
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080'
const docsUrl = process.env.NEXT_PUBLIC_DOCS_URL || 'https://docs.artana.bio'
const adminUrl = process.env.NEXT_PUBLIC_ADMIN_URL || 'http://localhost:3000/dashboard'

const buildCspHeader = () => {
  const isDevelopment = process.env.NODE_ENV === 'development'
  const connectSources = ["'self'", apiBaseUrl, docsUrl, adminUrl, siteUrl, 'https://www.google-analytics.com']

  if (isDevelopment) {
    try {
      const site = new URL(siteUrl)
      connectSources.push(`ws://${site.host}`)
    } catch {
      connectSources.push('ws://localhost:3000')
    }
  }

  const scriptSources = ["'self'", "'unsafe-inline'", 'https://www.googletagmanager.com']
  if (isDevelopment) {
    scriptSources.push("'unsafe-eval'")
  }

  const directives = [
    "default-src 'self'",
    "base-uri 'self'",
    `connect-src ${connectSources.join(' ')}`,
    "font-src 'self' data: https:",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "img-src 'self' data: https:",
    "object-src 'none'",
    `script-src ${scriptSources.join(' ')}`,
    "style-src 'self' 'unsafe-inline'",
  ]

  if (!isDevelopment) {
    directives.push('upgrade-insecure-requests')
  }

  return directives.join('; ')
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  compress: true,
  experimental: {
    // Avoid unstable devtools segment explorer module wiring in dev mode.
    devtoolSegmentExplorer: false,
    // Keep dev on stable, non-experimental routing/cache paths.
    cacheComponents: false,
    clientSegmentCache: false,
    clientParamParsing: false,
    ppr: false,
  },
  async headers() {
    const csp = buildCspHeader()
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-DNS-Prefetch-Control', value: 'off' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
          { key: 'Content-Security-Policy', value: csp },
        ],
      },
      {
        source: '/_next/static/:path*',
        headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
      },
      {
        source: '/:path*.(svg|jpg|jpeg|png|webp|ico|woff2)',
        headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
      },
    ]
  },
}

module.exports = nextConfig
