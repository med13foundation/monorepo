import type {
  EvidenceTier,
  MechanismLifecycleState,
  ProteinDomainType,
} from '@/types/mechanisms'

export const EVIDENCE_TIER_LABELS: Record<EvidenceTier, string> = {
  definitive: 'Definitive',
  strong: 'Strong',
  moderate: 'Moderate',
  supporting: 'Supporting',
  weak: 'Weak',
  disproven: 'Disproven',
}

export const EVIDENCE_TIER_VARIANTS: Record<
  EvidenceTier,
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  definitive: 'default',
  strong: 'default',
  moderate: 'secondary',
  supporting: 'outline',
  weak: 'outline',
  disproven: 'destructive',
}

export const DOMAIN_TYPE_OPTIONS: { label: string; value: ProteinDomainType }[] = [
  { label: 'Structural', value: 'structural' },
  { label: 'Functional', value: 'functional' },
  { label: 'Binding site', value: 'binding_site' },
  { label: 'Disordered', value: 'disordered' },
]

export const MECHANISM_LIFECYCLE_LABELS: Record<MechanismLifecycleState, string> = {
  draft: 'Draft',
  reviewed: 'Reviewed',
  canonical: 'Canonical',
  deprecated: 'Deprecated',
}

export const MECHANISM_LIFECYCLE_VARIANTS: Record<
  MechanismLifecycleState,
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  draft: 'outline',
  reviewed: 'secondary',
  canonical: 'default',
  deprecated: 'destructive',
}
