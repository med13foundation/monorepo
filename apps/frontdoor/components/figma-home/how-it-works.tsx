'use client'

import { ScrollReveal, StaggerItem, StaggerReveal } from './scroll-reveal'

const STEPS = [
  {
    num: '01',
    title: 'Initialize Space',
    body: 'Define your domain — a target, pathway, or disease context. Artana.bio scopes the knowledge graph to your research question from day one.',
  },
  {
    num: '02',
    title: 'Autonomous Ingestion',
    body: 'The engine continuously monitors PubMed, preprint servers, and curated repositories. New relevant papers are ingested within hours of publication.',
  },
  {
    num: '03',
    title: 'Strict Extraction & Normalization',
    body: 'Named entity recognition and relation extraction pull precise biological assertions from full text. Entities are normalized to standard ontologies — no ambiguous synonyms.',
  },
  {
    num: '04',
    title: 'Agentic Discovery',
    body: "Query your graph in natural language, explore computed connections, or let the agentic layer surface unexpected relationships your team didn't know to look for.",
  },
] as const

export function FigmaHowItWorks(): JSX.Element {
  return (
    <section
      id="how-it-works"
      style={{
        background: '#F9F8F6',
        paddingTop: 96,
        paddingBottom: 96,
        borderTop: '1px solid #EEE9E2',
        borderBottom: '1px solid #EEE9E2',
      }}
    >
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 32px' }}>
        <ScrollReveal style={{ textAlign: 'center', maxWidth: 600, margin: '0 auto 72px' }}>
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
            How It Works
          </span>
          <h2
            style={{
              fontFamily: "'Manrope', sans-serif",
              fontWeight: 700,
              fontSize: 'clamp(26px, 3.2vw, 38px)',
              lineHeight: 1.18,
              letterSpacing: '-0.7px',
              color: '#0B0F1A',
            }}
          >
            From unstructured text to computable biology in minutes.
          </h2>
        </ScrollReveal>

        <StaggerReveal className="steps-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0, position: 'relative' }}>
          <div
            aria-hidden="true"
            className="connector-line"
            style={{
              position: 'absolute',
              top: 26,
              left: 'calc(12.5% + 24px)',
              right: 'calc(12.5% + 24px)',
              height: 1,
              background: '#CBD5E1',
              zIndex: 0,
            }}
          />
          {STEPS.map((step, i) => (
            <StaggerItem direction="up" key={step.num}>
              <div
                className="step-inner"
                style={{
                  position: 'relative',
                  zIndex: 1,
                  padding: '0 24px',
                  textAlign: 'center',
                }}
              >
                <div
                  className="step-bubble"
                  style={{
                    width: 56,
                    height: 56,
                    borderRadius: '50%',
                    background: i === 0 ? '#0D9488' : 'white',
                    border: `2px solid ${i === 0 ? '#0D9488' : '#CBD5E1'}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 28px',
                    transition: 'border-color 0.2s, background 0.2s',
                  }}
                >
                  <span
                    style={{
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: 14,
                      fontWeight: 600,
                      color: i === 0 ? 'white' : '#0D9488',
                      letterSpacing: '0.02em',
                    }}
                  >
                    {step.num}
                  </span>
                </div>
                <div className="step-body">
                  <h3
                    style={{
                      fontFamily: "'Manrope', sans-serif",
                      fontWeight: 700,
                      fontSize: 16,
                      lineHeight: 1.3,
                      color: '#0B0F1A',
                      marginBottom: 10,
                      letterSpacing: '-0.2px',
                    }}
                  >
                    {step.title}
                  </h3>
                  <p
                    style={{
                      fontFamily: "'IBM Plex Sans', sans-serif",
                      fontSize: 14,
                      lineHeight: 1.65,
                      color: '#64748B',
                    }}
                  >
                    {step.body}
                  </p>
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerReveal>
      </div>

      <style>{`
        @media (max-width: 768px) {
          .steps-grid { grid-template-columns: 1fr !important; gap: 40px !important; }
          .connector-line { display: none !important; }
          .step-inner { text-align: left !important; display: flex !important; align-items: flex-start !important; gap: 20px !important; }
          .step-bubble { margin: 0 !important; flex-shrink: 0; }
          .step-body { text-align: left !important; }
        }
      `}</style>
    </section>
  )
}
