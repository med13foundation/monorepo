"use client"

import Link from 'next/link'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Card, CardContent } from '@/components/ui/card'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { UploadCloud } from 'lucide-react'
import { ingestKernelRecordsAction } from '@/app/actions/kernel-ingest'
import type { JSONValue, JSONObject } from '@/types/generated'
import type { KernelIngestResponse } from '@/types/kernel'

interface SpaceIngestClientProps {
  spaceId: string
}

function isJsonValue(value: unknown): value is JSONValue {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return true
  }
  if (Array.isArray(value)) {
    return value.every((item) => isJsonValue(item))
  }
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).every((item) => isJsonValue(item))
  }
  return false
}

function isJsonObject(value: unknown): value is JSONObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  return Object.values(value as Record<string, unknown>).every((item) => isJsonValue(item))
}

export default function SpaceIngestClient({ spaceId }: SpaceIngestClientProps) {
  const router = useRouter()
  const [entityType, setEntityType] = useState('GENE')
  const [recordType, setRecordType] = useState('')
  const [rowsJson, setRowsJson] = useState(
    JSON.stringify([{ gene_symbol: 'MED13', note: 'hello kernel ingest' }], null, 2),
  )
  const [isRunning, setIsRunning] = useState(false)
  const [lastResult, setLastResult] = useState<KernelIngestResponse | null>(null)

  async function handleRun() {
    const entityTypeTrim = entityType.trim()
    if (!entityTypeTrim) {
      toast.error('Entity type is required')
      return
    }

    let parsedRows: unknown
    try {
      parsedRows = JSON.parse(rowsJson) as unknown
    } catch {
      toast.error('Rows must be valid JSON')
      return
    }

    if (!Array.isArray(parsedRows)) {
      toast.error('Rows JSON must be an array of objects')
      return
    }

    const rows = parsedRows.filter((row): row is JSONObject => isJsonObject(row))
    if (rows.length != parsedRows.length) {
      toast.error('Each row must be a JSON object (values must be valid JSON primitives/arrays/objects).')
      return
    }

    const payload = {
      entity_type: entityTypeTrim,
      record_type: recordType.trim() || null,
      records: rows.map((row, idx) => ({
        source_id: `row-${idx + 1}`,
        data: row,
        metadata: {},
      })),
    }

    setIsRunning(true)
    const result = await ingestKernelRecordsAction(spaceId, payload)
    setIsRunning(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    setLastResult(result.data)
    toast.success(
      `Ingested: ${result.data.entities_created} entities, ${result.data.observations_created} observations`,
    )
    router.refresh()
  }

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Ingest"
        description="Upload or connect data sources, map to the dictionary, normalize units, resolve entities, and write kernel facts."
      >
        <div className="space-y-4">
          <Card>
            <CardHeader className="space-y-1">
              <CardTitle className="text-lg">Quick Ingest (JSON)</CardTitle>
              <CardDescription>
                Submit raw rows as JSON. Mapping is deterministic (synonyms only) and will only record observations when
                keys match dictionary synonyms.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="entity_type">Entity Type</Label>
                  <Input
                    id="entity_type"
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                    placeholder="GENE"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="record_type">Record Type (optional)</Label>
                  <Input
                    id="record_type"
                    value={recordType}
                    onChange={(e) => setRecordType(e.target.value)}
                    placeholder="pubmed"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="rows">Rows (JSON Array)</Label>
                <Textarea
                  id="rows"
                  value={rowsJson}
                  onChange={(e) => setRowsJson(e.target.value)}
                  className="min-h-[220px] font-mono text-xs"
                />
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button onClick={() => handleRun()} disabled={isRunning}>
                  <UploadCloud className="mr-2 size-4" />
                  Run Ingest
                </Button>
                <Button asChild variant="outline">
                  <Link href={`/spaces/${spaceId}/observations`}>View Observations</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href={`/spaces/${spaceId}/knowledge-graph`}>View Graph</Link>
                </Button>
              </div>
            </CardContent>
          </Card>

          {lastResult && (
            <Card>
              <CardHeader className="space-y-1">
                <CardTitle className="text-lg">Last Run</CardTitle>
                <CardDescription>
                  {lastResult.success ? 'Success' : 'Completed with errors'}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <strong>Entities created:</strong> {lastResult.entities_created}
                </div>
                <div>
                  <strong>Observations created:</strong> {lastResult.observations_created}
                </div>
                {lastResult.errors.length > 0 && (
                  <div className="space-y-1">
                    <strong>Errors:</strong>
                    <ul className="list-disc pl-5 text-destructive">
                      {lastResult.errors.slice(0, 10).map((err) => (
                        <li key={err}>{err}</li>
                      ))}
                    </ul>
                    {lastResult.errors.length > 10 && (
                      <div className="text-xs text-muted-foreground">
                        Showing first 10 errors.
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="flex flex-col gap-2 py-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-muted-foreground">
                Need to add mappings? Create variables and synonyms in the Dictionary.
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button asChild variant="outline">
                  <Link href={`/spaces/${spaceId}/data-sources`}>Manage Data Sources</Link>
                </Button>
                <Button asChild>
                  <Link href="/admin/dictionary">Edit Dictionary</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </DashboardSection>
    </div>
  )
}
