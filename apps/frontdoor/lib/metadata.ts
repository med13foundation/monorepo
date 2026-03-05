import type { Metadata } from 'next'

import { siteConfig } from '@/lib/site-config'

type MetadataInput = {
  title: string
  description: string
  path: string
}

const withLeadingSlash = (path: string): string => {
  if (!path) {
    return '/'
  }
  return path.startsWith('/') ? path : `/${path}`
}

const normalizePath = (path: string): string => {
  const prefixed = withLeadingSlash(path)
  if (prefixed === '/') {
    return prefixed
  }
  return prefixed.endsWith('/') ? prefixed.slice(0, -1) : prefixed
}

const absoluteUrl = (path: string): string => {
  const normalized = normalizePath(path)
  return `${siteConfig.siteUrl}${normalized}`
}

export const buildMetadata = ({ title, description, path }: MetadataInput): Metadata => {
  const canonical = absoluteUrl(path)
  const ogImage = `${siteConfig.siteUrl}/frontdoor-mark.svg`

  return {
    title,
    description,
    metadataBase: new URL(siteConfig.siteUrl),
    alternates: {
      canonical,
    },
    openGraph: {
      title,
      description,
      url: canonical,
      siteName: siteConfig.siteName,
      type: 'website',
      images: [
        {
          url: ogImage,
          width: 1200,
          height: 630,
          alt: 'Artana.bio front door website',
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [ogImage],
    },
  }
}
