import { siteConfig } from '@/lib/site-config'

import { TrackedLink } from './tracked-link'

type FooterColumn = {
  heading: string
  links: { label: string; href: string; external?: boolean }[]
}

const footerColumns: FooterColumn[] = [
  {
    heading: 'Platform',
    links: [
      { label: 'Platform', href: '/platform' },
      { label: 'Security', href: '/security' },
      { label: 'Request Access', href: '/request-access' },
    ],
  },
  {
    heading: 'Resources',
    links: [
      { label: 'Docs', href: siteConfig.docsUrl, external: true },
      { label: 'Admin Login', href: siteConfig.adminUrl, external: true },
      { label: 'Contact', href: '/contact' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy', href: '/legal/privacy' },
      { label: 'Terms', href: '/legal/terms' },
    ],
  },
]

export const SiteFooter = (): JSX.Element => {
  return (
    <footer className="site-footer">
      <div className="site-container footer-grid">
        <div>
          <p className="footer-brand">Artana.bio</p>
          <p className="footer-note">Domain-agnostic research infrastructure, biomedical-first deployment.</p>
          <a className="footer-email" href={`mailto:${siteConfig.supportEmail}`}>
            {siteConfig.supportEmail}
          </a>
        </div>

        {footerColumns.map((column) => (
          <div className="footer-links" key={column.heading}>
            <p className="footer-heading">{column.heading}</p>
            {column.links.map((link) => (
              <TrackedLink
                eventCategory="footer"
                eventLabel={`footer_${link.label.toLowerCase().replace(/\s+/g, '_')}`}
                external={link.external}
                href={link.href}
                key={link.label}
              >
                {link.label}
              </TrackedLink>
            ))}
          </div>
        ))}
      </div>
      <div className="site-container footer-bottom">
        <p>© 2026 Artana.bio. All rights reserved.</p>
        <p>Private by default · Audit-ready architecture · Enterprise controls available.</p>
      </div>
    </footer>
  )
}
