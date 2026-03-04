import type { GenerateHypothesesResponse } from '@/types/kernel'

type FeedbackTone = 'default' | 'success' | 'error'

interface GenerationFeedback {
  summary: string
  details: string[]
  tone: FeedbackTone
}

function summarizeErrorCode(code: string): string {
  if (code === 'no_seed_entities_resolved') {
    return 'No seed entities were available for graph exploration.'
  }
  if (code === 'no_candidates_discovered') {
    return 'Graph exploration returned no candidate relations.'
  }
  if (code === 'all_candidates_below_threshold') {
    return 'Candidates were found but all scored below the acceptance threshold.'
  }
  if (code === 'all_candidates_deduped') {
    return 'Candidates were found but all were duplicates of existing hypotheses.'
  }
  if (code === 'no_candidates_selected') {
    return 'Candidates were found but none passed final selection.'
  }
  if (code === 'candidate_missing_relation_type') {
    return 'Some candidates were dropped due to missing relation type.'
  }
  if (code.startsWith('seed_discovery_failed:')) {
    const parts = code.split(':')
    if (parts.length >= 3) {
      return `Seed discovery failed (${parts[2]}).`
    }
    return 'Seed discovery failed for one or more seeds.'
  }
  if (code.startsWith('candidate_endpoint_unresolved:')) {
    return 'Some candidates were dropped because source/target entities could not be resolved.'
  }
  return code.split('_').join(' ')
}

function dedupeStrings(values: string[]): string[] {
  const seen = new Set<string>()
  const deduped: string[] = []
  for (const value of values) {
    if (seen.has(value)) {
      continue
    }
    seen.add(value)
    deduped.push(value)
  }
  return deduped
}

export function buildHypothesisGenerationFeedback(
  response: GenerateHypothesesResponse,
): GenerationFeedback {
  if (response.created_count > 0) {
    return {
      summary: `Generated ${response.created_count} hypotheses (deduped ${response.deduped_count}).`,
      details: [],
      tone: 'success',
    }
  }

  const derivedDetails: string[] = []
  if (response.used_seed_count === 0) {
    derivedDetails.push('No seeds were resolved for this space.')
  }
  if (response.used_seed_count > 0 && response.candidates_seen === 0) {
    derivedDetails.push('No graph relation candidates were returned for the selected seeds.')
  }
  if (response.deduped_count > 0) {
    derivedDetails.push(`All eligible candidates were deduped (${response.deduped_count}).`)
  }

  const errorDetails = response.errors.map(summarizeErrorCode)
  const details = dedupeStrings([...derivedDetails, ...errorDetails]).slice(0, 4)
  const summary = 'Generation completed but produced no new hypotheses.'
  return {
    summary,
    details,
    tone: details.length > 0 ? 'error' : 'default',
  }
}
