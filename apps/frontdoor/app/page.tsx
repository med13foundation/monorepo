import { FigmaHomePage } from '@/components/figma-home/home-page'
import { buildMetadata } from '@/lib/metadata'

export const metadata = buildMetadata({
  title: 'Artana.bio | Accelerating Rare Disease Research',
  description:
    'Artana.bio builds AI-powered research infrastructure for rare disease discovery with private research spaces, security-first architecture, and developer-ready graph APIs.',
  path: '/',
})

export default function HomePage(): JSX.Element {
  return <FigmaHomePage />
}
