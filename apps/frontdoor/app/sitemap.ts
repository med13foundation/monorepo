import type { MetadataRoute } from 'next'

import { siteConfig } from '@/lib/site-config'

const routes = [
  '/',
  '/platform',
  '/security',
  '/contact',
  '/request-access',
  '/legal/privacy',
  '/legal/terms',
]

export default function sitemap(): MetadataRoute.Sitemap {
  return routes.map((path) => ({
    url: `${siteConfig.siteUrl}${path}`,
    changeFrequency: path === '/' ? 'weekly' : 'monthly',
    priority: path === '/' ? 1 : 0.7,
    lastModified: new Date(),
  }))
}
