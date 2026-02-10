export type EvidenceTier =
  | 'definitive'
  | 'strong'
  | 'moderate'
  | 'supporting'
  | 'weak'
  | 'disproven'

export type MechanismLifecycleState =
  | 'draft'
  | 'reviewed'
  | 'canonical'
  | 'deprecated'

export type ProteinDomainType =
  | 'structural'
  | 'functional'
  | 'binding_site'
  | 'disordered'

export interface ProteinDomainCoordinate {
  x: number
  y: number
  z: number
  confidence?: number | null
}

export interface ProteinDomainPayload {
  name: string
  source_id?: string | null
  start_residue: number
  end_residue: number
  domain_type: ProteinDomainType
  description?: string | null
  coordinates?: ProteinDomainCoordinate[] | null
}

export interface Mechanism {
  id: number
  name: string
  description?: string | null
  evidence_tier: EvidenceTier
  confidence_score: number
  source: string
  lifecycle_state: MechanismLifecycleState
  protein_domains: ProteinDomainPayload[]
  phenotype_ids: number[]
  phenotype_count: number
  created_at: string
  updated_at: string
}

export interface MechanismCreateRequest {
  name: string
  description: string
  evidence_tier: EvidenceTier
  confidence_score: number
  source: string
  lifecycle_state?: MechanismLifecycleState
  protein_domains: ProteinDomainPayload[]
  phenotype_ids: number[]
}

export interface MechanismUpdateRequest {
  name?: string | null
  description?: string | null
  evidence_tier?: EvidenceTier | null
  confidence_score?: number | null
  source?: string | null
  lifecycle_state?: MechanismLifecycleState | null
  protein_domains?: ProteinDomainPayload[] | null
  phenotype_ids?: number[] | null
}
