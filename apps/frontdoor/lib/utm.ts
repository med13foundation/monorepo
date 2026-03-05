export type UTMParameters = {
  source?: string
  medium?: string
  campaign?: string
  term?: string
  content?: string
}

const UTM_STORAGE_KEY = 'artana_frontdoor_utm'

const normalizeValue = (value: string | null): string | undefined => {
  const trimmed = value?.trim()
  if (!trimmed) {
    return undefined
  }
  return trimmed
}

export const extractUTMParameters = (searchParams: URLSearchParams): UTMParameters => {
  return {
    source: normalizeValue(searchParams.get('utm_source')),
    medium: normalizeValue(searchParams.get('utm_medium')),
    campaign: normalizeValue(searchParams.get('utm_campaign')),
    term: normalizeValue(searchParams.get('utm_term')),
    content: normalizeValue(searchParams.get('utm_content')),
  }
}

export const hasAnyUTM = (utm: UTMParameters): boolean => {
  return Boolean(utm.source || utm.medium || utm.campaign || utm.term || utm.content)
}

export const mergeUTMParameters = (base: UTMParameters, incoming: UTMParameters): UTMParameters => {
  return {
    source: incoming.source ?? base.source,
    medium: incoming.medium ?? base.medium,
    campaign: incoming.campaign ?? base.campaign,
    term: incoming.term ?? base.term,
    content: incoming.content ?? base.content,
  }
}

export const loadStoredUTM = (storage: Storage): UTMParameters => {
  const raw = storage.getItem(UTM_STORAGE_KEY)
  if (!raw) {
    return {}
  }

  try {
    const parsed = JSON.parse(raw) as UTMParameters
    return {
      source: normalizeValue(parsed.source ?? null),
      medium: normalizeValue(parsed.medium ?? null),
      campaign: normalizeValue(parsed.campaign ?? null),
      term: normalizeValue(parsed.term ?? null),
      content: normalizeValue(parsed.content ?? null),
    }
  } catch {
    return {}
  }
}

export const storeUTM = (storage: Storage, utm: UTMParameters): void => {
  if (!hasAnyUTM(utm)) {
    return
  }
  storage.setItem(UTM_STORAGE_KEY, JSON.stringify(utm))
}
