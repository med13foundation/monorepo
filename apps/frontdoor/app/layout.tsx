import type { Metadata } from 'next'
import { IBM_Plex_Sans, Manrope } from 'next/font/google'
import Script from 'next/script'
import { Suspense, type ReactNode } from 'react'

import { AnalyticsTracker } from '@/components/analytics-tracker'
import { buildMetadata } from '@/lib/metadata'
import { siteConfig } from '@/lib/site-config'

import './globals.css'

const headingFont = Manrope({
  subsets: ['latin'],
  weight: ['500', '600', '700', '800'],
  variable: '--font-heading',
})

const bodyFont = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-body',
})

export const metadata: Metadata = buildMetadata({
  title: 'Artana.bio | Domain-agnostic Research Platform',
  description:
    'Understand Artana.bio in minutes. Explore architecture, security controls, and developer onboarding for private, computable research spaces.',
  path: '/',
})

export default function RootLayout({ children }: { children: ReactNode }): JSX.Element {
  const gaMeasurementId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID

  return (
    <html lang="en">
      <body className={`${headingFont.variable} ${bodyFont.variable}`}>
        {gaMeasurementId ? (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${gaMeasurementId}`}
              strategy="afterInteractive"
            />
            <Script id="ga-init" strategy="afterInteractive">
              {`
                window.dataLayer = window.dataLayer || [];
                function gtag(){window.dataLayer.push(arguments);}
                window.gtag = gtag;
                gtag('js', new Date());
                gtag('config', '${gaMeasurementId}', { send_page_view: false });
              `}
            </Script>
          </>
        ) : null}

        <a className="skip-link" href="#main-content">
          Skip to content
        </a>

        <div className="site-background" aria-hidden="true" />
        {children}
        <Suspense fallback={null}>
          <AnalyticsTracker />
        </Suspense>

        <noscript>
          <p className="noscript-note">Analytics requires JavaScript. Core content and forms still work without scripts.</p>
        </noscript>
      </body>
    </html>
  )
}
