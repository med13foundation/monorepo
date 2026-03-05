import type { ReactNode } from 'react'

import { FigmaFooter } from '@/components/figma-home/footer'
import { FigmaNav } from '@/components/figma-home/nav'

export default function SiteLayout({ children }: { children: ReactNode }): JSX.Element {
  return (
    <div className="frontdoor-shell">
      <FigmaNav />
      <main id="main-content">{children}</main>
      <FigmaFooter />
    </div>
  )
}
