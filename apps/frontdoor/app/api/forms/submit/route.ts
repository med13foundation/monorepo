import { randomUUID } from 'crypto'

import { NextRequest, NextResponse } from 'next/server'

import { leadSubmissionSchema } from '@/lib/form-schema'
import { logError, logInfo } from '@/lib/logger'
import { checkRateLimit } from '@/lib/rate-limit'

const RATE_LIMIT = {
  limit: 6,
  windowMs: 60_000,
}

const getClientAddress = (request: NextRequest): string => {
  const forwardedFor = request.headers.get('x-forwarded-for')
  if (forwardedFor) {
    return forwardedFor.split(',')[0].trim()
  }

  const realIp = request.headers.get('x-real-ip')
  if (realIp) {
    return realIp
  }

  return 'unknown'
}

const submitToEndpoint = async (
  endpoint: string,
  body: Record<string, unknown>,
): Promise<{ ok: boolean; status: number }> => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 8_000)

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
      cache: 'no-store',
    })

    return {
      ok: response.ok,
      status: response.status,
    }
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const submissionId = randomUUID()
  const clientIp = getClientAddress(request)
  const rateLimitKey = `form-submit:${clientIp}`

  const rateLimit = checkRateLimit(rateLimitKey, RATE_LIMIT)
  if (!rateLimit.allowed) {
    logInfo('form_rate_limited', {
      submissionId,
      clientIp,
      retryAfterSeconds: rateLimit.retryAfterSeconds,
    })

    return NextResponse.json(
      {
        message: 'Too many requests. Please try again shortly.',
      },
      {
        status: 429,
        headers: {
          'Retry-After': String(rateLimit.retryAfterSeconds),
        },
      },
    )
  }

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ message: 'Invalid JSON payload.' }, { status: 400 })
  }

  const parsed = leadSubmissionSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json(
      {
        message: 'Invalid form payload.',
        errors: parsed.error.flatten().fieldErrors,
      },
      { status: 400 },
    )
  }

  const payload = parsed.data

  // Quietly succeed for probable bot traffic.
  if (payload.honeypot) {
    logInfo('form_honeypot_triggered', {
      submissionId,
      inquiryType: payload.inquiryType,
      clientIp,
    })

    return NextResponse.json({ success: true, submissionId }, { status: 200 })
  }

  const endpoint = process.env.CONTACT_FORM_ENDPOINT
  const requestBody = {
    submissionId,
    submittedAt: new Date().toISOString(),
    inquiryType: payload.inquiryType,
    contact: {
      fullName: payload.fullName,
      workEmail: payload.workEmail,
      organization: payload.organization,
      role: payload.role,
    },
    message: payload.message,
    attribution: {
      source: payload.source,
      medium: payload.medium,
      campaign: payload.campaign,
      term: payload.term,
      content: payload.content,
    },
    metadata: {
      userAgent: request.headers.get('user-agent') ?? 'unknown',
      clientIp,
      path: request.nextUrl.pathname,
    },
  }

  try {
    if (!endpoint) {
      if (process.env.NODE_ENV === 'production') {
        logError('form_endpoint_missing', {
          submissionId,
          inquiryType: payload.inquiryType,
        })
        return NextResponse.json({ message: 'Service temporarily unavailable.' }, { status: 503 })
      }

      logInfo('form_submission_local_only', {
        submissionId,
        inquiryType: payload.inquiryType,
      })
      return NextResponse.json({ success: true, submissionId }, { status: 200 })
    }

    const submitResult = await submitToEndpoint(endpoint, requestBody)

    if (!submitResult.ok) {
      logError('form_forwarding_failed', {
        submissionId,
        inquiryType: payload.inquiryType,
        endpoint,
        status: submitResult.status,
      })
      return NextResponse.json({ message: 'Could not submit form right now.' }, { status: 502 })
    }

    logInfo('form_submission_forwarded', {
      submissionId,
      inquiryType: payload.inquiryType,
      endpoint,
    })

    return NextResponse.json({ success: true, submissionId }, { status: 200 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown forwarding error'

    logError('form_submission_error', {
      submissionId,
      inquiryType: payload.inquiryType,
      message,
    })

    return NextResponse.json({ message: 'Unexpected error while processing form.' }, { status: 500 })
  }
}
