'use client'

import { ArrowRight, MessageSquare } from './icons'
import { motion } from '@/lib/motion-compat'

import { ScrollReveal } from './scroll-reveal'

export function FigmaFinalCta(): JSX.Element {
  return (
    <section
      id="request-access"
      style={{ background: '#0B0F1A', paddingTop: 96, paddingBottom: 96, position: 'relative', overflow: 'hidden' }}
    >
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.025) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
          pointerEvents: 'none',
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          bottom: -100,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 700,
          height: 400,
          borderRadius: '50%',
          background: 'radial-gradient(ellipse, rgba(13,148,136,0.12) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      <ScrollReveal style={{ maxWidth: 680, margin: '0 auto', padding: '0 32px', textAlign: 'center', position: 'relative' }}>
        <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#5EEAD4', letterSpacing: '0.1em', textTransform: 'uppercase', display: 'block', marginBottom: 16 }}>
          Get Started
        </span>
        <h2 style={{ fontFamily: "'Manrope', sans-serif", fontWeight: 800, fontSize: 'clamp(30px, 4.5vw, 52px)', lineHeight: 1.1, letterSpacing: '-1.2px', color: '#F8FAFC', marginBottom: 20 }}>
          Stop searching the literature. <span style={{ color: '#5EEAD4' }}>Start computing it.</span>
        </h2>
        <p style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 17, lineHeight: 1.7, color: '#64748B', margin: '0 auto 44px', maxWidth: 520 }}>
          Join research teams at leading institutions who have replaced manual literature workflows with Artana.bio&apos;s
          computable knowledge graph.
        </p>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'center', marginBottom: 20 }}>
          <motion.a
            href="/request-access"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '14px 26px', background: '#0D9488', color: 'white', borderRadius: 8, textDecoration: 'none', fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 15, fontWeight: 600, letterSpacing: '-0.1px', boxShadow: '0 2px 8px rgba(13,148,136,0.35)' }}
            whileHover={{ background: '#0F766E', y: -2 }}
            whileTap={{ scale: 0.98 }}
          >
            Get Early Access
            <ArrowRight size={16} />
          </motion.a>
          <motion.a
            href="/contact"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '14px 24px', border: '1.5px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#CBD5E1', fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 15, fontWeight: 600, textDecoration: 'none', letterSpacing: '-0.1px' }}
            whileHover={{ borderColor: 'rgba(94,234,212,0.3)', color: '#5EEAD4' }}
            whileTap={{ scale: 0.98 }}
          >
            <MessageSquare size={15} />
            Talk to Our Team
          </motion.a>
        </div>

      </ScrollReveal>
    </section>
  )
}
