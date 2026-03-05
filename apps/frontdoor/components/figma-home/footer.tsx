import Link from 'next/link'

import { siteConfig } from '@/lib/site-config'

import { LogoHorizontal } from './artana-logo'

const FOOTER_COLS = [
  {
    heading: 'Research Space',
    links: [
      { label: 'Product Overview', href: '/#research-space' },
      { label: 'Knowledge Graph', href: '/#features' },
      { label: 'Agentic Discovery', href: '/#features' },
      { label: 'Multiplayer Curation', href: '/#features' },
      { label: 'Request Access', href: '/request-access' },
    ],
  },
  {
    heading: 'Security',
    links: [
      { label: 'Security Overview', href: '/security' },
      { label: 'Compliance', href: '/security' },
      { label: 'Trust Center', href: '/security' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'Our Mission', href: '/platform' },
      { label: 'Contact', href: '/contact' },
      { label: 'Documentation', href: siteConfig.docsUrl, external: true },
      { label: 'Admin Login', href: siteConfig.adminUrl, external: true },
      { label: 'Privacy Policy', href: '/legal/privacy' },
      { label: 'Terms of Service', href: '/legal/terms' },
    ],
  },
] as const

export function FigmaFooter(): JSX.Element {
  return (
    <footer className="fg-footer-shell">
      <div className="fg-footer-inner">
        <div className="fg-footer-top">
          <div>
            <Link className="fg-footer-brand-link" href="/#hero">
              <LogoHorizontal size="sm" />
            </Link>
            <p className="fg-footer-note">AI and biology infrastructure for rare disease research.</p>
            <div className="fg-footer-email-wrap">
              <a className="fg-footer-email" href={`mailto:${siteConfig.supportEmail}`}>
                {siteConfig.supportEmail}
              </a>
            </div>
          </div>

          <div className="fg-footer-cols">
            {FOOTER_COLS.map((col) => (
              <div key={col.heading}>
                <p className="fg-footer-heading">{col.heading}</p>
                <ul className="fg-footer-list">
                  {col.links.map((link) => {
                    const isExternal = 'external' in link && Boolean(link.external)

                    return (
                      <li key={link.label}>
                        {isExternal ? (
                          <a className="fg-footer-link" href={link.href} rel="noopener noreferrer" target="_blank">
                            {link.label}
                          </a>
                        ) : (
                          <Link className="fg-footer-link" href={link.href}>
                            {link.label}
                          </Link>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="fg-footer-bottom">
          <p>© 2026 Artana.bio. All rights reserved.</p>
        </div>
      </div>

      <style>{`
        .fg-footer-shell {
          background: #050810;
          border-top: 1px solid #0f1623;
          font-family: 'IBM Plex Sans', sans-serif;
          padding: 64px 0 40px;
        }

        .fg-footer-inner {
          margin: 0 auto;
          max-width: 1200px;
          padding: 0 32px;
        }

        .fg-footer-top {
          display: grid;
          gap: 64px;
          grid-template-columns: 220px 1fr;
          margin-bottom: 56px;
        }

        .fg-footer-brand-link {
          align-items: center;
          display: inline-flex;
          margin-bottom: 16px;
          text-decoration: none;
        }

        .fg-footer-note {
          color: #334155;
          font-size: 13px;
          line-height: 1.6;
          max-width: 180px;
        }

        .fg-footer-email-wrap {
          margin-top: 16px;
        }

        .fg-footer-email {
          color: #475569;
          font-size: 12px;
          text-decoration: none;
          transition: color 0.15s;
        }

        .fg-footer-email:hover,
        .fg-footer-email:focus-visible {
          color: #5eead4;
        }

        .fg-footer-cols {
          display: grid;
          gap: 32px;
          grid-template-columns: repeat(4, minmax(0, 1fr));
        }

        .fg-footer-heading {
          color: #475569;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.08em;
          margin-bottom: 14px;
          text-transform: uppercase;
        }

        .fg-footer-list {
          display: flex;
          flex-direction: column;
          gap: 9px;
          list-style: none;
          margin: 0;
          padding: 0;
        }

        .fg-footer-link {
          color: #475569;
          font-size: 13px;
          text-decoration: none;
          transition: color 0.15s;
        }

        .fg-footer-link:hover,
        .fg-footer-link:focus-visible {
          color: #cbd5e1;
        }

        .fg-footer-bottom {
          align-items: center;
          border-top: 1px solid #0f1623;
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          justify-content: space-between;
          padding-top: 24px;
        }

        .fg-footer-bottom p {
          color: #1e2d3d;
          font-size: 12px;
          margin: 0;
        }

        @media (max-width: 900px) {
          .fg-footer-top {
            gap: 40px;
            grid-template-columns: 1fr;
          }

          .fg-footer-cols {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 640px) {
          .fg-footer-inner {
            padding: 0 20px;
          }

          .fg-footer-cols {
            gap: 24px;
          }

          .fg-footer-bottom {
            align-items: flex-start;
            flex-direction: column;
          }
        }
      `}</style>
    </footer>
  )
}
