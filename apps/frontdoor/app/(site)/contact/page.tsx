import { CTABand } from '@/components/cta-band'
import { LeadForm } from '@/components/lead-form'
import { buildMetadata } from '@/lib/metadata'
import { siteConfig } from '@/lib/site-config'
import { Suspense } from 'react'

export const metadata = buildMetadata({
  title: 'Contact | Artana.bio',
  description: 'Contact the Artana.bio platform team for product, architecture, or security questions.',
  path: '/contact',
})

export default function ContactPage(): JSX.Element {
  return (
    <>
      <section className="page-section">
        <div className="site-container page-intro">
          <h1>Contact Artana.bio</h1>
          <p>
            Send onboarding, architecture, or security questions to the platform team. This public form is for
            high-level coordination only and must not include PHI.
          </p>
        </div>

        <div className="site-container">
          <Suspense fallback={null}>
            <LeadForm inquiryType="contact" />
          </Suspense>
        </div>
      </section>

      <CTABand
        primaryHref="/request-access"
        primaryLabel="Request access"
        secondaryExternal
        secondaryHref={siteConfig.docsUrl}
        secondaryLabel="Read docs"
        summary="If you are ready for hands-on evaluation, use access onboarding to route your team."
        title="Need implementation access instead of general contact?"
      />
    </>
  )
}
