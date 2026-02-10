'use client'

import { FileText, Loader2, PlusCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface StatementHeaderProps {
  search: string
  searchChange: (value: string) => void
  createAction: () => void
  refreshAction: () => void
  isRefreshing: boolean
  canCreate: boolean
}

export function StatementHeader({
  search,
  searchChange,
  createAction,
  refreshAction,
  isRefreshing,
  canCreate,
}: StatementHeaderProps) {
  return (
    <CardHeader className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <CardTitle className="font-heading text-xl">Statements of Understanding</CardTitle>
          <CardDescription>
            Hypotheses and evolving explanations that can be promoted to canonical mechanisms.
          </CardDescription>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="outline" onClick={refreshAction} disabled={isRefreshing}>
            {isRefreshing ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Refreshing…
              </>
            ) : (
              <>
                <FileText className="mr-2 size-4" />
                Refresh
              </>
            )}
          </Button>
          {canCreate && (
            <Button onClick={createAction}>
              <PlusCircle className="mr-2 size-4" />
              Add Statement
            </Button>
          )}
        </div>
      </div>
      <div className="max-w-md space-y-2">
        <Label htmlFor="statement-search">Search</Label>
        <Input
          id="statement-search"
          placeholder="Search statements"
          value={search}
          onChange={(event) => searchChange(event.target.value)}
        />
      </div>
    </CardHeader>
  )
}
