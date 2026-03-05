import type { MetadataRoute } from 'next'

import { siteConfig } from '@/lib/site-config'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: ['/', '/platform', '/security', '/contact', '/request-access', '/legal/privacy', '/legal/terms'],
        disallow: ['/api/'],
      },
    ],
    sitemap: `${siteConfig.siteUrl}/sitemap.xml`,
  }
}
