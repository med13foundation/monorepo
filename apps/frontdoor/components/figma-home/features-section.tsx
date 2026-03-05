'use client'

import { ShieldCheck, Users, Zap } from './icons'
import { motion } from '@/lib/motion-compat'

import { ScrollReveal, StaggerItem, StaggerReveal } from './scroll-reveal'

const FEATURES = [
  {
    icon: Zap,
    tag: 'Evergreen Data Pipelines',
    title: 'Knowledge that updates itself.',
    body: 'Artana.bio continuously monitors the literature and automatically ingests new publications relevant to your Research Space. Your knowledge graph stays current without manual effort — so your team focuses on interpretation, not maintenance.',
    accent: '#0D9488',
  },
  {
    icon: Users,
    tag: 'Multiplayer Curation',
    title: 'Your whole lab, one living graph.',
    body: 'PIs, postdocs, and bioinformaticians collaborate on the same computable knowledge base in real time. Curation decisions are versioned, attributed, and auditable — no more conflicting spreadsheets or siloed annotations.',
    accent: '#0D9488',
  },
  {
    icon: ShieldCheck,
    tag: 'Domain-Isolated Precision',
    title: 'Signal only. No global noise.',
    body: 'Each Research Space is isolated to your domain of interest. Strict entity normalization, confidence scoring, and ontology alignment ensure extracted relationships are precise — never diluted by the noise of public databases.',
    accent: '#0D9488',
  },
] as const

export function FigmaFeaturesSection(): JSX.Element {
  return (
    <section id="features" style={{ background: 'white', paddingTop: 96, paddingBottom: 96 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 32px' }}>
        <ScrollReveal style={{ textAlign: 'center', maxWidth: 680, margin: '0 auto 64px' }}>
          <span
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 11,
              fontWeight: 600,
              color: '#0D9488',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              display: 'block',
              marginBottom: 12,
            }}
          >
            Core Capabilities
          </span>
          <h2
            style={{
              fontFamily: "'Manrope', sans-serif",
              fontWeight: 700,
              fontSize: 'clamp(26px, 3.2vw, 38px)',
              lineHeight: 1.18,
              letterSpacing: '-0.7px',
              color: '#0B0F1A',
              marginBottom: 16,
            }}
          >
            Enter the Research Space: Your Lab&apos;s Private Discovery Engine.
          </h2>
          <p
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 16,
              lineHeight: 1.7,
              color: '#6B7280',
            }}
          >
            Three foundational capabilities that replace fragmented tools with a single, computable source of
            biological truth.
          </p>
        </ScrollReveal>

        <StaggerReveal
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: 24,
          }}
        >
          {FEATURES.map((f) => {
            const Icon = f.icon
            return (
              <StaggerItem key={f.tag}>
                <motion.div
                  style={{
                    border: '1px solid #E2E8F0',
                    borderRadius: 12,
                    overflow: 'hidden',
                    height: '100%',
                    boxShadow: '0 0 0 rgba(0,0,0,0)',
                  }}
                  transition={{ duration: 0.22 }}
                  whileHover={{
                    boxShadow: '0 6px 28px rgba(0,0,0,0.07)',
                    borderColor: '#CBD5E1',
                    y: -3,
                  }}
                >
                  <div style={{ height: 3, background: f.accent, opacity: 0.85 }} />
                  <div style={{ padding: '28px 28px 32px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                      <div
                        style={{
                          width: 36,
                          height: 36,
                          borderRadius: 8,
                          background: '#F0FDFA',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        <Icon color="#0D9488" size={17} strokeWidth={2} />
                      </div>
                      <span
                        style={{
                          fontFamily: "'IBM Plex Sans', sans-serif",
                          fontSize: 11,
                          fontWeight: 600,
                          color: '#0D9488',
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                        }}
                      >
                        {f.tag}
                      </span>
                    </div>
                    <h3
                      style={{
                        fontFamily: "'Manrope', sans-serif",
                        fontWeight: 700,
                        fontSize: 19,
                        lineHeight: 1.3,
                        color: '#0B0F1A',
                        marginBottom: 12,
                        letterSpacing: '-0.3px',
                      }}
                    >
                      {f.title}
                    </h3>
                    <p
                      style={{
                        fontFamily: "'IBM Plex Sans', sans-serif",
                        fontSize: 15,
                        lineHeight: 1.7,
                        color: '#64748B',
                      }}
                    >
                      {f.body}
                    </p>
                  </div>
                </motion.div>
              </StaggerItem>
            )
          })}
        </StaggerReveal>
      </div>
    </section>
  )
}
