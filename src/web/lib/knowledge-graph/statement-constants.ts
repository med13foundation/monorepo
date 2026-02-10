import type { StatementStatus } from '@/types/statements'

export const STATEMENT_STATUS_LABELS: Record<StatementStatus, string> = {
  draft: 'Draft',
  under_review: 'Under review',
  well_supported: 'Well supported',
}

export const STATEMENT_STATUS_VARIANTS: Record<
  StatementStatus,
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  draft: 'outline',
  under_review: 'secondary',
  well_supported: 'default',
}
