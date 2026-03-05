import { leadSubmissionSchema } from '@/lib/form-schema'

describe('leadSubmissionSchema', () => {
  it('accepts a valid request access payload', () => {
    const result = leadSubmissionSchema.safeParse({
      inquiryType: 'request_access',
      fullName: 'Taylor Researcher',
      workEmail: 'taylor@example.org',
      organization: 'Foundation Labs',
      role: 'Data Engineering',
      message: 'We need a secure ingestion and graph workflow.',
      source: 'newsletter',
      medium: 'email',
      campaign: 'launch-2026',
      term: '',
      content: '',
      noPhiConfirmation: true,
      honeypot: '',
    })

    expect(result.success).toBe(true)
  })

  it('rejects payloads without PHI confirmation', () => {
    const result = leadSubmissionSchema.safeParse({
      inquiryType: 'contact',
      fullName: 'Taylor Researcher',
      workEmail: 'taylor@example.org',
      organization: 'Foundation Labs',
      role: 'Data Engineering',
      message: 'Can we review your architecture?',
      noPhiConfirmation: false,
      honeypot: '',
    })

    expect(result.success).toBe(false)
  })

  it('sanitizes angle brackets from text fields', () => {
    const result = leadSubmissionSchema.parse({
      inquiryType: 'contact',
      fullName: '<Taylor>',
      workEmail: 'TAYLOR@EXAMPLE.ORG',
      organization: 'Foundation <Labs>',
      role: 'Data <Team>',
      message: '<script>alert(1)</script>',
      noPhiConfirmation: true,
      honeypot: '',
    })

    expect(result.fullName).toBe('Taylor')
    expect(result.organization).toBe('Foundation Labs')
    expect(result.workEmail).toBe('taylor@example.org')
    expect(result.message).toBe('scriptalert(1)/script')
  })
})
