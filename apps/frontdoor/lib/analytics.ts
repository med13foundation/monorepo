export type AnalyticsPrimitive = string | number | boolean
export type AnalyticsPayload = Record<string, AnalyticsPrimitive | null | undefined>

declare global {
  interface Window {
    dataLayer?: Array<Record<string, AnalyticsPrimitive | null | undefined>>
    gtag?: (...args: unknown[]) => void
  }
}

const pushDataLayer = (payload: Record<string, AnalyticsPrimitive | null | undefined>): void => {
  if (typeof window === 'undefined') {
    return
  }

  if (!window.dataLayer) {
    window.dataLayer = []
  }

  window.dataLayer.push(payload)
}

export const trackEvent = (eventName: string, payload: AnalyticsPayload = {}): void => {
  if (typeof window === 'undefined') {
    return
  }

  const mergedPayload = {
    event: eventName,
    ...payload,
  }

  pushDataLayer(mergedPayload)

  if (typeof window.gtag === 'function') {
    window.gtag('event', eventName, payload)
  }
}

export const trackPageView = (path: string): void => {
  trackEvent('page_view', { path })
}
