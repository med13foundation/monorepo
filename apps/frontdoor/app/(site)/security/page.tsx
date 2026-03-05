import { CTABand } from '@/components/cta-band'
import { buildMetadata } from '@/lib/metadata'
import { siteConfig } from '@/lib/site-config'

export const metadata = buildMetadata({
  title: 'Security | Artana.bio',
  description:
    'Public security overview for Artana.bio focused on privacy, access control, and responsible operations.',
  path: '/security',
})

export default function SecurityPage(): JSX.Element {
  return (
    <>
      <section className="page-section">
        <div className="site-container page-intro">
          <h1>Security and privacy built for real-world research teams</h1>
          <p>
            Artana.bio is designed to protect research work, respect privacy, and support institutional trust. This
            page explains our security posture in clear terms without exposing internal technical implementation details.
          </p>
        </div>

        <div className="site-container grid-3">
          <article className="card">
            <h3>Private research spaces</h3>
            <p>
              Research spaces are separated by design, so teams can work confidently in their own environment with
              role-based access controls.
            </p>
            <ul>
              <li>Role-based permissions for team members.</li>
              <li>Access boundaries aligned to workspace ownership.</li>
              <li>Controls designed for least-privilege access.</li>
            </ul>
          </article>
          <article className="card">
            <h3>Protected data handling</h3>
            <p>
              Sensitive data handling follows strict safeguards, including encryption and controlled access patterns for
              higher-risk information.
            </p>
            <ul>
              <li>Encryption for sensitive records.</li>
              <li>Access policies that reduce unnecessary exposure.</li>
              <li>Operational controls for secure rollout and governance.</li>
            </ul>
          </article>
          <article className="card">
            <h3>Traceability and accountability</h3>
            <p>
              Important system actions are recorded to support review, investigations, and compliance workflows when
              needed.
            </p>
            <ul>
              <li>Audit trails for key operations.</li>
              <li>Retention-aware logging practices.</li>
              <li>Operational visibility for security reviews.</li>
            </ul>
          </article>
        </div>
      </section>

      <CTABand
        primaryHref="/contact"
        primaryLabel="Contact security"
        secondaryExternal
        secondaryHref={siteConfig.docsUrl}
        secondaryLabel="Read security docs"
        summary="Need controls mapping, architecture validation, or deployment model details for a review board?"
        title="Align your security review with implementation facts"
      />
    </>
  )
}
