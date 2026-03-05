'use client'

import { useSearchParams } from 'next/navigation'
import { FormEvent, useEffect, useMemo, useState } from 'react'

import { trackEvent } from '@/lib/analytics'
import type { LeadSubmissionPayload } from '@/lib/form-schema'
import type { UTMParameters } from '@/lib/utm'
import { extractUTMParameters, hasAnyUTM, loadStoredUTM, mergeUTMParameters, storeUTM } from '@/lib/utm'

type InquiryType = 'contact' | 'request_access'

type LeadFormProps = {
  inquiryType: InquiryType
}

type FormState = {
  fullName: string
  workEmail: string
  organization: string
  role: string
  message: string
  noPhiConfirmation: boolean
  honeypot: string
}

type FieldErrorMap = Partial<Record<keyof FormState, string>>

const initialFormState: FormState = {
  fullName: '',
  workEmail: '',
  organization: '',
  role: '',
  message: '',
  noPhiConfirmation: false,
  honeypot: '',
}

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const validateForm = (state: FormState, inquiryType: InquiryType): FieldErrorMap => {
  const errors: FieldErrorMap = {}

  if (state.fullName.trim().length < 2) {
    errors.fullName = 'Enter your full name.'
  }

  if (!emailPattern.test(state.workEmail.trim())) {
    errors.workEmail = 'Enter a valid work email address.'
  }

  if (state.organization.trim().length < 2) {
    errors.organization = 'Enter your organization.'
  }

  if (state.role.trim().length < 2) {
    errors.role = 'Enter your role or team.'
  }

  if (inquiryType === 'contact' && state.message.trim().length < 10) {
    errors.message = 'Add a short message so we can route your request.'
  }

  if (!state.noPhiConfirmation) {
    errors.noPhiConfirmation = 'Please confirm your message has no PHI.'
  }

  return errors
}

const submitLabelByType: Record<InquiryType, string> = {
  contact: 'Send message',
  request_access: 'Request access',
}

export const LeadForm = ({ inquiryType }: LeadFormProps): JSX.Element => {
  const [formState, setFormState] = useState<FormState>(initialFormState)
  const [utm, setUtm] = useState<UTMParameters>({})
  const [errors, setErrors] = useState<FieldErrorMap>({})
  const [submitting, setSubmitting] = useState(false)
  const [submissionMessage, setSubmissionMessage] = useState<string | null>(null)
  const [submissionError, setSubmissionError] = useState<string | null>(null)

  const searchParams = useSearchParams()

  useEffect(() => {
    const current = extractUTMParameters(new URLSearchParams(searchParams.toString()))
    if (typeof window === 'undefined') {
      return
    }

    const stored = loadStoredUTM(window.sessionStorage)
    const merged = mergeUTMParameters(stored, current)
    setUtm(merged)

    if (hasAnyUTM(merged)) {
      storeUTM(window.sessionStorage, merged)
    }
  }, [searchParams])

  const submitLabel = useMemo(() => submitLabelByType[inquiryType], [inquiryType])

  const handleInputChange = (field: keyof FormState, value: string | boolean): void => {
    setFormState((current) => ({
      ...current,
      [field]: value,
    }))

    setErrors((current) => ({
      ...current,
      [field]: undefined,
    }))
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setSubmissionError(null)
    setSubmissionMessage(null)

    const nextErrors = validateForm(formState, inquiryType)
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }

    setSubmitting(true)

    const payload: LeadSubmissionPayload = {
      inquiryType,
      fullName: formState.fullName,
      workEmail: formState.workEmail,
      organization: formState.organization,
      role: formState.role,
      message: formState.message,
      source: utm.source,
      medium: utm.medium,
      campaign: utm.campaign,
      term: utm.term,
      content: utm.content,
      noPhiConfirmation: true,
      honeypot: formState.honeypot,
    }

    try {
      const response = await fetch('/api/forms/submit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const responseJson = (await response.json().catch(() => null)) as { message?: string } | null
        throw new Error(responseJson?.message ?? 'Submission failed. Please try again later.')
      }

      setFormState(initialFormState)
      setSubmissionMessage('Thanks. We received your request and will follow up soon.')
      trackEvent('form_submission_success', {
        inquiry_type: inquiryType,
        utm_source: utm.source,
        utm_medium: utm.medium,
        utm_campaign: utm.campaign,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unexpected error while submitting.'
      setSubmissionError(message)
      trackEvent('form_submission_error', {
        inquiry_type: inquiryType,
        message,
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="lead-form" noValidate onSubmit={handleSubmit}>
      <label htmlFor="fullName">
        Full name
        <input
          autoComplete="name"
          id="fullName"
          name="fullName"
          onChange={(event) => handleInputChange('fullName', event.target.value)}
          required
          type="text"
          value={formState.fullName}
        />
        {errors.fullName ? <span className="field-error">{errors.fullName}</span> : null}
      </label>

      <label htmlFor="workEmail">
        Work email
        <input
          autoComplete="email"
          id="workEmail"
          name="workEmail"
          onChange={(event) => handleInputChange('workEmail', event.target.value)}
          required
          type="email"
          value={formState.workEmail}
        />
        {errors.workEmail ? <span className="field-error">{errors.workEmail}</span> : null}
      </label>

      <label htmlFor="organization">
        Organization
        <input
          autoComplete="organization"
          id="organization"
          name="organization"
          onChange={(event) => handleInputChange('organization', event.target.value)}
          required
          type="text"
          value={formState.organization}
        />
        {errors.organization ? <span className="field-error">{errors.organization}</span> : null}
      </label>

      <label htmlFor="role">
        Role or team
        <input
          autoComplete="organization-title"
          id="role"
          name="role"
          onChange={(event) => handleInputChange('role', event.target.value)}
          required
          type="text"
          value={formState.role}
        />
        {errors.role ? <span className="field-error">{errors.role}</span> : null}
      </label>

      <label htmlFor="message">
        Message
        <textarea
          id="message"
          name="message"
          onChange={(event) => handleInputChange('message', event.target.value)}
          placeholder="Describe your use case or question"
          rows={6}
          value={formState.message}
        />
        {errors.message ? <span className="field-error">{errors.message}</span> : null}
      </label>

      <div aria-hidden="true" className="honeypot-wrap">
        <label htmlFor="honeypot">
          Leave this field blank
          <input
            id="honeypot"
            name="honeypot"
            onChange={(event) => handleInputChange('honeypot', event.target.value)}
            tabIndex={-1}
            type="text"
            value={formState.honeypot}
          />
        </label>
      </div>

      <label className="checkbox-row" htmlFor="noPhiConfirmation">
        <input
          checked={formState.noPhiConfirmation}
          id="noPhiConfirmation"
          name="noPhiConfirmation"
          onChange={(event) => handleInputChange('noPhiConfirmation', event.target.checked)}
          type="checkbox"
        />
        I confirm this message contains no PHI.
      </label>
      {errors.noPhiConfirmation ? <span className="field-error">{errors.noPhiConfirmation}</span> : null}

      <p className="privacy-note">
        We use this form only for onboarding and support routing. Do not submit patient identifiers or clinical records.
      </p>

      <button className="button button-primary" disabled={submitting} type="submit">
        {submitting ? 'Submitting...' : submitLabel}
      </button>

      <div aria-live="polite" className="submission-status" role="status">
        {submissionMessage ? <p className="submission-success">{submissionMessage}</p> : null}
        {submissionError ? <p className="submission-error">{submissionError}</p> : null}
      </div>
    </form>
  )
}
