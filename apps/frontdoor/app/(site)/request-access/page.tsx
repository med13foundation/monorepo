import { CTABand } from '@/components/cta-band'
import { LeadForm } from '@/components/lead-form'
import { buildMetadata } from '@/lib/metadata'
import { siteConfig } from '@/lib/site-config'
import { Suspense } from 'react'

export const metadata = buildMetadata({
  title: 'Request Access | Artana.bio',
  description: 'Request evaluation access for Artana.bio and route your team to the right onboarding flow.',
  path: '/request-access',
})

export default function RequestAccessPage(): JSX.Element {
  return (
    <>
      <section className="page-section">
        <div className="site-container page-intro">
          <h1>Request platform access</h1>
          <p>
            Tell us your organization, use case, and timeline. We will route your request to the right onboarding path
            and provide next steps.
          </p>
        </div>

        <div className="site-container">
          <Suspense fallback={null}>
            <LeadForm inquiryType="request_access" />
          </Suspense>
        </div>
      </section>

      <CTABand
        primaryHref="/contact"
        primaryLabel="Contact team"
        secondaryExternal
        secondaryHref={siteConfig.docsUrl}
        secondaryLabel="Browse docs"
        summary="Have procurement, compliance, or technical questions before requesting access?"
        title="Need a conversation first"
      />
    </>
  )
}
