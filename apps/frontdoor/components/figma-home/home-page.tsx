import { FigmaFeaturesSection } from './features-section'
import { FigmaFinalCta } from './final-cta'
import { FigmaFooter } from './footer'
import { FigmaHero } from './hero'
import { FigmaHowItWorks } from './how-it-works'
import { FigmaNav } from './nav'
import { FigmaProblemSection } from './problem-section'
import { FigmaProductIntro } from './product-intro'
import { FigmaSecuritySection } from './security-section'

export function FigmaHomePage(): JSX.Element {
  return (
    <div
      style={{
        fontFamily: "'IBM Plex Sans', sans-serif",
        WebkitFontSmoothing: 'antialiased',
        MozOsxFontSmoothing: 'grayscale',
        minHeight: '100vh',
        background: '#080C14',
      }}
    >
      <FigmaNav />

      <main id="main-content">
        <FigmaHero />
        <FigmaProductIntro />
        <FigmaProblemSection />
        <FigmaFeaturesSection />
        <FigmaHowItWorks />
        <FigmaSecuritySection />
        <FigmaFinalCta />
      </main>

      <FigmaFooter />
    </div>
  )
}
