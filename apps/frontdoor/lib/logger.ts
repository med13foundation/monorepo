const withDefaults = (level: 'info' | 'error', event: string, details: Record<string, unknown>): string => {
  return JSON.stringify({
    level,
    event,
    timestamp: new Date().toISOString(),
    ...details,
  })
}

export const logInfo = (event: string, details: Record<string, unknown>): void => {
  console.info(withDefaults('info', event, details))
}

export const logError = (event: string, details: Record<string, unknown>): void => {
  console.error(withDefaults('error', event, details))
}
