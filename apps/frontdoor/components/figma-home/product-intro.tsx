'use client'

import { ArrowRight, ChevronRight } from './icons'
import { motion } from '@/lib/motion-compat'

import { ScrollReveal } from './scroll-reveal'

function KnowledgeGraphCard(): JSX.Element {
  const nodes = [
    { id: 'med13', cx: 228, cy: 148, r: 17, fill: '#0D9488', stroke: '#5EEAD4', strokeW: 1.5, label: 'MED13', labelDy: -24 },
    { id: 'brd4', cx: 318, cy: 84, r: 12, fill: '#1E293B', stroke: '#334155', strokeW: 1, label: 'BRD4', labelDy: -18 },
    { id: 'cdk8', cx: 340, cy: 200, r: 12, fill: '#1E293B', stroke: '#334155', strokeW: 1, label: 'CDK8', labelDy: 22 },
    { id: 'sox2', cx: 142, cy: 72, r: 11, fill: '#1E293B', stroke: '#334155', strokeW: 1, label: 'SOX2', labelDy: -17 },
    { id: 'oct4', cx: 118, cy: 202, r: 11, fill: '#1E293B', stroke: '#334155', strokeW: 1, label: 'OCT4', labelDy: 22 },
    { id: 'ccnt1', cx: 228, cy: 250, r: 9, fill: '#2D3748', stroke: '#4A5568', strokeW: 1, label: 'CCNT1', labelDy: 20 },
    { id: 'lit1', cx: 390, cy: 58, r: 5, fill: '#334155', stroke: '#475569', strokeW: 1, label: '', labelDy: 0 },
    { id: 'lit2', cx: 408, cy: 205, r: 5, fill: '#334155', stroke: '#475569', strokeW: 1, label: '', labelDy: 0 },
    { id: 'lit3', cx: 68, cy: 46, r: 5, fill: '#334155', stroke: '#475569', strokeW: 1, label: '', labelDy: 0 },
    { id: 'lit4', cx: 42, cy: 218, r: 5, fill: '#334155', stroke: '#475569', strokeW: 1, label: '', labelDy: 0 },
  ]

  const edges = [
    { x1: 228, y1: 148, x2: 318, y2: 84, stroke: '#0D9488', opacity: 0.7, strokeW: 1.5 },
    { x1: 228, y1: 148, x2: 340, y2: 200, stroke: '#0D9488', opacity: 0.6, strokeW: 1.5 },
    { x1: 228, y1: 148, x2: 142, y2: 72, stroke: '#0D9488', opacity: 0.65, strokeW: 1.5 },
    { x1: 228, y1: 148, x2: 118, y2: 202, stroke: '#0D9488', opacity: 0.6, strokeW: 1.5 },
    { x1: 228, y1: 148, x2: 228, y2: 250, stroke: '#4B5563', opacity: 0.5, strokeW: 1 },
    { x1: 318, y1: 84, x2: 390, y2: 58, stroke: '#334155', opacity: 0.35, strokeW: 1, dash: '4 3' },
    { x1: 340, y1: 200, x2: 408, y2: 205, stroke: '#334155', opacity: 0.35, strokeW: 1, dash: '4 3' },
    { x1: 142, y1: 72, x2: 68, y2: 46, stroke: '#334155', opacity: 0.35, strokeW: 1, dash: '4 3' },
    { x1: 118, y1: 202, x2: 42, y2: 218, stroke: '#334155', opacity: 0.35, strokeW: 1, dash: '4 3' },
    { x1: 318, y1: 84, x2: 340, y2: 200, stroke: '#475569', opacity: 0.3, strokeW: 1 },
    { x1: 142, y1: 72, x2: 118, y2: 202, stroke: '#475569', opacity: 0.3, strokeW: 1 },
  ]

  const edgeLabels = [
    { x: 282, y: 112, text: 'activates', fill: '#14B8A6' },
    { x: 186, y: 104, text: 'binds', fill: '#14B8A6' },
    { x: 332, y: 148, text: 'co-reg.', fill: '#64748B' },
  ]

  return (
    <motion.div
      style={{
        borderRadius: 14,
        overflow: 'hidden',
        border: '1px solid #1E2D3D',
        boxShadow: '0 24px 60px rgba(0,0,0,0.55), 0 0 0 1px rgba(94,234,212,0.06)',
        background: '#0D1117',
        position: 'relative',
      }}
      transition={{ duration: 0.3 }}
      whileHover={{
        boxShadow: '0 28px 70px rgba(0,0,0,0.65), 0 0 0 1px rgba(94,234,212,0.12), 0 0 40px rgba(13,148,136,0.08)',
      }}
    >
      <div style={{ background: '#0B0F1A', borderBottom: '1px solid #1E2D3D', padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flex: 1 }}>
          <motion.span
            animate={{ boxShadow: ['0 0 5px #10B981', '0 0 11px #10B981', '0 0 5px #10B981'] }}
            style={{ width: 7, height: 7, borderRadius: '50%', background: '#10B981', display: 'inline-block', flexShrink: 0, boxShadow: '0 0 5px #10B981' }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
          <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#CBD5E1', letterSpacing: '0.01em' }}>
            Private Research Space
          </span>
        </div>
        <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: '#475569' }}>MED13 Complex Study</span>
      </div>

      <div style={{ padding: '6px 6px 4px' }}>
        <svg aria-label="Knowledge graph visualization" style={{ width: '100%', height: 'auto', display: 'block' }} viewBox="0 0 460 296">
          <defs>
            <filter height="220%" id="pi-nodeGlow" width="220%" x="-60%" y="-60%">
              <feGaussianBlur result="blur" stdDeviation="5" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter height="300%" id="pi-centralGlow" width="300%" x="-100%" y="-100%">
              <feGaussianBlur result="blur" stdDeviation="8" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <pattern height="24" id="pi-graphGrid" patternUnits="userSpaceOnUse" width="24">
              <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#1A2233" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect fill="url(#pi-graphGrid)" height="296" width="460" />
          {edges.map((e, i) => (
            <line key={i} stroke={e.stroke} strokeDasharray={e.dash} strokeOpacity={e.opacity} strokeWidth={e.strokeW} x1={e.x1} x2={e.x2} y1={e.y1} y2={e.y2} />
          ))}
          {edgeLabels.map((el, i) => (
            <text
              fill={el.fill}
              key={i}
              style={{ fontSize: 8, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 500 }}
              textAnchor="middle"
              x={el.x}
              y={el.y}
            >
              {el.text}
            </text>
          ))}
          <text style={{ fontSize: 7, fontFamily: "'IBM Plex Mono', monospace" }} textAnchor="middle" x={390} y={44} fill="#334155">PAPER</text>
          <text style={{ fontSize: 7, fontFamily: "'IBM Plex Mono', monospace" }} textAnchor="middle" x={408} y={191} fill="#334155">PAPER</text>
          <text style={{ fontSize: 7, fontFamily: "'IBM Plex Mono', monospace" }} textAnchor="middle" x={68} y={32} fill="#334155">PAPER</text>
          <text style={{ fontSize: 7, fontFamily: "'IBM Plex Mono', monospace" }} textAnchor="middle" x={42} y={204} fill="#334155">PAPER</text>

          {nodes.filter((n) => n.id !== 'med13').map((node) => (
            <g filter={node.r >= 10 ? 'url(#pi-nodeGlow)' : undefined} key={node.id}>
              <circle cx={node.cx} cy={node.cy} fill={node.fill} r={node.r} stroke={node.stroke} strokeWidth={node.strokeW} />
              {node.label ? (
                <text
                  fill="#94A3B8"
                  style={{ fontSize: 9, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 500 }}
                  textAnchor="middle"
                  x={node.cx}
                  y={node.cy + node.labelDy}
                >
                  {node.label}
                </text>
              ) : null}
            </g>
          ))}

          <g filter="url(#pi-centralGlow)">
            <circle cx={228} cy={148} fill="#0D9488" fillOpacity={0.15} r={22} />
            <circle cx={228} cy={148} fill="#0D9488" r={17} stroke="#5EEAD4" strokeWidth={1.5} />
          </g>
          <text style={{ fontSize: 8, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600 }} textAnchor="middle" x={228} y={152} fill="white">MED13</text>

          <g transform="translate(294,238)">
            <rect fill="#0D9488" fillOpacity={0.9} height={13} rx={3} width={28} x={-14} y={-8} />
            <text fill="white" style={{ fontSize: 7, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600 }} textAnchor="middle" x={0} y={2}>NEW</text>
          </g>
        </svg>
      </div>

      <div style={{ background: '#0B0F1A', borderTop: '1px solid #1A2233', padding: '10px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 20 }}>
          {[{ value: '847', label: 'relationships' }, { value: '2,340', label: 'papers indexed' }].map((stat) => (
            <span key={stat.label} style={{ display: 'flex', gap: 5, alignItems: 'baseline' }}>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, fontWeight: 600, color: '#CBD5E1' }}>{stat.value}</span>
              <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 10, color: '#475569' }}>{stat.label}</span>
            </span>
          ))}
        </div>
        <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 10, color: '#334155' }}>Updated 2 min ago</span>
      </div>
    </motion.div>
  )
}

export function FigmaProductIntro(): JSX.Element {
  return (
    <section
      id="research-space"
      style={{
        position: 'relative',
        overflow: 'hidden',
        background: '#FFFFFF',
        paddingTop: 96,
        paddingBottom: 104,
        borderTop: '1px solid #EEE9E2',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(circle, #CBD5E1 1px, transparent 1px)',
          backgroundSize: '28px 28px',
          opacity: 0.35,
          pointerEvents: 'none',
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          bottom: -80,
          left: -80,
          width: 560,
          height: 560,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(13,148,136,0.05) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      <div
        className="pi-grid"
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '0 32px',
          position: 'relative',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 64,
          alignItems: 'center',
        }}
      >
        <div style={{ maxWidth: 580 }}>
          <ScrollReveal>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginBottom: 32 }}>
              <span
                style={{
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: 11,
                  fontWeight: 600,
                  color: '#0D9488',
                  background: '#F0FDFA',
                  border: '1px solid #CCFBF1',
                  borderRadius: 6,
                  padding: '4px 10px',
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                }}
              >
                Research Space
              </span>
              <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 12, color: '#94A3B8' }}>—</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#F59E0B', display: 'inline-block' }} />
                <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#D97706', letterSpacing: '0.01em' }}>
                  Coming Soon
                </span>
              </div>
            </div>
          </ScrollReveal>

          <ScrollReveal delay={0.08}>
            <h2
              style={{
                fontFamily: "'Manrope', sans-serif",
                fontWeight: 800,
                fontSize: 'clamp(32px, 4.5vw, 56px)',
                lineHeight: 1.1,
                letterSpacing: '-1.4px',
                color: '#0B0F1A',
                marginBottom: 24,
              }}
            >
              Research <span style={{ color: '#0D9488' }}>Space.</span>
            </h2>
            <p
              style={{
                fontFamily: "'IBM Plex Sans', sans-serif",
                fontSize: 18,
                lineHeight: 1.5,
                color: '#0B0F1A',
                fontWeight: 500,
                marginBottom: 16,
                letterSpacing: '-0.2px',
              }}
            >
              A private, auto-updating knowledge graph for your lab&apos;s discoveries.
            </p>
          </ScrollReveal>

          <ScrollReveal delay={0.16}>
            <p style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: 16, lineHeight: 1.74, color: '#4B5568', marginBottom: 40, maxWidth: 520 }}>
              Replace static reference managers and noisy global databases with a computable knowledge graph that
              continuously reads literature, extracts precise biological relationships, and turns your projects into a
              living discovery engine — built specifically for rare disease research.
            </p>
          </ScrollReveal>

          <ScrollReveal delay={0.22} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
            <motion.a
              href="/request-access"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '13px 24px',
                background: '#0D9488',
                color: 'white',
                borderRadius: 8,
                textDecoration: 'none',
                fontFamily: "'IBM Plex Sans', sans-serif",
                fontSize: 15,
                fontWeight: 600,
                letterSpacing: '-0.1px',
                boxShadow: '0 1px 3px rgba(13,148,136,0.3), 0 4px 12px rgba(13,148,136,0.15)',
              }}
              whileHover={{ background: '#0F766E', y: -2 }}
              whileTap={{ scale: 0.98 }}
            >
              Get Early Access
              <ArrowRight size={16} />
            </motion.a>
            <motion.a
              href="#how-it-works"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 7,
                padding: '13px 22px',
                background: 'white',
                color: '#0B0F1A',
                borderRadius: 8,
                textDecoration: 'none',
                fontFamily: "'IBM Plex Sans', sans-serif",
                fontSize: 15,
                fontWeight: 600,
                border: '1.5px solid #E2E8F0',
                letterSpacing: '-0.1px',
              }}
              whileHover={{ borderColor: '#0D9488', color: '#0D9488' }}
              whileTap={{ scale: 0.98 }}
            >
              See How It Works
              <ChevronRight size={15} />
            </motion.a>
          </ScrollReveal>

        </div>

        <ScrollReveal className="pi-graph" delay={0.1} direction="right" style={{ width: '100%' }}>
          <KnowledgeGraphCard />
        </ScrollReveal>
      </div>

      <style>{`
        @media (max-width: 860px) {
          .pi-grid { grid-template-columns: 1fr !important; gap: 48px !important; }
          .pi-graph { max-width: 480px; margin: 0 auto; }
        }

        @media (max-width: 520px) {
          .pi-grid { padding: 0 20px !important; }
        }
      `}</style>
    </section>
  )
}
