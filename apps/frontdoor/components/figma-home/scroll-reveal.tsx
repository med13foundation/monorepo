'use client'

import { useRef, type CSSProperties, type ReactNode } from 'react'

import { motion, useInView } from '@/lib/motion-compat'

type ScrollRevealProps = {
  children: ReactNode
  delay?: number
  direction?: 'up' | 'left' | 'right' | 'none'
  distance?: number
  duration?: number
  style?: CSSProperties
  className?: string
}

const EASE = [0.22, 1, 0.36, 1] as const

export function ScrollReveal({
  children,
  delay = 0,
  direction = 'up',
  distance = 22,
  duration = 0.56,
  style,
  className,
}: ScrollRevealProps): JSX.Element {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-72px 0px' })

  const initial = {
    opacity: 0,
    y: direction === 'up' ? distance : 0,
    x: direction === 'left' ? -distance : direction === 'right' ? distance : 0,
  }

  return (
    <motion.div
      animate={inView ? { opacity: 1, y: 0, x: 0 } : initial}
      className={className}
      initial={initial}
      ref={ref}
      style={style}
      transition={{ duration, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  )
}

type StaggerProps = {
  children: ReactNode
  stagger?: number
  delayStart?: number
  style?: CSSProperties
  className?: string
}

export function StaggerReveal({
  children,
  stagger = 0.09,
  delayStart = 0,
  style,
  className,
}: StaggerProps): JSX.Element {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-72px 0px' })

  return (
    <motion.div
      animate={inView ? 'visible' : 'hidden'}
      className={className}
      initial="hidden"
      ref={ref}
      style={style}
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: stagger, delayChildren: delayStart } },
      }}
    >
      {children}
    </motion.div>
  )
}

type StaggerItemProps = {
  children: ReactNode
  direction?: 'up' | 'left' | 'right' | 'none'
  distance?: number
  style?: CSSProperties
  className?: string
}

export function StaggerItem({
  children,
  direction = 'up',
  distance = 20,
  style,
  className,
}: StaggerItemProps): JSX.Element {
  const hidden = {
    opacity: 0,
    y: direction === 'up' ? distance : 0,
    x: direction === 'left' ? -distance : direction === 'right' ? distance : 0,
  }

  return (
    <motion.div
      className={className}
      style={style}
      variants={{
        hidden,
        visible: { opacity: 1, y: 0, x: 0, transition: { duration: 0.52, ease: EASE } },
      }}
    >
      {children}
    </motion.div>
  )
}
