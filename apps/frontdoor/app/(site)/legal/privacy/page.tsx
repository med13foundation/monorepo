import { CTABand } from '@/components/cta-band'
import { buildMetadata } from '@/lib/metadata'
import { siteConfig } from '@/lib/site-config'

export const metadata = buildMetadata({
  title: 'Privacy | Artana.bio',
  description: 'Privacy notice for the Artana.bio front door website.',
  path: '/legal/privacy',
})

export default function PrivacyPage(): JSX.Element {
  return (
    <>
      <section className="page-section">
        <div className="site-container page-intro">
          <h1>Privacy notice</h1>
          <p>Last updated: 2026-02-27</p>
        </div>

        <div className="site-container grid-2">
          <article className="card">
            <h2>Data we process on this website</h2>
            <ul>
              <li>Basic analytics events (page views, CTA clicks, form submission outcomes).</li>
              <li>Form submission data for contact and access requests.</li>
              <li>UTM attribution parameters when present.</li>
            </ul>
          </article>

          <article className="card">
            <h2>Restrictions and safeguards</h2>
            <ul>
              <li>No PHI should be submitted through public forms.</li>
              <li>Form payloads are schema-validated server-side before forwarding.</li>
              <li>Submission attempts are rate-limited and logged for abuse prevention.</li>
            </ul>
          </article>
        </div>
      </section>

      <CTABand
        primaryHref="/contact"
        primaryLabel="Contact team"
        secondaryExternal
        secondaryHref={siteConfig.docsUrl}
        secondaryLabel="Read docs"
        summary="Need details on data handling for onboarding workflows?"
        title="Questions about front door data usage"
      />
    </>
  )
}
