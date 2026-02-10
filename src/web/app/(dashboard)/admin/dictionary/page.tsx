import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import DictionaryClient from './dictionary-client'
import {
  fetchDictionaryRelationConstraints,
  fetchDictionaryResolutionPolicies,
  fetchDictionaryTransforms,
  fetchDictionaryVariables,
} from '@/lib/api/dictionary'
import { UserRole } from '@/types/auth'
import type {
  EntityResolutionPolicyListResponse,
  RelationConstraintListResponse,
  TransformRegistryListResponse,
  VariableDefinitionListResponse,
} from '@/types/dictionary'

export default async function DictionaryPage() {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user.role !== UserRole.ADMIN) {
    redirect('/dashboard?error=AdminOnly')
  }

  let variables: VariableDefinitionListResponse | null = null
  let variablesError: string | null = null
  let transforms: TransformRegistryListResponse | null = null
  let transformsError: string | null = null
  let policies: EntityResolutionPolicyListResponse | null = null
  let policiesError: string | null = null
  let constraints: RelationConstraintListResponse | null = null
  let constraintsError: string | null = null

  try {
    variables = await fetchDictionaryVariables({}, token)
  } catch (error) {
    variablesError = error instanceof Error ? error.message : 'Unable to load dictionary variables.'
    console.error('[DictionaryPage] Failed to fetch variables', error)
  }

  try {
    transforms = await fetchDictionaryTransforms({}, token)
  } catch (error) {
    transformsError = error instanceof Error ? error.message : 'Unable to load transform registry.'
    console.error('[DictionaryPage] Failed to fetch transforms', error)
  }

  try {
    policies = await fetchDictionaryResolutionPolicies(token)
  } catch (error) {
    policiesError = error instanceof Error ? error.message : 'Unable to load resolution policies.'
    console.error('[DictionaryPage] Failed to fetch resolution policies', error)
  }

  try {
    constraints = await fetchDictionaryRelationConstraints({}, token)
  } catch (error) {
    constraintsError = error instanceof Error ? error.message : 'Unable to load relation constraints.'
    console.error('[DictionaryPage] Failed to fetch relation constraints', error)
  }

  return (
    <DictionaryClient
      variables={variables}
      variablesError={variablesError}
      transforms={transforms}
      transformsError={transformsError}
      policies={policies}
      policiesError={policiesError}
      constraints={constraints}
      constraintsError={constraintsError}
    />
  )
}
