'use client'

import { useEffect, useId, useState } from 'react'
import { X } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { lookupPhenotypes, searchPhenotypes } from '@/lib/api/phenotypes'
import type { PhenotypeResponse } from '@/types/generated'

interface PhenotypeMultiSelectProps {
  spaceId: string
  label: string
  description?: string
  selectedIds: number[]
  onChange: (value: number[]) => void
  placeholder?: string
  minSearchLength?: number
  disabled?: boolean
}

export function PhenotypeMultiSelect({
  spaceId,
  label,
  description,
  selectedIds,
  onChange,
  placeholder = 'Search HPO terms…',
  minSearchLength = 2,
  disabled = false,
}: PhenotypeMultiSelectProps) {
  const inputId = useId()
  const { data: session } = useSession()
  const token = session?.user?.access_token
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PhenotypeResponse[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [lookupMap, setLookupMap] = useState<Record<number, PhenotypeResponse>>({})

  useEffect(() => {
    if (!token || selectedIds.length === 0) {
      return
    }
    const missing = selectedIds.filter((id) => !lookupMap[id])
    if (missing.length === 0) {
      return
    }
    let cancelled = false
    const runLookup = async () => {
      try {
        const phenotypes = await lookupPhenotypes(spaceId, missing, token)
        if (cancelled) {
          return
        }
        setLookupMap((prev) => {
          const next = { ...prev }
          phenotypes.forEach((phenotype) => {
            next[phenotype.id] = phenotype
          })
          return next
        })
      } catch (error) {
        console.error('[PhenotypeMultiSelect] lookup failed', error)
      }
    }
    runLookup()
    return () => {
      cancelled = true
    }
  }, [lookupMap, selectedIds, spaceId, token])

  useEffect(() => {
    if (!token) {
      return
    }
    const normalized = query.trim()
    if (normalized.length < minSearchLength) {
      setResults([])
      setIsSearching(false)
      return
    }
    let cancelled = false
    setIsSearching(true)
    const timer = setTimeout(() => {
      const runSearch = async () => {
        try {
          const response = await searchPhenotypes(spaceId, normalized, 12, token)
          if (cancelled) {
            return
          }
          setResults(response)
        } catch (error) {
          if (!cancelled) {
            console.error('[PhenotypeMultiSelect] search failed', error)
            setResults([])
          }
        } finally {
          if (!cancelled) {
            setIsSearching(false)
          }
        }
      }
      runSearch()
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, minSearchLength, spaceId, token])

  const availableResults = results.filter((result) => !selectedIds.includes(result.id))

  const addPhenotype = (phenotype: PhenotypeResponse) => {
    if (selectedIds.includes(phenotype.id)) {
      return
    }
    onChange([...selectedIds, phenotype.id])
    setLookupMap((prev) => ({ ...prev, [phenotype.id]: phenotype }))
    setQuery('')
    setResults([])
  }

  const removePhenotype = (phenotypeId: number) => {
    onChange(selectedIds.filter((id) => id !== phenotypeId))
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor={inputId}>{label}</Label>
        <Input
          id={inputId}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
          disabled={disabled}
        />
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>

      {selectedIds.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedIds.map((phenotypeId) => {
            const phenotype = lookupMap[phenotypeId]
            const labelText = phenotype
              ? `${phenotype.hpo_id} • ${phenotype.name}`
              : `Phenotype #${phenotypeId}`
            return (
              <Badge key={phenotypeId} variant="secondary" className="flex items-center gap-1">
                <span>{labelText}</span>
                {!disabled && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-4 rounded-full"
                    onClick={() => removePhenotype(phenotypeId)}
                    aria-label={`Remove phenotype ${phenotypeId}`}
                  >
                    <X className="size-3" />
                  </Button>
                )}
              </Badge>
            )
          })}
        </div>
      )}

      {query.trim().length >= minSearchLength && (
        <div className="rounded border border-muted bg-muted/20 p-2">
          {isSearching ? (
            <p className="text-sm text-muted-foreground">Searching…</p>
          ) : availableResults.length === 0 ? (
            <p className="text-sm text-muted-foreground">No phenotypes found.</p>
          ) : (
            <div className="space-y-1">
              {availableResults.map((phenotype) => (
                <button
                  key={phenotype.id}
                  type="button"
                  className="w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
                  onClick={() => addPhenotype(phenotype)}
                >
                  <div className="font-medium">{phenotype.hpo_id}</div>
                  <div className="text-xs text-muted-foreground">{phenotype.name}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
