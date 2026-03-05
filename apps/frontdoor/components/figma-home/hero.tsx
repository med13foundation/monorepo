'use client'

import { ArrowRight, ChevronRight } from './icons'
import { motion } from '@/lib/motion-compat'

const EASE = [0.22, 1, 0.36, 1] as const

const fadeUp = (delay: number): { initial: { opacity: number; y: number }; animate: { opacity: number; y: number }; transition: { duration: number; delay: number; ease: readonly [number, number, number, number] } } => ({
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.62, delay, ease: EASE },
})

const HERO_STATS = [
  {
    value: '10,000+',
    label: 'Rare diseases identified worldwide',
  },
  {
    value: '30M+',
    label: 'People in the U.S. living with a rare disease',
  },
  {
    value: '~95%',
    label: 'Rare diseases without an FDA-approved treatment',
  },
] as const

export function FigmaHero(): JSX.Element {
  return (
    <section
      id="hero"
      style={{
        position: 'relative',
        overflow: 'hidden',
        background: '#080C14',
        paddingTop: 88,
        paddingBottom: 104,
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `url("data:image/svg+xml,${encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.028)" stroke-width="0.5"/></svg>'
          )}")`,
          backgroundSize: '40px 40px',
          pointerEvents: 'none',
        }}
      />

      <svg
        aria-hidden="true"
        fill="none"
        height="560"
        style={{
          position: 'absolute',
          top: -48,
          right: -64,
          opacity: 0.042,
          pointerEvents: 'none',
        }}
        viewBox="0 0 680 560"
        width="680"
        xmlns="http://www.w3.org/2000/svg"
      >
        {([
          [480, 60, 560, 145],
          [480, 60, 395, 78],
          [480, 60, 514, 192],
          [560, 145, 514, 192],
          [560, 145, 618, 252],
          [514, 192, 416, 228],
          [514, 192, 536, 316],
          [395, 78, 302, 142],
          [416, 228, 302, 268],
          [416, 228, 458, 348],
          [536, 316, 618, 252],
          [536, 316, 458, 348],
          [302, 142, 302, 268],
          [302, 268, 210, 348],
          [458, 348, 374, 432],
          [302, 268, 374, 432],
        ] as [number, number, number, number][]).map(([x1, y1, x2, y2], i) => (
          <line key={i} stroke="white" strokeLinecap="round" strokeWidth="0.8" x1={x1} x2={x2} y1={y1} y2={y2} />
        ))}

        {([
          [480, 60, 3.5],
          [560, 145, 2.5],
          [395, 78, 2.5],
          [514, 192, 4.5],
          [618, 252, 2],
          [416, 228, 3],
          [536, 316, 2.5],
          [302, 142, 2.5],
          [302, 268, 3],
          [458, 348, 2.5],
          [210, 348, 2],
          [374, 432, 2],
        ] as [number, number, number][]).map(([cx, cy, r], i) => (
          <circle cx={cx} cy={cy} fill="white" key={i} r={r} />
        ))}
      </svg>

      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          bottom: -120,
          left: -80,
          width: 560,
          height: 560,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(13,148,136,0.05) 0%, transparent 62%)',
          pointerEvents: 'none',
        }}
      />

      <svg
        aria-hidden="true"
        fill="none"
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '100%',
          maxWidth: 1400,
          height: 'auto',
          opacity: 1,
          pointerEvents: 'none',
        }}
        viewBox="0 0 1200 800"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient cx="50%" cy="50%" id="teal-core" r="50%">
            <stop offset="0%" stopColor="#2dd4bf" stopOpacity="0.06" />
            <stop offset="60%" stopColor="#2dd4bf" stopOpacity="0.015" />
            <stop offset="100%" stopColor="#2dd4bf" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle cx="720" cy="380" fill="url(#teal-core)" r="260" />

        {[120, 200, 300, 420].map((r, i) => {
          const cx = 720
          const cy = 380
          const opacity = [0.045, 0.035, 0.025, 0.015][i]
          const sw = [0.8, 0.6, 0.5, 0.4][i]
          const pts = Array.from({ length: 6 }, (_, j) => {
            const angle = (Math.PI / 3) * j - Math.PI / 2
            return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`
          }).join(' ')

          return (
            <polygon fill="none" key={`hex-${i}`} points={pts} stroke="white" strokeOpacity={opacity} strokeWidth={sw} />
          )
        })}

        {Array.from({ length: 6 }, (_, j) => {
          const cx = 720
          const cy = 380
          const angle = (Math.PI / 3) * j - Math.PI / 2
          const x2 = cx + 420 * Math.cos(angle)
          const y2 = cy + 420 * Math.sin(angle)

          return <line key={`spoke-${j}`} stroke="white" strokeOpacity="0.02" strokeWidth="0.4" x1={cx} x2={x2} y1={cy} y2={y2} />
        })}

        {[120, 300].map((r, ri) =>
          [0, 2, 4].map((j) => {
            const cx = 720
            const cy = 380
            const angle = (Math.PI / 3) * j - Math.PI / 2
            const x = cx + r * Math.cos(angle)
            const y = cy + r * Math.sin(angle)
            return (
              <circle
                cx={x}
                cy={y}
                fill="#2dd4bf"
                fillOpacity={ri === 0 ? 0.12 : 0.06}
                key={`dot-${ri}-${j}`}
                r={ri === 0 ? 2 : 1.5}
              />
            )
          })
        )}

        <circle cx="720" cy="380" fill="#2dd4bf" fillOpacity="0.1" r="3" />
        <circle cx="720" cy="380" r="8" stroke="#2dd4bf" strokeOpacity="0.06" strokeWidth="0.5" />
      </svg>

      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: -200,
          right: -100,
          width: 600,
          height: 600,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(13,148,136,0.03) 0%, transparent 55%)',
          pointerEvents: 'none',
        }}
      />

      <div
        className="hero-grid"
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '0 32px',
          position: 'relative',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        <div style={{ width: '100%' }}>
          <motion.h1
            {...fadeUp(0.18)}
            style={{
              fontFamily: "'Manrope', sans-serif",
              fontWeight: 800,
              fontSize: 'clamp(40px, 5.5vw, 72px)',
              lineHeight: 1.05,
              letterSpacing: '-0.03em',
              color: '#F8FAFC',
              marginBottom: 24,
              textAlign: 'left',
            }}
          >
            Accelerating{' '}
            <span
              style={{
                background: 'linear-gradient(135deg, #5EEAD4 0%, #0D9488 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              Rare Disease
            </span>{' '}
            Research.
          </motion.h1>

          <motion.p
            {...fadeUp(0.3)}
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: 18,
              lineHeight: 1.65,
              color: '#94A3B8',
              marginBottom: 40,
              textAlign: 'left',
              maxWidth: 620,
            }}
          >
            Artana Bio builds AI-powered research infrastructure for the most underserved patients in medicine. We give
            rare disease scientists the computational tools to move from hypothesis to discovery — faster than was ever
            possible before.
          </motion.p>

          <motion.div
            {...fadeUp(0.4)}
            style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 64, justifyContent: 'flex-start' }}
          >
            <motion.a
              href="#research-space"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '14px 28px',
                background: '#0D9488',
                color: 'white',
                borderRadius: 8,
                textDecoration: 'none',
                fontFamily: "'IBM Plex Sans', sans-serif",
                fontSize: 15,
                fontWeight: 600,
                letterSpacing: '-0.01em',
                boxShadow: '0 4px 20px rgba(13,148,136,0.3)',
              }}
              whileHover={{ background: '#0F766E', y: -2 }}
              whileTap={{ scale: 0.98 }}
            >
              Explore Research Space
              <ArrowRight size={16} />
            </motion.a>
            <motion.a
              href="/platform"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '14px 28px',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 8,
                color: '#F8FAFC',
                textDecoration: 'none',
                fontFamily: "'IBM Plex Sans', sans-serif",
                fontSize: 15,
                fontWeight: 600,
                letterSpacing: '-0.01em',
                background: 'rgba(255,255,255,0.03)',
              }}
              whileHover={{ background: 'rgba(255,255,255,0.08)', borderColor: 'rgba(255,255,255,0.2)' }}
              whileTap={{ scale: 0.98 }}
            >
              Our Mission
              <ChevronRight size={15} />
            </motion.a>
          </motion.div>

        </div>
      </div>

      <div
        className="hero-divider"
        style={{
          maxWidth: 1200,
          margin: '80px auto 0',
          padding: '0 32px',
          display: 'flex',
          alignItems: 'center',
          gap: 24,
          position: 'relative',
        }}
      >
        <div style={{ flex: 1, height: 1, background: 'linear-gradient(90deg, transparent, rgba(30,45,61,0.6))' }} />
        <div style={{ flex: 1, height: 1, background: 'linear-gradient(90deg, rgba(30,45,61,0.6), transparent)' }} />
      </div>

      <div
        style={{ maxWidth: 1200, margin: '28px auto 0', padding: '0 32px' }}
      >
        <div
          className="hero-stats"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            gap: 24,
            paddingTop: 18,
            paddingBottom: 8,
          }}
        >
          {HERO_STATS.map((stat, index) => (
            <div
              className="hero-stat-item"
              key={stat.label}
              style={{
                borderLeft: index === 0 ? 'none' : '1px solid rgba(148,163,184,0.18)',
                paddingLeft: index === 0 ? 0 : 24,
              }}
            >
              <p
                style={{
                  margin: 0,
                  fontFamily: "'Manrope', sans-serif",
                  fontWeight: 800,
                  fontSize: 'clamp(32px, 4vw, 44px)',
                  lineHeight: 1.05,
                  color: '#F8FAFC',
                  letterSpacing: '-0.02em',
                }}
              >
                {stat.value}
              </p>
              <p
                style={{
                  margin: '10px 0 0',
                  fontFamily: "'IBM Plex Sans', sans-serif",
                  fontSize: 14,
                  lineHeight: 1.55,
                  color: '#7A8CA5',
                  maxWidth: 280,
                }}
              >
                {stat.label}
              </p>
            </div>
          ))}
        </div>
        <p
          style={{
            margin: '12px 0 0',
            fontFamily: "'IBM Plex Sans', sans-serif",
            fontSize: 12,
            lineHeight: 1.5,
            color: '#4E6079',
          }}
        >
          Estimates based on U.S. FDA and NCATS rare disease summaries.
        </p>
      </div>

      <style>{`
        @media (max-width: 760px) {
          .hero-divider {
            display: none !important;
          }
        }

        @media (max-width: 900px) {
          .hero-stats {
            grid-template-columns: 1fr !important;
            gap: 18px !important;
          }

          .hero-stat-item {
            border-left: none !important;
            padding-left: 0 !important;
          }
        }

        @media (max-width: 520px) {
          .hero-grid { padding: 0 20px !important; }
        }
      `}</style>
    </section>
  )
}
