import { CTABand } from '@/components/cta-band'
import { buildMetadata } from '@/lib/metadata'

export const metadata = buildMetadata({
  title: 'Mission | Artana.bio',
  description:
    'Artana.bio exists to support the MED13 Foundation mission with research infrastructure for rare disease discovery.',
  path: '/platform',
})

export default function PlatformPage(): JSX.Element {
  return (
    <>
      <section className="page-section">
        <div className="site-container page-intro">
          <h1>Our mission</h1>
          <p>
            Artana.bio was built to help advance the mission of the MED13 Foundation by giving research teams better
            tools to organize evidence, collaborate, and move faster toward meaningful discoveries.
          </p>
        </div>

        <div className="site-container grid-3">
          <article className="card">
            <h3>Why this work matters</h3>
            <p>
              Rare disease research teams often face fragmented data, long review cycles, and limited resources.
              Better infrastructure can reduce friction and increase research velocity.
            </p>
            <ul>
              <li>Faster access to relevant evidence.</li>
              <li>More coordination across labs and collaborators.</li>
              <li>Clearer research context for decision-making.</li>
            </ul>
          </article>

          <article className="card">
            <h3>Built to support MED13 Foundation</h3>
            <p>
              Artana.bio is designed to support the MED13 Foundation&apos;s efforts to accelerate research and improve
              outcomes for the MED13 community.
            </p>
            <ul>
              <li>
                Learn more about the foundation at{' '}
                <a href="https://med13.org" rel="noopener noreferrer" target="_blank">
                  med13.org
                </a>
                .
              </li>
              <li>Aligned with patient-centered research priorities.</li>
              <li>Focused on real scientific and clinical impact.</li>
            </ul>
          </article>

          <article className="card">
            <h3>How Artana.bio helps</h3>
            <p>
              We provide a shared research environment where teams can track findings, connect evidence, and keep
              discovery work moving in one direction.
            </p>
            <ul>
              <li>Continuously updated research context.</li>
              <li>Collaboration-ready workflows for distributed teams.</li>
              <li>A clear path from literature to hypothesis generation.</li>
            </ul>
          </article>
        </div>
      </section>

      <section className="page-section">
        <div className="site-container grid-2">
          <article className="card">
            <h2>Our principles</h2>
            <ul>
              <li>Patient-centered purpose.</li>
              <li>Scientific integrity and transparency.</li>
              <li>Responsible use of AI in research workflows.</li>
            </ul>
          </article>
          <article className="card">
            <h2>What success looks like</h2>
            <ul>
              <li>More time spent on science, less on manual curation.</li>
              <li>Faster hypothesis-to-experiment cycles.</li>
              <li>Stronger collaboration between researchers and foundations.</li>
            </ul>
          </article>
        </div>
      </section>

      <CTABand
        primaryHref="/request-access"
        primaryLabel="Work with us"
        secondaryExternal
        secondaryHref="https://med13.org"
        secondaryLabel="Visit MED13 Foundation"
        summary="We collaborate with researchers, partners, and mission-driven organizations advancing rare disease work."
        title="Join the mission"
      />
    </>
  )
}
