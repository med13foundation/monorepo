'use client'

import { useEffect, useState } from 'react'

import { siteConfig } from '@/lib/site-config'

import { TrackedLink } from './tracked-link'

export const SiteHeader = (): JSX.Element => {
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = (): void => {
      setScrolled(window.scrollY > 8)
    }

    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })

    return () => {
      window.removeEventListener('scroll', onScroll)
    }
  }, [])

  return (
    <header className={`site-header ${scrolled ? 'is-scrolled' : ''}`}>
      <div className="site-container header-inner">
        <TrackedLink ariaLabel="Go to homepage" className="brand" eventCategory="navigation" eventLabel="brand_home" href="/">
          <span className="brand-mark" aria-hidden="true">
            <svg fill="none" height="26" viewBox="0 0 28 28" width="26" xmlns="http://www.w3.org/2000/svg">
              <rect fill="#0D9488" height="28" rx="7" width="28" />
              <circle cx="14" cy="10" fill="white" r="3" />
              <circle cx="8" cy="20" fill="white" fillOpacity="0.74" r="2.5" />
              <circle cx="20" cy="20" fill="white" fillOpacity="0.74" r="2.5" />
              <line stroke="white" strokeOpacity="0.6" strokeWidth="1.2" x1="14" x2="8" y1="10" y2="20" />
              <line stroke="white" strokeOpacity="0.6" strokeWidth="1.2" x1="14" x2="20" y1="10" y2="20" />
              <line stroke="white" strokeOpacity="0.42" strokeWidth="1" x1="8" x2="20" y1="20" y2="20" />
            </svg>
          </span>
          <span className="brand-text">Artana.bio</span>
        </TrackedLink>

        <button
          aria-controls="frontdoor-nav"
          aria-expanded={menuOpen}
          aria-label="Toggle navigation menu"
          className="menu-button"
          onClick={() => setMenuOpen((value) => !value)}
          type="button"
        >
          {menuOpen ? 'Close' : 'Menu'}
        </button>

        <nav className={`site-nav ${menuOpen ? 'site-nav-open' : ''}`} id="frontdoor-nav">
          <ul>
            {siteConfig.navItems.map((item) => (
              <li key={item.label} onClick={() => setMenuOpen(false)}>
                <TrackedLink
                  className="nav-link"
                  eventCategory="navigation"
                  eventLabel={`nav_${item.label.toLowerCase().replace(/\s+/g, '_')}`}
                  external={item.external}
                  href={item.href}
                >
                  {item.label}
                </TrackedLink>
              </li>
            ))}
            <li onClick={() => setMenuOpen(false)}>
              <TrackedLink className="button button-primary header-primary" eventLabel="nav_request_access" href="/request-access">
                Request access
              </TrackedLink>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  )
}
