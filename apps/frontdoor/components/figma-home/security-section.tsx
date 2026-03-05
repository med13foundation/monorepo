'use client'

import { ArrowRight, EyeOff, ScrollText, Server, ShieldCheck, Users } from './icons'

import { ScrollReveal } from './scroll-reveal'

const PILLARS = [
  {
    icon: EyeOff,
    title: 'Private by default',
    body: 'Data is never shared, indexed, or exposed across tenants. Isolation is enforced at the architecture level — not governed by policy alone.',
  },
  {
    icon: Users,
    title: 'Role-based access controls',
    body: 'Define granular permissions per team member, project, and data class. Access is least-privilege by default and auditable at every layer.',
  },
  {
    icon: ScrollText,
    title: 'Audit logging',
    body: 'Every query, curation action, and permission change is logged with full user attribution and timestamps — ready for institutional review.',
  },
  {
    icon: ShieldCheck,
    title: 'Encrypted data at rest and in transit',
    body: 'AES-256 at rest. TLS 1.3 in transit. Encryption keys are managed per-customer with configurable residency controls.',
  },
  {
    icon: Server,
    title: 'Enterprise deployment options',
    body: 'Deploy to your own cloud environment, on-premises infrastructure, or a dedicated hosted tenant. Full data residency control included.',
  },
] as const

export function FigmaSecuritySection(): JSX.Element {
  return (
    <section
      id="security"
      style={{
        background: '#080C14',
        paddingTop: 96,
        paddingBottom: 96,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `url("data:image/svg+xml,${encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.022)" stroke-width="0.5"/></svg>'
          )}")`,
          backgroundSize: '40px 40px',
          pointerEvents: 'none',
        }}
      />

      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: -140,
          right: -140,
          width: 520,
          height: 520,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(13,148,136,0.05) 0%, transparent 65%)',
          pointerEvents: 'none',
        }}
      />

      <div
        className="security-grid"
        style={{ maxWidth: 920, margin: '0 auto', padding: '0 32px', position: 'relative' }}
      >
        <ScrollReveal direction="left">
          <span
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 11,
              fontWeight: 600,
              color: '#5EEAD4',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              display: 'block',
              marginBottom: 16,
            }}
          >
            Security &amp; Privacy
          </span>

          <h2
            style={{
              fontFamily: "'Manrope', sans-serif",
              fontWeight: 700,
              fontSize: 'clamp(24px, 2.8vw, 34px)',
              lineHeight: 1.2,
              letterSpacing: '-0.5px',
              color: '#F8FAFC',
              marginBottom: 14,
            }}
          >
            Built for regulated, high-stakes science.
          </h2>

          <p
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 16,
              lineHeight: 1.7,
              color: '#64748B',
              marginBottom: 48,
              maxWidth: 480,
            }}
          >
            Enterprise security isn&apos;t a feature tier — it&apos;s a design requirement. Artana Bio is architected from
            the ground up for institutions where access control and data integrity are non-negotiable.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {PILLARS.map((p, i) => {
              const Icon = p.icon
              return (
                <div
                  key={p.title}
                  style={{
                    display: 'flex',
                    gap: 18,
                    paddingTop: i === 0 ? 0 : 24,
                    paddingBottom: i === PILLARS.length - 1 ? 0 : 24,
                    borderBottom: i < PILLARS.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                  }}
                >
                  <div
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: 8,
                      background: 'rgba(13,148,136,0.10)',
                      border: '1px solid rgba(13,148,136,0.18)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: 2,
                    }}
                  >
                    <Icon color="#5EEAD4" size={15} strokeWidth={1.75} />
                  </div>

                  <div>
                    <p
                      style={{
                        fontFamily: "'Manrope', sans-serif",
                        fontWeight: 600,
                        fontSize: 14,
                        color: '#E2E8F0',
                        marginBottom: 4,
                        letterSpacing: '-0.1px',
                      }}
                    >
                      {p.title}
                    </p>
                    <p
                      style={{
                        fontFamily: "'IBM Plex Sans', sans-serif",
                        fontSize: 13,
                        lineHeight: 1.65,
                        color: '#475569',
                      }}
                    >
                      {p.body}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>

          <a
            href="/security"
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(94,234,212,0.35)'
              e.currentTarget.style.background = 'rgba(94,234,212,0.04)'
              e.currentTarget.style.color = '#F1F5F9'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)'
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.color = '#CBD5E1'
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 20px',
              marginTop: 36,
              border: '1.5px solid rgba(255,255,255,0.12)',
              borderRadius: 8,
              color: '#CBD5E1',
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 13,
              fontWeight: 600,
              textDecoration: 'none',
              letterSpacing: '-0.1px',
              transition: 'border-color 0.15s, background 0.15s, color 0.15s',
            }}
          >
            Security overview
            <ArrowRight size={14} />
          </a>
        </ScrollReveal>

      </div>
    </section>
  )
}
