import type { EvidenceTier, ProteinDomainPayload } from '@/types/mechanisms'

export type StatementStatus = 'draft' | 'under_review' | 'well_supported'

export interface Statement {
  id: number
  title: string
  summary: string
  evidence_tier: EvidenceTier
  confidence_score: number
  status: StatementStatus
  source: string
  protein_domains: ProteinDomainPayload[]
  phenotype_ids: number[]
  phenotype_count: number
  promoted_mechanism_id?: number | null
  created_at: string
  updated_at: string
}

export interface StatementCreateRequest {
  title: string
  summary: string
  evidence_tier: EvidenceTier
  confidence_score: number
  status?: StatementStatus
  source: string
  protein_domains: ProteinDomainPayload[]
  phenotype_ids: number[]
}

export interface StatementUpdateRequest {
  title?: string | null
  summary?: string | null
  evidence_tier?: EvidenceTier | null
  confidence_score?: number | null
  status?: StatementStatus | null
  source?: string | null
  protein_domains?: ProteinDomainPayload[] | null
  phenotype_ids?: number[] | null
  promoted_mechanism_id?: number | null
}
