import { z } from 'zod'

const cleanText = (value: string): string => {
  return value.trim().replace(/[<>]/g, '')
}

const optionalCleanText = z.string().max(500).optional().or(z.literal('')).transform((value) => {
  if (!value) {
    return undefined
  }
  return cleanText(value)
})

export const inquiryTypeSchema = z.enum(['contact', 'request_access'])

export const leadSubmissionSchema = z.object({
  inquiryType: inquiryTypeSchema,
  fullName: z.string().min(2).max(120).transform(cleanText),
  workEmail: z.string().email().max(255).transform((value) => value.trim().toLowerCase()),
  organization: z.string().min(2).max(160).transform(cleanText),
  role: z.string().min(2).max(120).transform(cleanText),
  message: z.string().max(2500).optional().or(z.literal('')).transform((value) => {
    if (!value) {
      return undefined
    }
    return cleanText(value)
  }),
  source: optionalCleanText,
  medium: optionalCleanText,
  campaign: optionalCleanText,
  term: optionalCleanText,
  content: optionalCleanText,
  noPhiConfirmation: z.literal(true),
  honeypot: z.string().max(0).optional().or(z.literal('')),
})

export type LeadSubmissionPayload = z.infer<typeof leadSubmissionSchema>
