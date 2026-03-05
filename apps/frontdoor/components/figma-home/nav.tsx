import Link from 'next/link'

import { siteConfig } from '@/lib/site-config'

import { LogoHorizontal } from './artana-logo'

const NAV_LINKS = [
  { label: 'Research Space', href: '/#research-space' },
  { label: 'Security', href: '/security' },
  { label: 'Mission', href: '/platform' },
] as const

export function FigmaNav(): JSX.Element {
  return (
    <header className="fg-nav-shell">
      <div className="fg-nav-inner">
        <Link className="fg-brand" href="/#hero">
          <LogoHorizontal size="sm" />
        </Link>

        <nav aria-label="Primary navigation" className="fg-nav-links">
          {NAV_LINKS.map((link) => (
            <Link className="fg-nav-link" href={link.href} key={link.label}>
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="fg-nav-actions">
          <a className="fg-nav-signin" href={siteConfig.adminUrl} rel="noopener noreferrer" target="_blank">
            Sign In
          </a>
          <Link className="fg-nav-cta" href="/request-access">
            Request Access
          </Link>
        </div>
      </div>

      <style>{`
        .fg-nav-shell {
          backdrop-filter: blur(16px);
          background: rgba(8, 12, 20, 0.9);
          border-bottom: 1px solid rgba(30, 42, 63, 0.9);
          position: sticky;
          top: 0;
          z-index: 50;
        }

        .fg-nav-inner {
          align-items: center;
          display: grid;
          gap: 1rem;
          grid-template-columns: auto 1fr auto;
          height: 64px;
          margin: 0 auto;
          max-width: 1200px;
          padding: 0 32px;
        }

        .fg-brand {
          align-items: center;
          display: inline-flex;
          text-decoration: none;
        }

        .fg-nav-links {
          align-items: center;
          display: flex;
          gap: 2px;
          margin-left: 12px;
        }

        .fg-nav-link {
          align-items: center;
          border-radius: 6px;
          color: #94a3b8;
          display: inline-flex;
          font-family: 'IBM Plex Sans', sans-serif;
          font-size: 14px;
          font-weight: 500;
          padding: 6px 14px;
          text-decoration: none;
          transition: color 0.15s, background-color 0.15s;
        }

        .fg-nav-link:hover,
        .fg-nav-link:focus-visible {
          background: rgba(255, 255, 255, 0.08);
          color: #f8fafc;
        }

        .fg-nav-actions {
          align-items: center;
          display: flex;
          gap: 8px;
        }

        .fg-nav-signin {
          border-radius: 7px;
          color: #94a3b8;
          font-family: 'IBM Plex Sans', sans-serif;
          font-size: 14px;
          font-weight: 500;
          padding: 7px 16px;
          text-decoration: none;
          transition: color 0.15s;
        }

        .fg-nav-signin:hover,
        .fg-nav-signin:focus-visible {
          color: #f8fafc;
        }

        .fg-nav-cta {
          background: #0d9488;
          border-radius: 7px;
          box-shadow: 0 1px 3px rgba(13, 148, 136, 0.25);
          color: #ffffff;
          font-family: 'IBM Plex Sans', sans-serif;
          font-size: 14px;
          font-weight: 600;
          letter-spacing: -0.1px;
          padding: 8px 18px;
          text-decoration: none;
          transition: background-color 0.15s, box-shadow 0.15s;
        }

        .fg-nav-cta:hover,
        .fg-nav-cta:focus-visible {
          background: #0f766e;
          box-shadow: 0 2px 8px rgba(13, 148, 136, 0.35);
        }

        @media (max-width: 900px) {
          .fg-nav-inner {
            grid-template-columns: auto auto;
          }

          .fg-nav-links {
            display: none;
          }
        }

        @media (max-width: 640px) {
          .fg-nav-inner {
            padding: 0 20px;
          }

          .fg-nav-signin {
            display: none;
          }

          .fg-nav-cta {
            padding: 8px 14px;
          }
        }
      `}</style>
    </header>
  )
}
