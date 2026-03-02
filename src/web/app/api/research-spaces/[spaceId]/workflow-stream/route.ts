import { randomUUID } from 'crypto'
import { NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'

import { authOptions } from '@/lib/auth'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface SpaceWorkflowStreamRouteContext {
  params: Promise<{
    spaceId: string
  }>
}

export async function GET(
  request: Request,
  context: SpaceWorkflowStreamRouteContext,
): Promise<Response> {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token
  if (!token) {
    return new NextResponse(JSON.stringify({ detail: 'Authentication required' }), {
      status: 401,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }

  const { spaceId } = await context.params
  const upstreamUrl = new URL(`/research-spaces/${spaceId}/workflow-stream`, API_BASE_URL)
  const requestUrl = new URL(request.url)
  requestUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value)
  })

  const upstream = await fetch(upstreamUrl, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
      'X-Request-ID': randomUUID(),
      Connection: 'keep-alive',
    },
    cache: 'no-store',
  })
  if (!upstream.ok) {
    const errorBody = await upstream.text()
    return new NextResponse(errorBody || 'Workflow stream proxy failed', {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') ?? 'text/plain',
      },
    })
  }
  if (upstream.body === null) {
    return new NextResponse('Workflow stream body unavailable', { status: 502 })
  }

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  })
}
