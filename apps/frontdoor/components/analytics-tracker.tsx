'use client'

import { usePathname, useSearchParams } from 'next/navigation'
import { useEffect } from 'react'

import { trackPageView } from '@/lib/analytics'
import { extractUTMParameters, hasAnyUTM, loadStoredUTM, mergeUTMParameters, storeUTM } from '@/lib/utm'

export const AnalyticsTracker = (): null => {
  const pathname = usePathname()
  const searchParams = useSearchParams()

  useEffect(() => {
    const query = searchParams.toString()
    const path = query ? `${pathname}?${query}` : pathname
    trackPageView(path)

    const currentUTM = extractUTMParameters(new URLSearchParams(query))
    if (typeof window !== 'undefined' && hasAnyUTM(currentUTM)) {
      const stored = loadStoredUTM(window.sessionStorage)
      const merged = mergeUTMParameters(stored, currentUTM)
      storeUTM(window.sessionStorage, merged)
    }
  }, [pathname, searchParams])

  return null
}
