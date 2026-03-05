'use client'

import { BookOpen, Clock, Globe } from './icons'

import { ScrollReveal, StaggerItem, StaggerReveal } from './scroll-reveal'

const PROBLEMS = [
  {
    icon: BookOpen,
    title: "Reference Managers Don't Read",
    body: "Tools like Zotero and Mendeley store papers but can't extract biological meaning. They manage your library — they don't understand it. Every insight still requires a human to read, tag, and connect.",
  },
  {
    icon: Globe,
    title: 'Global Databases Are Too Noisy',
    body: "PubMed, STRING, and BioGRID aggregate everything, indiscriminately. Your lab's specific targets drown in millions of irrelevant interactions. Filtering consumes the research time that discovery should use.",
  },
  {
    icon: Clock,
    title: 'Manual Literature Reviews Decay',
    body: 'A review completed in Q1 is already incomplete by Q3. New biology publications arrive every day. No team can read fast enough. Static reviews are snapshots — Artana.bio keeps knowledge alive.',
  },
] as const

export function FigmaProblemSection(): JSX.Element {
  return (
    <section
      style={{
        background: '#F9F8F6',
        paddingTop: 96,
        paddingBottom: 96,
        borderTop: '1px solid #EEE9E2',
        borderBottom: '1px solid #EEE9E2',
      }}
    >
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 32px' }}>
        <ScrollReveal style={{ maxWidth: 760, marginBottom: 60 }}>
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
            The Problem
          </span>
          <h2
            style={{
              fontFamily: "'Manrope', sans-serif",
              fontWeight: 700,
              fontSize: 'clamp(28px, 3.5vw, 40px)',
              lineHeight: 1.18,
              letterSpacing: '-0.8px',
              color: '#0B0F1A',
              marginBottom: 16,
            }}
          >
            Biology moves too fast for static tools.
          </h2>
          <p
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 16,
              lineHeight: 1.7,
              color: '#6B7280',
            }}
          >
            Every week your team spends performing manual curation is a week behind the literature. Existing tools were
            built for document storage, not biological reasoning.
          </p>
        </ScrollReveal>

        <StaggerReveal
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 24,
          }}
        >
          {PROBLEMS.map((p) => {
            const Icon = p.icon
            return (
              <StaggerItem key={p.title}>
                <div
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#CBD5E1'
                    e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.06)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#E9EDF2'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                  style={{
                    background: 'white',
                    border: '1px solid #E9EDF2',
                    borderRadius: 12,
                    padding: '32px 28px',
                    height: '100%',
                    transition: 'border-color 0.2s, box-shadow 0.2s',
                  }}
                >
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 10,
                      background: '#F1F5F9',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginBottom: 20,
                    }}
                  >
                    <Icon color="#475569" size={18} strokeWidth={1.75} />
                  </div>
                  <h3
                    style={{
                      fontFamily: "'Manrope', sans-serif",
                      fontWeight: 700,
                      fontSize: 17,
                      lineHeight: 1.3,
                      color: '#0B0F1A',
                      marginBottom: 12,
                      letterSpacing: '-0.2px',
                    }}
                  >
                    {p.title}
                  </h3>
                  <p
                    style={{
                      fontFamily: "'IBM Plex Sans', sans-serif",
                      fontSize: 15,
                      lineHeight: 1.68,
                      color: '#64748B',
                    }}
                  >
                    {p.body}
                  </p>
                </div>
              </StaggerItem>
            )
          })}
        </StaggerReveal>
      </div>
    </section>
  )
}
