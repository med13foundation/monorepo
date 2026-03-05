import { TrackedLink } from '@/components/tracked-link'

export default function NotFoundPage(): JSX.Element {
  return (
    <section className="page-section">
      <div className="site-container page-intro">
        <h1>Page not found</h1>
        <p>The link may be outdated. Use one of the main routes below.</p>
        <div className="hero-actions" style={{ marginTop: '1rem' }}>
          <TrackedLink className="button button-primary" eventLabel="404_home" href="/">
            Go to home
          </TrackedLink>
          <TrackedLink className="button button-secondary" eventLabel="404_contact" href="/contact">
            Contact team
          </TrackedLink>
        </div>
      </div>
    </section>
  )
}
