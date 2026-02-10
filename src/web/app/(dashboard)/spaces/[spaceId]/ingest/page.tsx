import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceIngestClient from '../space-ingest-client'

interface SpaceIngestPageProps {
  params: { spaceId: string }
}

export default async function SpaceIngestPage({ params }: SpaceIngestPageProps) {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  return <SpaceIngestClient spaceId={params.spaceId} />
}
