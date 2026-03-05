import { TrackedLink } from '@/components/tracked-link'

type CTABandProps = {
  title: string
  summary: string
  primaryLabel: string
  primaryHref: string
  secondaryLabel: string
  secondaryHref: string
  secondaryExternal?: boolean
}

export const CTABand = ({
  title,
  summary,
  primaryLabel,
  primaryHref,
  secondaryLabel,
  secondaryHref,
  secondaryExternal,
}: CTABandProps): JSX.Element => {
  return (
    <section className="cta-band" aria-labelledby="cta-band-title">
      <div className="site-container cta-band-inner">
        <div>
          <h2 id="cta-band-title">{title}</h2>
          <p>{summary}</p>
        </div>
        <div className="cta-actions">
          <TrackedLink className="button button-primary" eventLabel={`cta_primary_${primaryLabel}`} href={primaryHref}>
            {primaryLabel}
          </TrackedLink>
          <TrackedLink
            className="button button-secondary"
            eventLabel={`cta_secondary_${secondaryLabel}`}
            external={secondaryExternal}
            href={secondaryHref}
          >
            {secondaryLabel}
          </TrackedLink>
        </div>
      </div>
    </section>
  )
}
