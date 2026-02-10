import type { EvidenceTier } from '@/types/mechanisms'
import type { Statement, StatementStatus } from '@/types/statements'
import {
  buildDomainState,
  normalizeDomains,
  type DomainFormState,
} from '@/lib/knowledge-graph/mechanism-form'

export type StatementFormState = {
  title: string
  summary: string
  evidence_tier: EvidenceTier
  confidence_score: string
  status: StatementStatus
  source: string
  phenotype_ids: number[]
  domains: DomainFormState[]
}

export const buildStatementFormState = (
  statement?: Statement,
): StatementFormState => ({
  title: statement?.title ?? '',
  summary: statement?.summary ?? '',
  evidence_tier: statement?.evidence_tier ?? 'supporting',
  confidence_score: String(statement?.confidence_score ?? 0.5),
  status: statement?.status ?? 'draft',
  source: statement?.source ?? 'manual_curation',
  phenotype_ids: statement?.phenotype_ids ?? [],
  domains: statement?.protein_domains?.length
    ? statement.protein_domains.map(buildDomainState)
    : [],
})

export { normalizeDomains }
