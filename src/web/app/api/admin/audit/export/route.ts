import { randomUUID } from 'crypto'
import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'

import { authOptions } from '@/lib/auth'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

export async function GET(request: NextRequest): Promise<Response> {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!token) {
    return NextResponse.json(
      { detail: 'Authentication required' },
      { status: 401 },
    )
  }

  const upstreamUrl = new URL('/admin/audit/logs/export', API_BASE_URL)
  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value)
  })

  const upstream = await fetch(upstreamUrl, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json, text/csv',
      'X-Request-ID': randomUUID(),
    },
    cache: 'no-store',
  })

  if (!upstream.ok) {
    const errorBody = await upstream.text()
    return new NextResponse(errorBody || 'Audit export failed', {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') ?? 'text/plain',
      },
    })
  }

  const payload = await upstream.arrayBuffer()
  return new NextResponse(payload, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/octet-stream',
      'Content-Disposition':
        upstream.headers.get('Content-Disposition') ??
        'attachment; filename="audit_logs_export.dat"',
      'Cache-Control': 'no-store',
    },
  })
}
