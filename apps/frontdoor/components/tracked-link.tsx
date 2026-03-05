'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'

import { trackEvent } from '@/lib/analytics'

type TrackedLinkProps = {
  href: string
  children: ReactNode
  className?: string
  eventLabel: string
  eventCategory?: string
  external?: boolean
  ariaLabel?: string
}

const isExternalUrl = (href: string): boolean => {
  return href.startsWith('http://') || href.startsWith('https://')
}

export const TrackedLink = ({
  href,
  children,
  className,
  eventLabel,
  eventCategory = 'cta',
  external,
  ariaLabel,
}: TrackedLinkProps): JSX.Element => {
  const treatAsExternal = external ?? isExternalUrl(href)

  const handleClick = (): void => {
    trackEvent('cta_click', {
      label: eventLabel,
      category: eventCategory,
      href,
    })
  }

  if (treatAsExternal) {
    return (
      <a
        aria-label={ariaLabel}
        className={className}
        href={href}
        onClick={handleClick}
        rel="noopener noreferrer"
        target="_blank"
      >
        {children}
      </a>
    )
  }

  return (
    <Link aria-label={ariaLabel} className={className} href={href} onClick={handleClick}>
      {children}
    </Link>
  )
}
