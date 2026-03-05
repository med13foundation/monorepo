import { NextResponse } from 'next/server'

import { logInfo } from '@/lib/logger'

export async function GET(): Promise<NextResponse> {
  const payload = {
    status: 'ok',
    service: 'artana-frontdoor',
    timestamp: new Date().toISOString(),
  }

  logInfo('health_check', payload)
  return NextResponse.json(payload)
}
