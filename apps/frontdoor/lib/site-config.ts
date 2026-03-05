export type NavItem = {
  label: string
  href: string
  external?: boolean
}

const FALLBACK_SITE_URL = 'http://localhost:3010'
const FALLBACK_ADMIN_URL = 'http://localhost:3000/dashboard'
const FALLBACK_DOCS_URL = 'https://docs.artana.bio'

const normalizeUrl = (value: string | undefined, fallback: string): string => {
  const candidate = value?.trim()
  if (!candidate) {
    return fallback
  }
  return candidate.endsWith('/') ? candidate.slice(0, -1) : candidate
}

const siteUrl = normalizeUrl(process.env.NEXT_PUBLIC_SITE_URL, FALLBACK_SITE_URL)
const adminUrl = normalizeUrl(process.env.NEXT_PUBLIC_ADMIN_URL, FALLBACK_ADMIN_URL)
const docsUrl = normalizeUrl(process.env.NEXT_PUBLIC_DOCS_URL, FALLBACK_DOCS_URL)

export const siteConfig = {
  siteName: 'Artana.bio',
  siteTagline: 'Domain-agnostic research platform for private, computable discovery workflows.',
  siteUrl,
  adminUrl,
  docsUrl,
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim() || 'support@artana.bio',
  navItems: [
    { label: 'Platform', href: '/platform' },
    { label: 'Security', href: '/security' },
    { label: 'Docs', href: docsUrl, external: true },
    { label: 'Admin Login', href: adminUrl, external: true },
  ] satisfies NavItem[],
}
