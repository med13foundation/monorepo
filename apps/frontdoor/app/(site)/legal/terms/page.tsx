import { CTABand } from '@/components/cta-band'
import { buildMetadata } from '@/lib/metadata'
import { siteConfig } from '@/lib/site-config'

export const metadata = buildMetadata({
  title: 'Terms | Artana.bio',
  description: 'Terms of use for the Artana.bio front door website.',
  path: '/legal/terms',
})

export default function TermsPage(): JSX.Element {
  return (
    <>
      <section className="page-section">
        <div className="site-container page-intro">
          <h1>Terms of use</h1>
          <p>Last updated: 2026-02-27</p>
        </div>

        <div className="site-container grid-2">
          <article className="card">
            <h2>Use of this website</h2>
            <ul>
              <li>Use content for evaluation and onboarding decisions.</li>
              <li>Do not submit protected health information through forms.</li>
              <li>Do not attempt unauthorized access or disruption.</li>
            </ul>
          </article>

          <article className="card">
            <h2>Service boundaries</h2>
            <ul>
              <li>This front door is a public informational service.</li>
              <li>Authenticated workflows are hosted in the Artana.bio admin service.</li>
              <li>Backend API operations are governed by separate platform controls.</li>
            </ul>
          </article>
        </div>
      </section>

      <CTABand
        primaryHref="/request-access"
        primaryLabel="Request access"
        secondaryExternal
        secondaryHref={siteConfig.adminUrl}
        secondaryLabel="Admin login"
        summary="Ready to move from terms review to platform onboarding?"
        title="Continue to the correct product surface"
      />
    </>
  )
}
