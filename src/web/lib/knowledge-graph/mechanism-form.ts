import type {
  EvidenceTier,
  Mechanism,
  MechanismLifecycleState,
  ProteinDomainPayload,
  ProteinDomainType,
} from '@/types/mechanisms'

export type DomainFormState = {
  name: string
  source_id: string
  start_residue: string
  end_residue: string
  domain_type: ProteinDomainType
  description: string
}

export type MechanismFormState = {
  name: string
  description: string
  evidence_tier: EvidenceTier
  confidence_score: string
  source: string
  lifecycle_state: MechanismLifecycleState
  phenotype_ids: number[]
  domains: DomainFormState[]
}

export const buildDomainState = (domain?: ProteinDomainPayload): DomainFormState => ({
  name: domain?.name ?? '',
  source_id: domain?.source_id ?? '',
  start_residue: domain?.start_residue ? String(domain.start_residue) : '',
  end_residue: domain?.end_residue ? String(domain.end_residue) : '',
  domain_type: domain?.domain_type ?? 'structural',
  description: domain?.description ?? '',
})

export const buildFormState = (mechanism?: Mechanism): MechanismFormState => ({
  name: mechanism?.name ?? '',
  description: mechanism?.description ?? '',
  evidence_tier: mechanism?.evidence_tier ?? 'supporting',
  confidence_score: String(mechanism?.confidence_score ?? 0.5),
  source: mechanism?.source ?? 'manual_curation',
  lifecycle_state: mechanism?.lifecycle_state ?? 'draft',
  phenotype_ids: mechanism?.phenotype_ids ?? [],
  domains: mechanism?.protein_domains?.length
    ? mechanism.protein_domains.map(buildDomainState)
    : [],
})

export const normalizeDomains = (domains: DomainFormState[]): ProteinDomainPayload[] => {
  return domains
    .filter((domain) => domain.name.trim())
    .map((domain) => {
      const start = Number.parseInt(domain.start_residue, 10)
      const end = Number.parseInt(domain.end_residue, 10)
      return {
        name: domain.name.trim(),
        source_id: domain.source_id.trim() || undefined,
        start_residue: Number.isFinite(start) ? start : 1,
        end_residue: Number.isFinite(end) ? end : 1,
        domain_type: domain.domain_type,
        description: domain.description.trim() || undefined,
      }
    })
}
